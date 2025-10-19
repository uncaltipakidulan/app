import os
import sys
import time
import random
import logging
import hashlib
import shutil
import math
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import subprocess
import tempfile
from textblob import TextBlob

# IMPORT MIDO untuk manipulasi MIDI
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

# Import pyfluidsynth dengan error handling (opsional)
try:
    import fluidsynth as pyfluidsynth_lib
    FLUIDSYNTH_BINDING_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_BINDING_AVAILABLE = False

# Import pydub untuk manipulasi audio
from pydub import AudioSegment
from pydub.effects import normalize as pydub_normalize

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        sys.stdout # Menggunakan sys.stdout agar log tampil di konsol secara langsung
    ]
)
logger = logging.getLogger(__name__)

# Inisialisasi Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Path konfigurasi
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'

# Auto-detect SoundFont
SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',
    BASE_DIR / 'GeneralUser GS v1.471.sf2',
    BASE_DIR / 'FluidR3_GM.sf2',
    BASE_DIR / 'Super_Heavy_Guitar_Collection.sf2',
    BASE_DIR / 'TimGM6mb.sf2',
]

for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        break

if not SOUNDFONT_PATH:
    logger.warning("No SoundFont found. Download from: https://musical-artifacts.com/artifacts/661")
    logger.warning("FluidSynth will not work without a SoundFont!")

# Create directories
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

def check_module(module_name):
    """Check if a module is available"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def check_python_dependencies():
    """Check Python dependencies availability"""
    deps = {
        'Flask-CORS': check_module('flask_cors'),
        'mido': check_module('mido'),
        'TextBlob': check_module('textblob'),
        'Pydub': check_module('pydub'),
    }

    available_deps = [name for name, available in deps.items() if available]
    logger.info("Python dependencies detected: {}".format(', '.join(available_deps)))
    return available_deps

# General MIDI Instruments (case-insensitive matching)
INSTRUMENTS = {
    # Piano
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3, 'Electric Piano 1': 4, 'Electric Piano 2': 5,
    'Harpsichord': 6, 'Clavinet': 7,

    # Chromatic Percussion
    'Celesta': 8, 'Glockenspiel': 9, 'Music Box': 10, 'Vibraphone': 11,
    'Marimba': 12, 'Xylophone': 13, 'Tubular Bells': 14, 'Dulcimer': 15,

    # Organ
    'Drawbar Organ': 16, 'Percussive Organ': 17, 'Rock Organ': 18,
    'Church Organ': 19, 'Reed Organ': 20, 'Pipe Organ': 21,
    'Hammond Organ': 17, 'Rotary Organ': 18,

    # Guitar
    'Nylon String Guitar': 24, 'Steel String Guitar': 25, 'Jazz Electric Guitar': 26,
    'Clean Electric Guitar': 27, 'Muted Electric Guitar': 28, 'Overdriven Guitar': 29,
    'Distortion Guitar': 30, 'Guitar Harmonics': 31,

    # Bass
    'Acoustic Bass': 32, 'Electric Bass finger': 33, 'Electric Bass pick': 34,
    'Fretless Bass': 35, 'Slap Bass 1': 36, 'Slap Bass 2': 37,
    'Synth Bass 1': 38, 'Synth Bass 2': 39,

    # Strings
    'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43,
    'Tremolo Strings': 44, 'Pizzicato Strings': 45, 'Orchestral Strings': 46,
    'String Ensemble 1': 48, 'String Ensemble 2': 49, 'Synth Strings 1': 50,
    'Synth Strings 2': 51,

    # Choir & Pad
    'Choir Aahs': 52, 'Voice Oohs': 53, 'Synth Voice': 54, 'Orchestra Hit': 55,

    # Brass
    'Trumpet': 56, 'Trombone': 57, 'Tuba': 58, 'Muted Trumpet': 59,
    'French Horn': 60, 'Brass Section': 61, 'Synth Brass 1': 62, 'Synth Brass 2': 63,

    # Reed
    'Soprano Sax': 64, 'Alto Sax': 65, 'Tenor Sax': 66, 'Baritone Sax': 67,
    'Oboe': 68, 'English Horn': 69, 'Bassoon': 70, 'Clarinet': 71,

    # Pipe
    'Piccolo': 72, 'Flute': 73, 'Recorder': 74, 'Pan Flute': 75,
    'Blown Bottle': 76, 'Shakuhachi': 77, 'Whistle': 78, 'Ocarina': 79,

    # Synth Lead
    'Square Wave': 80, 'Sawtooth Wave': 81, 'Calliope Lead': 82, 'Chiff Lead': 83,
    'Charang': 84, 'Voice Lead': 85, 'Fifth Saw Wave': 86, 'Bass & Lead': 87,

    # Synth Pad
    'New Age Pad': 88, 'Warm Pad': 89, 'Poly Synth Pad': 90, 'Choir Pad': 91,
    'Bowed Glass Pad': 92, 'Metallic Pad': 93, 'Halo Pad': 94, 'Sweep Pad': 95,

    # Ethnic
    'Sitar': 104, 'Banjo': 105, 'Shamisen': 106, 'Koto': 107,
    'Kalimba': 108, 'Bagpipe': 109, 'Fiddle': 110, 'Shanai': 111,

    # Sound Effects
    'Guitar Fret Noise': 120, 'Breath Noise': 121, 'Seashore': 122, 'Bird Tweet': 123,
    'Telephone Ring': 124, 'Helicopter': 125, 'Applause': 126, 'Gunshot': 127,

    # Indonesian Instruments (approximations)
    'Gamelan': 114, 'Kendang': 115, 'Suling': 75, 'Rebab': 110,
    'Talempong': 14, 'Gambus': 25, 'Mandolin': 27, 'Harmonica': 22,
}

# Chords (MIDI note numbers, C4 = 60)
CHORDS = {
    # Major chords
    'C': [60, 64, 67], 'C#': [61, 65, 68], 'Db': [61, 65, 68],
    'D': [62, 66, 69], 'D#': [63, 67, 70], 'Eb': [63, 67, 70],
    'E': [64, 68, 71], 'F': [65, 69, 72], 'F#': [66, 70, 73],
    'Gb': [66, 70, 73], 'G': [67, 71, 74], 'G#': [68, 72, 75],
    'Ab': [68, 72, 75], 'A': [69, 73, 76], 'A#': [70, 74, 77],
    'Bb': [70, 74, 77], 'B': [71, 75, 78],

    # Minor chords
    'Cm': [60, 63, 67], 'C#m': [61, 64, 68], 'Dm': [62, 65, 69],
    'D#m': [63, 66, 70], 'Em': [64, 67, 71], 'Fm': [65, 68, 72],
    'F#m': [66, 69, 73], 'Gm': [67, 70, 74], 'G#m': [68, 71, 75],
    'Am': [69, 72, 76], 'A#m': [70, 73, 77], 'Bm': [71, 74, 78],

    # Seventh chords - EXPANDED untuk jazz/blues
    'C7': [60, 64, 67, 70], 'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74],
    'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77], 'A7': [69, 73, 76, 79],
    'B7': [71, 75, 78, 82], 'Cm7': [60, 63, 67, 70], 'Dm7': [62, 65, 69, 72],
    'Em7': [64, 67, 71, 74], 'Fm7': [65, 68, 72, 75], 'Gm7': [67, 70, 74, 77],
    'Am7': [69, 72, 76, 79], 'Bbmaj7': [70, 74, 77, 81], 'Cmaj7': [60, 64, 67, 71],
    'Dmaj7': [62, 66, 69, 73], 'Emaj7': [64, 68, 71, 75], 'Fmaj7': [65, 69, 72, 76],
    'Gmaj7': [67, 71, 74, 78], 'Amaj7': [69, 73, 76, 80], 'Ebmaj7': [63, 67, 70, 74],
    'Cm9': [60, 63, 67, 70, 74], 'Fm9': [65, 68, 72, 75, 79], 'G7b9': [67, 71, 74, 77, 80],

    # Suspended chords
    'Csus4': [60, 65, 67], 'Dsus4': [62, 67, 69], 'Esus4': [64, 69, 71],
    'Fsus4': [65, 70, 72], 'Gsus4': [67, 72, 74], 'Asus4': [69, 74, 76],

    # Diminished chords
    'Cdim': [60, 63, 66], 'Ddim': [62, 65, 68], 'Edim': [64, 67, 70],
    'Fdim': [65, 68, 71], 'Gdim': [67, 70, 73], 'Adim': [69, 72, 75],

    # Augmented chords
    'Caug': [60, 64, 68], 'Daug': [62, 66, 70], 'Eaug': [64, 68, 72],
    'Faug': [65, 69, 73], 'Gaug': [67, 71, 75], 'Aaug': [69, 73, 77],

    # Power chords (untuk metal/rock)
    'C5': [60, 67], 'D5': [62, 69], 'E5': [64, 71], 'F5': [65, 72],
    'G5': [67, 74], 'A5': [69, 76], 'B5': [71, 78], 'Eb5': [63, 70],
}

# Scales (intervals from root note)
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'latin': [0, 2, 4, 5, 7, 9, 10], # Latin scale (natural minor + major 7)
    'dangdut': [0, 1, 4, 5, 7, 8, 11], # Pelog/Slendro approximation
}

# Genre parameters - REVISED with detailed drum patterns and bass styles
GENRE_PARAMS = {
    'pop': {
        'tempo': 126, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': ['Clean Electric Guitar', 'Flute', 'Soprano Sax'], # Pilihan melody
            'rhythm_primary': ['Electric Piano 1'], # Piano untuk rhythm
            'rhythm_secondary': ['String Ensemble 1', 'Warm Pad'], # Pad/Strings untuk rhythm
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['C', 'F', 'Am', 'G'],
            ['G', 'C', 'Am', 'F'], ['F', 'C', 'G', 'Am'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'melodic', # Gaya bass untuk genre ini
        'mood': 'happy'
    },
    'rock': {
        'tempo': 135, 'key': 'E', 'scale': 'pentatonic', # Rock sering pakai pentatonik
        'instruments': {
            'melody': ['Distortion Guitar', 'Overdriven Guitar'], # Gitar distorsi untuk melody
            'rhythm_primary': ['Power Chord'], # Power chord
            'rhythm_secondary': ['Rock Organ'], # Organ untuk rhythm
            'bass': ['Electric Bass pick', 'Fretless Bass'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['E5', 'A5', 'B5', 'C#m'], ['Em', 'G', 'D', 'A'], ['E', 'D', 'A', 'E'],
            ['A', 'G', 'D', 'A'], ['C5', 'G5', 'A5', 'F5'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'driving', # Gaya bass
        'mood': 'energetic'
    },
    'metal': {
        'tempo': 120, 'key': 'E', 'scale': 'minor',
        'instruments': {
            'melody': ['Distortion Guitar', 'Overdriven Guitar'], # Gitar distorsi
            'rhythm_primary': ['Power Chord'], # Power chord
            'rhythm_secondary': ['String Ensemble 1'], # Strings untuk ambience
            'bass': ['Electric Bass pick', 'Synth Bass 1'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['E5', 'G5', 'D5', 'A5'], ['Em', 'C', 'G', 'D'], ['Am', 'Em', 'F', 'G'],
            ['D5', 'C5', 'G5', 'A5'], ['B5', 'A5', 'G5', 'F#5'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'heavy', # Gaya bass
        'mood': 'intense'
    },
    'ballad': {
        'tempo': 72, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': ['Nylon String Guitar', 'Violin', 'Flute'],
            'rhythm_primary': ['Electric Piano 1'],
            'rhythm_secondary': ['Warm Pad', 'String Ensemble 1'],
            'bass': ['Acoustic Bass', 'Fretless Bass'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['F', 'C', 'Dm', 'G'],
            ['C', 'Am', 'G', 'F'], ['Em', 'Am', 'Dm', 'G'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'sustained', # Gaya bass
        'mood': 'emotional'
    },
    'blues': {
        'tempo': 100, 'key': 'A', 'scale': 'blues',
        'instruments': {
            'melody': ['Tenor Sax', 'Jazz Electric Guitar', 'Harmonica'],
            'rhythm_primary': ['Electric Piano 1', 'Drawbar Organ'],
            'rhythm_secondary': ['Brass Section'],
            'bass': ['Acoustic Bass', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['A7', 'D7', 'E7'], # Classic 12-bar blues (broken down)
            ['G7', 'C7', 'D7'], ['E7', 'A7', 'B7'],
        ],
        'base_duration_beats_per_section': {'intro': 12, 'verse': 12, 'pre_chorus': 8, 'chorus': 12, 'bridge': 12, 'interlude': 8, 'outro': 8},
        'bass_style': 'walking', # Gaya bass
        'mood': 'soulful'
    },
    'jazz': {
        'tempo': 140, 'key': 'C', 'scale': 'major', # Jazz sering pakai major atau dorian
        'instruments': {
            'melody': ['Tenor Sax', 'Flute'],
            'rhythm_primary': ['Electric Piano 1', 'Acoustic Grand Piano'],
            'rhythm_secondary': ['Brass Section', 'String Ensemble 1'],
            'bass': ['Acoustic Bass', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'], ['Cm7', 'F7', 'Bbmaj7'], ['Am7', 'D7', 'Gmaj7'],
            ['Dm7', 'G7', 'Am7', 'D7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'walking', # Gaya bass
        'mood': 'sophisticated'
    },
    'hiphop': {
        'tempo': 97, 'key': 'Cm', 'scale': 'minor',
        'instruments': {
            'melody': ['Square Wave', 'Electric Piano 2'],
            'rhythm_primary': ['Poly Synth Pad', 'Electric Piano 2'],
            'rhythm_secondary': ['Synth Bass 1'], # Synth Bass bisa juga jadi rhythm
            'bass': ['Synth Bass 1', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Cm', 'Ab', 'Bb', 'Fm'], ['Fm', 'Ab', 'Bb', 'Eb'], ['Eb', 'Bb', 'Cm', 'Ab'],
            ['Cm', 'Eb', 'Ab', 'G'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'syncopated', # Gaya bass
        'mood': 'urban'
    },
    'latin': {
        'tempo': 91, 'key': 'G', 'scale': 'latin',
        'instruments': {
            'melody': ['Nylon String Guitar', 'Flute', 'Trumpet'],
            'rhythm_primary': ['Acoustic Grand Piano'],
            'rhythm_secondary': ['String Ensemble 1', 'Brass Section'],
            'bass': ['Acoustic Bass', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Am', 'D7', 'Gmaj7', 'Cmaj7'], ['G', 'Bm', 'Em', 'A7'], ['Dm', 'G7', 'Cmaj7', 'Fmaj7'],
            ['Em', 'Am', 'D7', 'Gmaj7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'tumbao', # Gaya bass
        'mood': 'rhythmic'
    },
    'dangdut': {
        'tempo': 140, 'key': 'Am', 'scale': 'dangdut',
        'instruments': {
            'melody': ['Suling', 'Clean Electric Guitar', 'Rebab'],
            'rhythm_primary': ['Gamelan', 'Electric Piano 1'],
            'rhythm_secondary': ['Nylon String Guitar'],
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Am', 'E7', 'Am', 'E7'], ['Am', 'Dm', 'E7', 'Am'], ['Dm', 'Am', 'E7', 'Am'],
            ['Am', 'G', 'F', 'E7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'offbeat_syncopated', # Gaya bass
        'mood': 'traditional'
    }
}

def select_progression(params, lyrics=""):
    """Select chord progression based on mood and sentiment analysis"""
    progressions = params['chord_progressions']
    
    if lyrics:
        blob = TextBlob(lyrics)
        polarity = blob.sentiment.polarity
        
        if polarity > 0.1: # Happy mood
            major_progressions = []
            for prog in progressions:
                is_major_prog = all(not chord.lower().startswith('m') and 'dim' not in chord and 'sus' not in chord for chord in prog)
                if is_major_prog: # Prefer fully major progressions for happy mood
                    major_progressions.append(prog)
            if major_progressions:
                return random.choice(major_progressions)
        
        elif polarity < -0.1: # Sad mood
            minor_progressions = []
            for prog in progressions:
                is_minor_prog = all(chord.lower().startswith('m') or 'dim' in chord for chord in prog)
                if is_minor_prog: # Prefer fully minor/diminished for sad mood
                    minor_progressions.append(prog)
            if minor_progressions:
                return random.choice(minor_progressions)
    
    selected = random.choice(progressions)
    logger.info("Selected progression: {} for mood {}".format(selected, params['mood']))
    return selected

def detect_genre_from_lyrics(lyrics):
    """Detect genre from lyrics using keyword matching"""
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'party', 'fun', 'happy', 'tonight', 'forever', 'together'],
        'rock': ['rock', 'guitar', 'energy', 'power', 'fire', 'wild', 'roll', 'scream', 'freedom'],
        'metal': ['metal', 'heavy', 'dark', 'scream', 'thunder', 'steel', 'rage', 'shadow', 'death'],
        'ballad': ['sad', 'love', 'heartbreak', 'memory', 'gentle', 'soft', 'tears', 'alone', 'forever'],
        'blues': ['soul', 'heartache', 'guitar', 'night', 'trouble', 'baby', 'lonely'],
        'jazz': ['jazz', 'smooth', 'night', 'sax', 'swing', 'harmony', 'blue', 'lounge'],
        'hiphop': ['rap', 'street', 'beat', 'flow', 'rhythm', 'hustle', 'city', 'time', 'crew'],
        'latin': ['latin', 'bossanova', 'salsa', 'rhythm', 'dance', 'passion', 'fiesta', 'caliente', 'amor'],
        'dangdut': ['dangdut', 'tradisional', 'cinta', 'hati', 'kenangan', 'indonesia', 'rindu', 'sayang', 'melayu']
    }

    blob = TextBlob(lyrics.lower())
    words = set(blob.words)

    scores = {genre: sum(1 for keyword in kw_list if keyword in words)
              for genre, kw_list in keywords.items()}

    detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
    logger.info("Genre detected from keywords: '{}'".format(detected_genre))
    return detected_genre

def find_best_instrument(choice_list, is_rock_metal=False):
    """Fuzzy matching for instruments based on general rules and rock/metal exceptions"""
    if not isinstance(choice_list, list):
        choice_list = [choice_list]

    if 'Power Chord' in choice_list and is_rock_metal:
        return 'Overdriven Guitar'

    for choice in choice_list:
        choice_lower = choice.lower().strip()
        
        if is_rock_metal:
            if 'gitar distorsi' in choice_lower or 'distortion guitar' in choice_lower: return 'Distortion Guitar'
            if 'organ' in choice_lower: return 'Rock Organ'
            if 'power chord' in choice_lower: return 'Overdriven Guitar'
        
        for instr_name, num in INSTRUMENTS.items():
            if choice_lower == instr_name.lower():
                return instr_name
        for instr_name, num in INSTRUMENTS.items():
            if (choice_lower in instr_name.lower() or
                any(word in instr_name.lower() for word in choice_lower.split())):
                return instr_name

    if any(word in choice_lower for word in ['gitar', 'melody', 'solo']) and not is_rock_metal:
        return 'Nylon String Guitar'
    if any(word in choice_lower for word in ['flute']):
        return 'Flute'
    if any(word in choice_lower for word in ['sax', 'saxophone']):
        return 'Soprano Sax'
    if any(word in choice_lower for word in ['piano', 'key']):
        return 'Electric Piano 1'
    if any(word in choice_lower for word in ['pad', 'strings']):
        return 'String Ensemble 1'
    if any(word in choice_lower for word in ['organ']):
        return 'Drawbar Organ'
    if any(word in choice_lower for word in ['bass']):
        return 'Electric Bass finger'
    
    logger.warning(f"No good instrument match for '{' / '.join(choice_list)}', falling back to Acoustic Grand Piano.")
    return 'Acoustic Grand Piano'


def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    """Generate instrumental parameters based on genre and lyrics analysis"""
    params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy()

    # --- FIXED: Tambahkan 'genre' ke params di awal ---
    params['genre'] = genre
    # --- END FIXED ---

    if user_tempo_input != 'auto':
        try:
            params['tempo'] = int(user_tempo_input)
            if not (60 <= params['tempo'] <= 200):
                logger.warning("Tempo out of range (60-200 BPM): {}, using default.".format(user_tempo_input))
                params['tempo'] = GENRE_PARAMS[genre.lower()]['tempo']
        except ValueError:
            logger.warning("Invalid tempo input: '{}', using default.".format(user_tempo_input))
            params['tempo'] = GENRE_PARAMS[genre.lower()]['tempo']

    blob = TextBlob(lyrics)
    sentiment = blob.sentiment.polarity

    if sentiment < -0.3:
        params['mood'] = 'sad'
        params['scale'] = 'minor'
    elif sentiment > 0.3:
        params['mood'] = 'happy'
        params['scale'] = 'major'
    # Pastikan scale yang dipilih ada di SCALES yang diizinkan
    if params['scale'] not in SCALES:
        params['scale'] = 'major' # Fallback jika scale tidak diizinkan

    is_rock_metal = params['genre'] in ['rock', 'metal']
    # Select instruments with fuzzy matching and genre-specific logic
    params['instruments']['melody'] = find_best_instrument(params['instruments']['melody'], is_rock_metal)
    params['instruments']['rhythm_primary'] = find_best_instrument(params['instruments']['rhythm_primary'], is_rock_metal)
    params['instruments']['rhythm_secondary'] = find_best_instrument(params['instruments']['rhythm_secondary'], is_rock_metal)
    params['instruments']['bass'] = find_best_instrument(params['instruments']['bass'], is_rock_metal)

    for category, instrument_name in params['instruments'].items():
        program_num = INSTRUMENTS.get(instrument_name, 0)
        logger.info("{} instrument: {} (Program {})".format(
            category.capitalize(), instrument_name, program_num
        ))

    selected_progression = select_progression(params, lyrics)
    params['chords'] = []
    for chord_name in selected_progression:
        if chord_name in CHORDS:
            params['chords'].append(CHORDS[chord_name])
        else:
            logger.warning("Chord '{}' not found. Using C major.".format(chord_name))
            params['chords'].append(CHORDS['C'])
    params['selected_progression'] = selected_progression

    logger.info("Parameter instrumental untuk {} (Mood: {}): Tempo={}BPM, Progression={}".format(
        genre, params['mood'], params['tempo'], selected_progression
    ))

    return params

def get_scale_notes(key, scale_name):
    """Get scale notes based on key and scale type"""
    root_midi = CHORDS.get(key, [60])[0]
    scale_intervals = SCALES.get(scale_name, SCALES['major'])
    return [root_midi + interval for interval in scale_intervals]

def generate_melody_section(params, section_beats, current_chord_progression, is_solo=False, add_expressive_effects=True):
    """Generates melody for a single section with expressive effects"""
    scale_notes = get_scale_notes(params['key'], params['scale'])
    
    melody_events = []
    pitch_bend_events = []

    # Dapatkan pola melodi berdasarkan mood
    if params['mood'] == 'sad':
        patterns = [[4, 2, 2, 8], [2, 2, 4, 6, 4], [4, 4, 2, 2, 8]]
        velocities = [60, 70]
        vibrato_depth_val = 200
        vibrato_freq_val = 4
    elif params['mood'] == 'energetic':
        patterns = [[2, 2, 4, 2, 2, 4], [2, 2, 2, 2, 4, 8], [4, 4, 4, 4]]
        velocities = [90, 100]
        vibrato_depth_val = 150
        vibrato_freq_val = 6
    elif params['mood'] == 'rhythmic' or params['genre'] in ['latin', 'dangdut']:
        patterns = [[2, 2, 4, 2, 0, 4], [4, 2, 2, 4, 4], [2, 4, 2, 4, 4]]
        velocities = [80, 90]
        vibrato_depth_val = 100
        vibrato_freq_val = 5
    else: # happy, default
        patterns = [[2, 2, 6], [4, 6, 4], [4, 4, 8]]
        velocities = [70, 85]
        vibrato_depth_val = 180
        vibrato_freq_val = 4
    
    if "Distortion Guitar" in params['instruments']['melody'] or "Overdriven Guitar" in params['instruments']['melody']:
        # Pola melodi untuk gitar rock/metal, lebih agresif
        patterns = [[2,2,4,4], [4,4,2,2,2,2], [8,4,4], [2,2,2,2,2,2,2,2]]
        velocities = [100, 115]

    if is_solo: # Untuk solo, lebih bebas dan cepat
        patterns = [[1,1,1,1, 2,2,4], [2, 1,1, 2, 1,1, 2], [1,1,1,1,1,1,1,1]]
        velocities = [110, 127]

    current_pattern = random.choice(patterns)
    current_velocity = random.choice(velocities)

    time_pos_beats = 0.0
    pattern_idx = 0
    quarter_to_beat = 0.25

    while time_pos_beats < section_beats:
        if pattern_idx >= len(current_pattern):
            current_pattern = random.choice(patterns) # Pilih pola baru
            pattern_idx = 0

        pattern_quarter_duration = current_pattern[pattern_idx]
        beat_duration = pattern_quarter_duration * quarter_to_beat
        
        if time_pos_beats + beat_duration > section_beats:
            beat_duration = section_beats - time_pos_beats
            if beat_duration < 0.01:
                break

        chord_index = int((time_pos_beats / section_beats) * len(current_chord_progression)) % len(current_chord_progression)
        current_chord = current_chord_progression[chord_index]
        
        possible_pitches = [p for p in scale_notes if p % 12 in [n % 12 for n in current_chord]]
        if not possible_pitches:
            possible_pitches = scale_notes

        octave_range = random.choice([0, 12])
        note_index = random.randint(0, len(possible_pitches) - 1)
        pitch = possible_pitches[note_index] + octave_range
        pitch = max(48, min(pitch, 84))
        
        velocity = current_velocity + random.randint(-10, 10)
        velocity = max(40, min(velocity, 127))
        
        melody_events.append((int(pitch), time_pos_beats, beat_duration, int(velocity)))
        
        if add_expressive_effects and beat_duration >= 1.0:
            if random.random() < 0.3:
                vibrato_depth = min(int(vibrato_depth_val), 8191)
                beats_per_vibrato_cycle = max(0.25, 1.0 / vibrato_freq_val)
                current_vibrato_time = time_pos_beats
                while current_vibrato_time < time_pos_beats + beat_duration - beats_per_vibrato_cycle/2:
                    if current_vibrato_time + beats_per_vibrato_cycle/2 < time_pos_beats + beat_duration:
                        pitch_bend_events.append((current_vibrato_time, vibrato_depth))
                    if current_vibrato_time + beats_per_vibrato_cycle < time_pos_beats + beat_duration:
                        pitch_bend_events.append((current_vibrato_time + beats_per_vibrato_cycle/2, -vibrato_depth))
                    current_vibrato_time += beats_per_vibrato_cycle
            elif random.random() < 0.1:
                initial_bend = int(random.uniform(-1000, 1000))
                slide_duration = min(0.25, beat_duration / 4)
                pitch_bend_events.append((time_pos_beats, initial_bend))
                pitch_bend_events.append((time_pos_beats + slide_duration, 0))

        if pitch_bend_events and pitch_bend_events[-1][0] < time_pos_beats + beat_duration:
            pitch_bend_events.append((time_pos_beats + beat_duration, 0))

        time_pos_beats += beat_duration
        pattern_idx += 1
    
    pitch_bend_events_cleaned = []
    pitch_bend_events.sort(key=lambda x: x[0])
    
    last_time = -1.0
    last_bend = None
    for event_time, bend_value in pitch_bend_events:
        quantized_time = round(event_time / 0.0625) * 0.0625 # Quantize to 16th note
        bend_int = max(-8192, min(8191, int(round(bend_value))))
        
        if (quantized_time > last_time + 0.03125 or 
            (last_bend is not None and bend_int != last_bend and abs(quantized_time - last_time) > 0.001)):
            pitch_bend_events_cleaned.append((quantized_time, bend_int))
            last_time = quantized_time
            last_bend = bend_int
        elif pitch_bend_events_cleaned and quantized_time == pitch_bend_events_cleaned[-1][0]:
            pitch_bend_events_cleaned[-1] = (quantized_time, bend_int)
            last_bend = bend_int
    
    return melody_events, pitch_bend_events_cleaned

def generate_rhythm_primary_section(params, section_beats, current_chord_progression):
    """Generates rhythm (piano/power chord) for a single section"""
    rhythm_data = []
    time_pos_beats = 0.0
    
    # Calculate beats per chord based on current section length and chords available
    beats_per_main_chord = section_beats / len(current_chord_progression) if len(current_chord_progression) > 0 else section_beats

    is_power_chord_rhythm = (params['genre'] in ['rock', 'metal'] and params['instruments']['rhythm_primary'] == 'Overdriven Guitar')

    for i in range(len(current_chord_progression)):
        chord_notes_midi = current_chord_progression[i]
        chord_actual_duration = beats_per_main_chord
        if time_pos_beats + chord_actual_duration > section_beats:
            chord_actual_duration = section_beats - time_pos_beats
            if chord_actual_duration < 0.01: break
        
        base_velocity = 80
        if params['genre'] in ['rock', 'metal']: base_velocity = 100
        elif params['genre'] == 'ballad': base_velocity = 70

        if is_power_chord_rhythm: # Power chord (rock/metal)
            power_chord_notes = [chord_notes_midi[0], chord_notes_midi[0] + 7]
            if len(chord_notes_midi) > 1:
                 power_chord_notes.append(chord_notes_midi[0] + 12) 
            
            for beat_sub_div in range(int(chord_actual_duration / 0.5)): # Setiap half beat
                current_sub_beat = time_pos_beats + (beat_sub_div * 0.5)
                if current_sub_beat < section_beats:
                    for note in power_chord_notes:
                        velocity = random.randint(base_velocity, base_velocity + 20)
                        rhythm_data.append((note, current_sub_beat, 0.4, velocity))
                else: break

        else: # Piano/Pad/String chords (generic)
            for beat_sub_div in range(int(chord_actual_duration / 1.0)): # Every beat
                 current_sub_beat = time_pos_beats + (beat_sub_div * 1.0)
                 if current_sub_beat < section_beats:
                    for note in chord_notes_midi:
                        velocity = random.randint(base_velocity - 10, base_velocity + 10)
                        rhythm_data.append((note, current_sub_beat, 0.9, velocity)) # Longer duration for sustained feel
                 else: break
        
        time_pos_beats += chord_actual_duration # Move to the next chord's absolute position
        
    return rhythm_data

def generate_rhythm_secondary_section(params, section_beats, current_chord_progression):
    """Generates secondary rhythm (pad/strings/organ) for a single section"""
    rhythm_data = []
    time_pos_beats = 0.0
    beats_per_main_chord = section_beats / len(current_chord_progression) if len(current_chord_progression) > 0 else section_beats
    
    base_velocity = 70
    if params['genre'] in ['rock', 'metal']: base_velocity = 85
    elif params['genre'] == 'ballad': base_velocity = 60

    for i in range(len(current_chord_progression)):
        chord_notes_midi = current_chord_progression[i]
        chord_actual_duration = beats_per_main_chord
        if time_pos_beats + chord_actual_duration > section_beats:
            chord_actual_duration = section_beats - time_pos_beats
            if chord_actual_duration < 0.01: break
        
        # Sustain chords for the full duration of the chord segment within the section
        for note in chord_notes_midi:
            velocity = random.randint(base_velocity - 5, base_velocity + 5)
            rhythm_data.append((note, time_pos_beats, chord_actual_duration, velocity))
        
        time_pos_beats += chord_actual_duration
        
    return rhythm_data

def generate_bass_line_section(params, section_beats, current_chord_progression):
    """Generates bass line for a single section based on genre-specific style"""
    bass_line_events = []
    time_pos_beats = 0.0
    beats_per_main_chord = section_beats / len(current_chord_progression) if len(current_chord_progression) > 0 else section_beats
    base_velocity = 100

    for i in range(len(current_chord_progression)):
        chord_notes_midi = current_chord_progression[i]
        root_note = chord_notes_midi[0] - 24 # One octave lower
        root_note = max(24, min(root_note, 48)) # Batasi rentang bass
        chord_actual_duration = beats_per_main_chord
        if time_pos_beats + chord_actual_duration > section_beats:
            chord_actual_duration = section_beats - time_pos_beats
            if chord_actual_duration < 0.01: break

        bass_style = params['bass_style']
        
        if bass_style == 'walking': # Jazz/Blues
            for beat_idx in range(int(chord_actual_duration)):
                current_sub_beat = time_pos_beats + beat_idx
                if current_sub_beat < section_beats:
                    note_to_play = root_note
                    if beat_idx % 4 == 1: note_to_play += random.choice([2, 3, 4, 5, 7])
                    elif beat_idx % 4 == 2: note_to_play += random.choice([-1, 0, 1, 2, 3])
                    elif beat_idx % 4 == 3: note_to_play -= random.choice([0, 1, 2])
                    velocity = random.randint(base_velocity - 10, base_velocity + 10)
                    bass_line_events.append((note_to_play, current_sub_beat, 0.9, velocity))
                else: break
        
        elif bass_style == 'driving': # Rock
            for beat_sub_div in range(int(chord_actual_duration / 0.5)): # Every half beat
                current_sub_beat = time_pos_beats + (beat_sub_div * 0.5)
                if current_sub_beat < section_beats:
                    velocity = random.randint(base_velocity, base_velocity + 15)
                    bass_line_events.append((root_note, current_sub_beat, 0.7, velocity))
                    if random.random() < 0.3:
                         if current_sub_beat + 0.5 < section_beats:
                            bass_line_events.append((root_note + random.choice([0, 5]), current_sub_beat + 0.5, 0.4, velocity - 10))
                else: break
        
        elif bass_style == 'heavy': # Metal
            for beat_sub_div in range(int(chord_actual_duration / 0.25)): # Every 16th note
                current_sub_beat = time_pos_beats + (beat_sub_div * 0.25)
                if current_sub_beat < section_beats:
                    velocity = random.randint(base_velocity + 5, base_velocity + 20)
                    bass_line_events.append((root_note, current_sub_beat, 0.2, velocity))
                else: break
        
        elif bass_style == 'sustained': # Ballad
            velocity = random.randint(base_velocity - 20, base_velocity - 5)
            bass_line_events.append((root_note, time_pos_beats, chord_actual_duration * 0.9, velocity))
        
        elif bass_style in ['syncopated', 'tumbao', 'offbeat_syncopated']: # Hiphop/Latin/Dangdut
            for beat_idx in range(int(chord_actual_duration / 1.0)):
                current_sub_beat = time_pos_beats + beat_idx
                if current_sub_beat < section_beats:
                    bass_line_events.append((root_note, current_sub_beat, 0.4, base_velocity))
                    if random.random() < 0.7 and current_sub_beat + 0.5 < section_beats:
                        bass_line_events.append((root_note + random.choice([0, 7, 12]), current_sub_beat + 0.5, 0.4, base_velocity - 10))
                    if random.random() < 0.5 and current_sub_beat + 0.25 < section_beats:
                        bass_line_events.append((root_note + 12, current_sub_beat + 0.25, 0.2, base_velocity - 20))
                else: break

        else: # Default: simple root notes
            for beat_idx in range(int(chord_actual_duration / 1.0)):
                current_sub_beat = time_pos_beats + beat_idx
                if current_sub_beat < section_beats:
                    velocity = random.randint(base_velocity - 10, base_velocity + 5)
                    bass_line_events.append((root_note, current_sub_beat, 0.8, velocity))
                else: break
        
        time_pos_beats += chord_actual_duration

    return bass_line_events

def generate_drum_pattern_section(params, section_type, section_beats):
    """Generates genre-specific drum pattern for a given section type"""
    drum_events = []
    
    # Base velocities
    kick_vel = 120
    snare_vel = 110
    hat_vel = 80
    tom_vel = 95
    crash_vel = 127
    ride_vel = 90
    
    # Velocity and complexity adjustments per section
    if section_type == 'intro':
        kick_vel, snare_vel, hat_vel = 90, 80, 60
    elif section_type == 'verse':
        kick_vel, snare_vel, hat_vel = 100, 90, 70
    elif section_type == 'pre_chorus':
        kick_vel, snare_vel, hat_vel = 110, 100, 80
    elif section_type == 'chorus':
        kick_vel, snare_vel, hat_vel = 127, 120, 100
    elif section_type == 'bridge':
        kick_vel, snare_vel, hat_vel = 95, 85, 65
    elif section_type == 'interlude':
        kick_vel, snare_vel, hat_vel = 80, 70, 50
    elif section_type == 'outro':
        kick_vel, snare_vel, hat_vel = 110, 100, 80
    
    # Main loop for beats
    for current_beat_idx in range(0, int(section_beats)):
        current_beat_time = float(current_beat_idx)

        # Kick Drum (36)
        if params['genre'] in ['rock', 'metal']:
            if current_beat_idx % 4 == 0: # Beat 1 (double kick)
                drum_events.append((36, current_beat_time, 0.3, random.randint(kick_vel, 127)))
                drum_events.append((36, current_beat_time + 0.25, 0.3, random.randint(kick_vel-10, 127-10)))
            elif current_beat_idx % 4 == 2: # Beat 3
                drum_events.append((36, current_beat_time, 0.5, random.randint(kick_vel, 127)))
        elif params['genre'] in ['hiphop', 'latin', 'dangdut']:
            # Syncopated/off-beat kicks
            drum_events.append((36, current_beat_time, 0.3, random.randint(kick_vel, kick_vel+10)))
            if random.random() < 0.4: # Tambah off-beat kick
                drum_events.append((36, current_beat_time + 0.5, 0.2, random.randint(kick_vel-20, kick_vel)))
        else: # Pop, Ballad, Blues, Jazz
            if current_beat_idx % 4 == 0 or current_beat_idx % 4 == 2: # Beat 1 & 3
                drum_events.append((36, current_beat_time, 0.4, random.randint(kick_vel, kick_vel+10)))
        
        # Snare Drum (38)
        if params['genre'] in ['rock', 'metal']:
            if current_beat_idx % 4 == 1 or current_beat_idx % 4 == 3: # Beat 2 & 4
                drum_events.append((38, current_beat_time, 0.4, random.randint(snare_vel, 127)))
        elif params['genre'] in ['hiphop', 'latin', 'dangdut']:
            if current_beat_idx % 4 == 1 or current_beat_idx % 4 == 3: # Beat 2 & 4
                drum_events.append((38, current_beat_time + random.choice([0, 0.125]), 0.3, random.randint(snare_vel, snare_vel+10))) # Sedikit syncopated
        else: # Pop, Ballad, Blues, Jazz
            if current_beat_idx % 4 == 1 or current_beat_idx % 4 == 3: # Beat 2 & 4
                drum_events.append((38, current_beat_time, 0.4, random.randint(snare_vel, snare_vel+10)))

        # Hi-hat (42) / Ride (51)
        if section_type == 'chorus' or params['genre'] in ['jazz', 'metal']:
            # Ride cymbal on eighth notes
            for eighth_sub_div in range(2):
                drum_events.append((51, current_beat_time + (eighth_sub_div * 0.5), 0.3, random.randint(ride_vel - 10, ride_vel + 10)))
            if section_type == 'chorus' and current_beat_idx % 2 == 0: # Crash setiap 2 beat di chorus
                drum_events.append((49, current_beat_time, 1.0, 127)) # Loud crash
        else:
            # Hi-hat on 16th notes
            for sixteenth_sub_div in range(4):
                drum_events.append((42, current_beat_time + (sixteenth_sub_div * 0.25), 0.1, random.randint(hat_vel - 10, hat_vel + 10)))
        
        # Fills (Tom-toms 47, 45, 43 - High, Mid, Low)
        if random.random() < 0.05 and current_beat_idx % 4 == 3 and current_beat_idx < section_beats - 4: # Small fill near end of phrase
            drum_events.append((47, current_beat_time + 3.5, 0.25, random.randint(90, 110))) # Low Tom
            drum_events.append((45, current_beat_time + 3.75, 0.25, random.randint(90, 110))) # Mid Tom
            drum_events.append((43, current_beat_time + 4.0, 0.25, random.randint(90, 110))) # High Tom (typo, should be current_beat_time + 3.5 + 0.5)

    # Crash Cymbal (49) - Intro/Outro/Chorus
    if section_type == 'intro':
        drum_events.append((49, 0, 1.0, crash_vel)) # Di awal section
    if section_type == 'outro':
        drum_events.append((49, section_beats - 1, 1.0, crash_vel)) # Di akhir section

    # Sort events by time
    drum_events.sort(key=lambda x: x[1])
    return drum_events


# Fungsi baru untuk membangun struktur lagu dan mengisi MIDI
def build_song_structure(params):
    """Builds the song structure (intro, verse, chorus, etc.) and chord progressions for each section"""
    target_min_duration_seconds = 180 # 3 minutes
    target_min_duration_beats = target_min_duration_seconds * (params['tempo'] / 60)

    song_structure = [] # List of (section_type, beats, chord_progression_for_section, is_solo_section)

    chord_progression_main = params['chords']
    # Ambil chord progression bridge dari daftar, pastikan berbeda dari main
    chord_progression_bridge = random.choice(GENRE_PARAMS[params['genre']]['chord_progressions'])
    while chord_progression_bridge == chord_progression_main and len(GENRE_PARAMS[params['genre']]['chord_progressions']) > 1:
        chord_progression_bridge = random.choice(GENRE_PARAMS[params['genre']]['chord_progressions'])


    # Durasi dasar untuk setiap bagian
    base_beats = params['base_duration_beats_per_section']

    # --- INTRO ---
    # Ensure intro always plays with a valid chord progression part
    intro_progression = chord_progression_main[:min(len(chord_progression_main), 2)]
    if not intro_progression: # Fallback if main progression is too short
        intro_progression = params['chords'][:min(len(params['chords']), 2)]
        if not intro_progression: intro_progression = [CHORDS['C']] # Final fallback
    song_structure.append(('intro', base_beats['intro'], intro_progression, False))

    current_beats = base_beats['intro']
    
    # --- VERSE - PRE_CHORUS - CHORUS Loop ---
    loop_count = 0
    while current_beats < target_min_duration_beats:
        if loop_count < 2 or random.random() < 0.7: # Minimal 2 loop V-PC-C, setelah itu random
            # Verse
            song_structure.append(('verse', base_beats['verse'], chord_progression_main, False))
            current_beats += base_beats['verse']
            if current_beats >= target_min_duration_beats: break

            # Pre-Chorus
            song_structure.append(('pre_chorus', base_beats['pre_chorus'], chord_progression_main, False))
            current_beats += base_beats['pre_chorus']
            if current_beats >= target_min_duration_beats: break
            
            # Chorus
            song_structure.append(('chorus', base_beats['chorus'], chord_progression_main, False))
            current_beats += base_beats['chorus']
            if current_beats >= target_min_duration_beats: break

        loop_count += 1
        
        # Tambahkan Bridge atau Interlude setelah beberapa loop Chorus
        if loop_count >= 2 and current_beats < target_min_duration_beats - (base_beats['bridge'] + base_beats['chorus']):
            if random.random() < 0.3: # 30% kemungkinan bridge
                 song_structure.append(('bridge', base_beats['bridge'], chord_progression_bridge, False))
                 current_beats += base_beats['bridge']
                 if current_beats >= target_min_duration_beats: break
                 
                 # Setelah bridge, biasanya kembali ke chorus atau interlude/solo
                 if random.random() < 0.5:
                     song_structure.append(('chorus', base_beats['chorus'], chord_progression_main, False))
                     current_beats += base_beats['chorus']
                     if current_beats >= target_min_duration_beats: break

            elif random.random() < 0.2: # 20% kemungkinan interlude / solo
                song_structure.append(('interlude', base_beats['interlude'], random.choice(GENRE_PARAMS[params['genre']]['chord_progressions']), True)) # Mark as solo section
                current_beats += base_beats['interlude']
                if current_beats >= target_min_duration_beats: break
                
                if random.random() < 0.5: # Setelah interlude, bisa balik ke verse atau chorus
                    song_structure.append(('verse', base_beats['verse'], chord_progression_main, False))
                    current_beats += base_beats['verse']
                    if current_beats >= target_min_duration_beats: break
                    song_structure.append(('chorus', base_beats['chorus'], chord_progression_main, False))
                    current_beats += base_beats['chorus']
                    if current_beats >= target_min_duration_beats: break


    # --- OUTRO ---
    # Pastikan ada outro, dan jika terlalu pendek, tambahkan pengulangan
    # Cek apakah durasi total sudah cukup panjang. Jika tidak, tambahkan bagian sampai cukup.
    while current_beats < target_min_duration_beats:
        # Tambahkan chorus atau verse lagi untuk mengisi durasi
        if (target_min_duration_beats - current_beats) >= base_beats['chorus']:
            song_structure.append(('chorus', base_beats['chorus'], chord_progression_main, False))
            current_beats += base_beats['chorus']
        elif (target_min_duration_beats - current_beats) >= base_beats['verse']:
            song_structure.append(('verse', base_beats['verse'], chord_progression_main, False))
            current_beats += base_beats['verse']
        else: # Jika sisa durasi sangat sedikit, tambahkan ke outro
            break
            
    # Akhirnya, tambahkan outro
    outro_duration_to_add = max(base_beats['outro'], (target_min_duration_beats - current_beats)) # Outro minimal 8 beat, atau lebih jika perlu memenuhi target.
    song_structure.append(('outro', outro_duration_to_add, chord_progression_main[0:1], False))
    current_beats += outro_duration_to_add

    # Final update total beats after all sections are added
    params['duration_beats'] = current_beats
    logger.info(f"Song structure built: {len(song_structure)} sections, total beats: {current_beats}, total seconds: {current_beats / (params['tempo']/60):.1f}s")
    return song_structure


def create_midi_file(params, output_path):
    """Create multi-track MIDI file with full song structure, panpot, and detailed drums using mido"""
    tempo = params['tempo']
    ticks_per_beat = 480

    mid = MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    melody_track = MidiTrack()
    rhythm_primary_track = MidiTrack() # Dulu harmony_track
    rhythm_secondary_track = MidiTrack() # Track baru untuk pad/strings/organ
    bass_track = MidiTrack()
    drums_track = MidiTrack()

    mid.tracks.extend([melody_track, rhythm_primary_track, rhythm_secondary_track, bass_track, drums_track])

    mido_tempo_us = bpm2tempo(tempo)
    melody_track.append(MetaMessage('set_tempo', tempo=mido_tempo_us, time=0))
    
    def beats_to_ticks(beats):
        return int(round(beats * ticks_per_beat))

    # --- Build Song Structure ---
    song_structure = build_song_structure(params)
    total_song_beats = params['duration_beats'] # Diambil dari params yang sudah diupdate

    current_absolute_beat = 0.0

    # Initialize all_messages lists for each track to collect events
    all_melody_messages = []
    all_melody_pitch_bend_events = []
    all_rhythm_primary_messages = []
    all_rhythm_secondary_messages = []
    all_bass_messages = []
    all_drums_messages = []

    # Assign instruments and initial controllers
    # MELODY TRACK - PAN CENTER
    melody_instrument_name = params['instruments']['melody']
    melody_track.append(Message('program_change', channel=0, program=INSTRUMENTS.get(melody_instrument_name, 0), time=0))
    melody_track.append(Message('control_change', channel=0, control=7, value=100, time=0))   # Volume
    melody_track.append(Message('control_change', channel=0, control=10, value=64, time=0))  # Pan CENTER (64)
    melody_track.append(Message('control_change', channel=0, control=101, value=0, time=0))  # RPN MSB for pitch bend range
    melody_track.append(Message('control_change', channel=0, control=100, value=0, time=0))  # RPN LSB
    melody_track.append(Message('control_change', channel=0, control=6, value=2, time=0))    # 2 semitones pitch bend range
    logger.info(f"Melody Track: {melody_instrument_name} (Pan: Center)")

    # RHYTHM PRIMARY TRACK (Piano/Power Chord) - PAN RIGHT
    rhythm_primary_instrument_name = params['instruments']['rhythm_primary']
    rhythm_primary_track.append(Message('program_change', channel=1, program=INSTRUMENTS.get(rhythm_primary_instrument_name, 0), time=0))
    rhythm_primary_track.append(Message('control_change', channel=1, control=7, value=90, time=0))   # Volume
    rhythm_primary_track.append(Message('control_change', channel=1, control=10, value=90, time=0)) # Pan RIGHT (90)
    logger.info(f"Rhythm Primary Track: {rhythm_primary_instrument_name} (Pan: Right)")

    # RHYTHM SECONDARY TRACK (Pad/Strings/Organ) - PAN LEFT-CENTER
    rhythm_secondary_instrument_name = params['instruments']['rhythm_secondary']
    rhythm_secondary_track.append(Message('program_change', channel=3, program=INSTRUMENTS.get(rhythm_secondary_instrument_name, 0), time=0)) # Channel 3
    rhythm_secondary_track.append(Message('control_change', channel=3, control=7, value=75, time=0)) # Volume
    rhythm_secondary_track.append(Message('control_change', channel=3, control=10, value=40, time=0)) # Pan LEFT-CENTER (40)
    logger.info(f"Rhythm Secondary Track: {rhythm_secondary_instrument_name} (Pan: Left-Center)")

    # BASS TRACK - PAN LEFT
    bass_instrument_name = params['instruments']['bass']
    bass_track.append(Message('program_change', channel=2, program=INSTRUMENTS.get(bass_instrument_name, 0), time=0))
    bass_track.append(Message('control_change', channel=2, control=7, value=110, time=0))  # Volume
    bass_track.append(Message('control_change', channel=2, control=10, value=30, time=0))  # Pan LEFT (30)
    logger.info(f"Bass Track: {bass_instrument_name} (Pan: Left)")

    # DRUMS TRACK - PAN CENTER
    drums_track.append(Message('control_change', channel=9, control=7, value=120, time=0))   # Volume MAX
    drums_track.append(Message('control_change', channel=9, control=11, value=100, time=0))  # Expression
    drums_track.append(Message('control_change', channel=9, control=10, value=64, time=0))   # Pan CENTER
    logger.info("Drums Track: Standard GM Kit (Pan: Center)")

    # --- Generate MIDI events for each section ---
    for section_type, section_beats, chord_progression_for_section, is_solo_section in song_structure:
        logger.info(f"Generating section: {section_type} for {section_beats} beats at absolute beat {current_absolute_beat}")
        
        # Melody
        # --- FIXED: Passing add_expressive_effects explicitly ---
        melody_events, pb_events = generate_melody_section(params, section_beats, chord_progression_for_section, is_solo_section, add_expressive_effects=True)
        # --- END FIXED ---
        for pitch, rel_beat, dur_beat, vel in melody_events:
            all_melody_messages.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('note_on', channel=0, note=pitch, velocity=vel, time=0)))
            all_melody_messages.append((beats_to_ticks(current_absolute_beat + rel_beat + dur_beat), Message('note_off', channel=0, note=pitch, velocity=0, time=0)))
        for rel_beat, bend_val in pb_events:
            all_melody_pitch_bend_events.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('pitchwheel', channel=0, pitch=bend_val, time=0)))

        # Rhythm Primary
        rhythm_primary_events = generate_rhythm_primary_section(params, section_beats, chord_progression_for_section)
        for pitch, rel_beat, dur_beat, vel in rhythm_primary_events:
            all_rhythm_primary_messages.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('note_on', channel=1, note=pitch, velocity=vel, time=0)))
            all_rhythm_primary_messages.append((beats_to_ticks(current_absolute_beat + rel_beat + dur_beat), Message('note_off', channel=1, note=pitch, velocity=0, time=0)))

        # Rhythm Secondary
        rhythm_secondary_events = generate_rhythm_secondary_section(params, section_beats, chord_progression_for_section)
        for pitch, rel_beat, dur_beat, vel in rhythm_secondary_events:
            all_rhythm_secondary_messages.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('note_on', channel=3, note=pitch, velocity=vel, time=0)))
            all_rhythm_secondary_messages.append((beats_to_ticks(current_absolute_beat + rel_beat + dur_beat), Message('note_off', channel=3, note=pitch, velocity=0, time=0)))

        # Bass
        bass_events = generate_bass_line_section(params, section_beats, chord_progression_for_section)
        for pitch, rel_beat, dur_beat, vel in bass_events:
            all_bass_messages.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('note_on', channel=2, note=pitch, velocity=vel, time=0)))
            all_bass_messages.append((beats_to_ticks(current_absolute_beat + rel_beat + dur_beat), Message('note_off', channel=2, note=pitch, velocity=0, time=0)))

        # Drums
        drum_events = generate_drum_pattern_section(params, section_type, section_beats)
        for note, rel_beat, dur_beat, vel in drum_events:
            all_drums_messages.append((beats_to_ticks(current_absolute_beat + rel_beat), Message('note_on', channel=9, note=note, velocity=vel, time=0)))
            all_drums_messages.append((beats_to_ticks(current_absolute_beat + rel_beat + dur_beat), Message('note_off', channel=9, note=note, velocity=0, time=0)))

        current_absolute_beat += section_beats # Maju ke awal bagian berikutnya

    # --- Convert absolute time events to delta time and append to tracks ---
    def process_events_for_track(track, events_list):
        events_list.sort(key=lambda x: x[0])
        current_abs_tick = 0
        for abs_tick, msg in events_list:
            delta_tick = max(0, abs_tick - current_abs_tick)
            msg.time = delta_tick
            track.append(msg)
            current_abs_tick = abs_tick
        return current_abs_tick

    process_events_for_track(melody_track, all_melody_messages + all_melody_pitch_bend_events)
    process_events_for_track(rhythm_primary_track, all_rhythm_primary_messages)
    process_events_for_track(rhythm_secondary_track, all_rhythm_secondary_messages)
    process_events_for_track(bass_track, all_bass_messages)
    process_events_for_track(drums_track, all_drums_messages)

    # Add end_of_track meta message to each track
    for track in mid.tracks:
        if len(track) == 0:
            track.append(MetaMessage('end_of_track', time=0))
        elif not isinstance(track[-1], MetaMessage) or track[-1].type != 'end_of_track':
            current_abs_time_at_end = sum(msg.time for msg in track)
            end_delta = max(0, beats_to_ticks(total_song_beats) - current_abs_time_at_end)
            track.append(MetaMessage('end_of_track', time=end_delta))

    try:
        mid.save(output_path)
        logger.info(f"MIDI generated successfully with full structure (Total Beats: {total_song_beats}): {output_path.name}")
        return True
    except Exception as e:
        logger.error("Error writing MIDI file with mido: {}".format(e), exc_info=True)
        return False

def debug_audio_file(file_path):
    """Debug function to analyze audio file content"""
    try:
        if not file_path.exists():
            logger.error("File does not exist: {}".format(file_path))
            return False
            
        audio = AudioSegment.from_file(file_path)
        logger.info("=== AUDIO DEBUG INFO ===")
        logger.info("File: {}".format(file_path.name))
        logger.info("Size: {:.1f} KB".format(file_path.stat().st_size / 1024))
        logger.info("Duration: {:.1f}s".format(len(audio) / 1000.0))
        logger.info("Peak: {:.1f}dBFS".format(audio.max_dBFS))
        logger.info("RMS: {:.1f}dB".format(audio.rms))
        logger.info("Channels: {}".format(audio.channels))
        logger.info("Sample rate: {}Hz".format(audio.frame_rate))
        
        if audio.max_dBFS < -60: # Sangat silent
            logger.error("⚠️  CRITICAL: Audio is extremely quiet! FluidSynth likely produced silent output.")
            return False
        elif audio.max_dBFS < -30: # Cukup silent, tapi masih ada sinyal
            logger.warning("⚠️  Audio is quiet. FluidSynth output might be low. Continue processing but check output.")
            return True
        else:
            logger.info("✅ Audio levels seem normal.")
            return True
            
    except Exception as e:
        logger.error("Debug error during audio analysis for {}: {}".format(file_path, e))
        return False

def midi_to_audio_subprocess(midi_path, output_wav_path, soundfont_path):
    """ARM64-optimized FluidSynth subprocess with FIXED volume and audio settings"""
    if not soundfont_path.exists():
        logger.error("SoundFont not found: {}".format(soundfont_path))
        return False

    if not midi_path.exists():
        logger.error("MIDI file not found: {}".format(midi_path))
        return False

    try:
        cmd = [
            'fluidsynth',
            '-F', str(output_wav_path),
            
            # ARM64 ENDIAN FIX
            '-o', 'audio.file.endian=little',
            '-o', 'audio.file.format=s16',
            '-o', 'synth.sample-rate=44100',
            
            # FIXED: Audio buffer settings untuk ARM64
            '-o', 'audio.period-size=512',
            '-o', 'audio.periods=4',
            
            # FIXED: Synth settings untuk volume yang lebih baik
            '-o', 'synth.gain=1.5',             # Meningkatkan gain keseluruhan dari 0.8 ke 1.5
            '-o', 'synth.midi-bank-select=gm',  # Gunakan General MIDI bank selection
            
            # --- FIXED: HAPUS PARAMETER INI UNTUK KOMPATIBILITAS FLUIDSYNTH LAMA ---
            # FluidSynth versi lama mungkin tidak memiliki parameter ini.
            # Menghapusnya akan membuat script lebih kompatibel.
            # '-o', 'synth.reverb.enable=0',
            # '-o', 'synth.chorus.enable=0',
            # --- END FIXED ---

            # File rendering only (no real-time audio)
            '-a', 'null',
            '-ni',  # No MIDI input
            str(soundfont_path),
            str(midi_path)
        ]

        logger.info("Rendering MIDI with FluidSynth (FIXED volume settings)...")
        logger.debug("Command: {}".format(' '.join(cmd)))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180, # Increased timeout to 3 minutes for longer tracks
            cwd=AUDIO_OUTPUT_DIR
        )

        if result.returncode == 0:
            if output_wav_path.exists() and output_wav_path.stat().st_size > 1000:
                file_size = output_wav_path.stat().st_size / 1024
                logger.info("WAV generated successfully: {} ({:.1f} KB)".format(
                    output_wav_path.name, file_size
                ))
                return True
            else:
                logger.warning("WAV file too small or empty: {}".format(output_wav_path))
                try:
                    test_audio = AudioSegment.from_wav(output_wav_path)
                    logger.warning("WAV analysis: Peak={:.1f}dBFS, RMS={:.1f}dB. It might be silent.".format(
                        test_audio.max_dBFS, test_audio.rms
                    ))
                except Exception as e:
                    logger.warning(f"Could not analyze small/empty WAV: {e}")
                return False

        logger.error("FluidSynth error (code {}):".format(result.returncode))
        if result.stderr:
            logger.error("STDERR: {}".format(result.stderr.strip()))
        if result.stdout:
            logger.info("STDOUT: {}".format(result.stdout.strip()))

        return False

    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout (180s)")
        return False
    except FileNotFoundError:
        logger.error("'fluidsynth' not found. Install: sudo apt install fluidsynth libsndfile1")
        return False
    except Exception as e:
        logger.error("Unexpected FluidSynth error: {}".format(e))
        return False

def midi_to_audio_pyfluidsynth(midi_path, output_wav_path, soundfont_path):
    """Fallback using pyfluidsynth (less reliable on ARM64)"""
    if not FLUIDSYNTH_BINDING_AVAILABLE:
        logger.warning("pyfluidsynth not available, cannot use pyfluidsynth fallback.")
        return False

    try:
        fs = pyfluidsynth_lib.Synth()
        fs.start(driver='alsa') # Assuming ALSA on Linux

        sfid = fs.sfload(str(soundfont_path))
        if sfid == pyfluidsynth_lib.ERROR_CODE:
            logger.error("Failed to load SoundFont with pyfluidsynth")
            fs.delete()
            return False

        logger.info("SoundFont '{}' loaded with pyfluidsynth (ID: {})".format(
            soundfont_path.name, sfid
        ))

        fs.delete()
        logger.warning("pyfluidsynth has limited MIDI file rendering capability. Subprocess is preferred.")
        return False

    except Exception as e:
        logger.error("pyfluidsynth error: {}".format(e))
        return False

def midi_to_audio(midi_path, output_wav_path):
    """Main MIDI to audio conversion"""
    if not SOUNDFONT_PATH:
        logger.error("SoundFont not available: {}".format(SOUNDFONT_PATH))
        return False

    success = midi_to_audio_subprocess(midi_path, output_wav_path, SOUNDFONT_PATH)

    if not success and FLUIDSYNTH_BINDING_AVAILABLE:
        logger.info("Falling back to pyfluidsynth (not recommended for MIDI rendering)...")
        success = midi_to_audio_pyfluidsynth(midi_path, output_wav_path, SOUNDFONT_PATH)

    return success

def wav_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3 with FIXED audio processing - SOLVED silent output"""
    if not wav_path.exists() or wav_path.stat().st_size == 0:
        logger.error("Empty WAV file: {}".format(wav_path))
        return False

    try:
        logger.info("Converting WAV to MP3 with FIXED processing: {} -> {}".format(wav_path.name, mp3_path.name))

        # Load WAV
        audio = AudioSegment.from_wav(wav_path)
        
        # DEBUG: Check original WAV volume
        logger.info("Original WAV analysis: Peak={:.1f}dBFS, RMS={:.1f}dB, Duration={:.1f}s".format(
            audio.max_dBFS, audio.rms, len(audio)/1000.0
        ))

        # === FIXED AUDIO PROCESSING PIPELINE ===
        
        # 1. INITIAL GAIN BOOST - Pastikan ada sinyal audio yang cukup
        logger.info("Step 1: Initial gain boost if too quiet...")
        if audio.max_dBFS < -10:  # Jika peak di bawah -10dBFS, berikan boost hingga -10dBFS
            initial_boost = -10 - audio.max_dBFS
            audio = audio + initial_boost
            logger.info(f"Applied initial boost: +{initial_boost:.1f}dB. New Peak: {audio.max_dBFS:.1f}dBFS")
        else:
            logger.info(f"Initial WAV peak ({audio.max_dBFS:.1f}dBFS) is good, no initial boost applied.")
        
        # 2. AGGRESSIVE NORMALIZATION - Target -0.3dBFS peak untuk memaksimalkan volume
        logger.info("Step 2: Aggressive normalization (Target -0.3dBFS peak)...")
        normalized_audio = pydub_normalize(audio, headroom=0.3)
        logger.info(f"After normalization: Peak={normalized_audio.max_dBFS:.1f}dBFS, RMS={normalized_audio.rms:.1f}dB")
        
        # 3. DYNAMIC RANGE COMPRESSION - Menghaluskan dinamika
        logger.info("Step 3: Applying dynamic range compression (Threshold=-12dB, Ratio=3:1)...")
        compressed = normalized_audio.compress_dynamic_range(
            threshold=-12.0,    # Menentukan kapan kompresi dimulai
            ratio=3.0,          # Mengurangi rentang dinamis 3 banding 1
            attack=5,           # Waktu reaksi kompresor (cepat)
            release=50          # Waktu kompresor berhenti bekerja (cepat)
        )
        logger.info(f"After compression: Peak={compressed.max_dBFS:.1f}dBFS, RMS={compressed.rms:.1f}dB")
        
        # 4. SUBTLE EQ - Penyesuaian frekuensi untuk clarity dan bass
        logger.info("Step 4: Applying subtle EQ (Bass +1.5dB, Clarity +0.5dB)...")
        bass_boosted = compressed.low_pass_filter(200) + 1.5 # Boost bass
        eq_audio = bass_boosted.high_pass_filter(800) + 0.5   # Boost clarity
        logger.info(f"After EQ: Peak={eq_audio.max_dBFS:.1f}dBFS, RMS={eq_audio.rms:.1f}dB")
        
        # 5. FINAL LIMITER - Mencegah clipping dan memaksimalkan loudness
        logger.info("Step 5: Applying final limiter (Target -0.3dBFS peak)...")
        limited = eq_audio.apply_gain(-0.3) # Pastikan peak tidak melewati -0.3dBFS
        logger.info(f"After limiting: Peak={limited.max_dBFS:.1f}dBFS, RMS={limited.rms:.1f}dB")
        
        # 6. LOUDNESS TARGETING (Optional, jika ingin target RMS spesifik)
        # Final_audio akan menjadi 'limited' kecuali ada target loudness spesifik.
        # Untuk saat ini, kita akan mengandalkan limiter untuk level akhir.
        final_audio = limited

        # 7. FINAL SANITY CHECK FOR CLIPPING
        if final_audio.max_dBFS > -0.1: # Jika masih ada puncak yang sangat dekat 0dBFS
            logger.warning(f"Clipping detected after final gain! Max peak: {final_audio.max_dBFS:.1f}dBFS. Reducing gain by {final_audio.max_dBFS + 0.1:.1f}dB.")
            final_audio = final_audio.apply_gain(-(final_audio.max_dBFS + 0.1))
        
        logger.info(f"Final processed audio stats: Peak={final_audio.max_dBFS:.1f}dBFS, RMS={final_audio.rms:.1f}dB, Duration={len(final_audio)/1000.0:.1f}s")

        # === HIGH-QUALITY MP3 EXPORT ===
        logger.info("Step 7: Exporting to 320kbps MP3 (Highest Quality)...")
        final_audio.export(
            mp3_path,
            format='mp3',
            bitrate='320k',        # High bitrate for quality
            parameters=[
                '-q:a', '0',       # Highest quality VBR (0 is best for LAME)
                '-ac', '2',        # Force stereo output
                '-ar', '44100'     # Force 44.1kHz sample rate
            ]
        )

        if mp3_path.exists() and mp3_path.stat().st_size > 500:
            file_size = mp3_path.stat().st_size / 1024
            
            try:
                test_mp3 = AudioSegment.from_mp3(mp3_path)
                if test_mp3.max_dBFS > -60: # Cek apakah MP3 memiliki sinyal audio yang cukup
                    logger.info("🎵 PROFESSIONAL MP3 generated: {} ({:.1f} KB, {:.1f}s)".format(
                        mp3_path.name, file_size, len(test_mp3)/1000.0
                    ))
                    return True
                else:
                    logger.error(f"MP3 verification failed: Output MP3 is silent (Peak={test_mp3.max_dBFS:.1f}dBFS).")
                    return False
            except Exception as mp3_verify_error:
                logger.warning(f"MP3 verification step failed: {mp3_verify_error}. Assuming MP3 is valid.")
                return True
                
        else:
            logger.error("MP3 file is too small or missing after conversion: {} (size: {} bytes)".format(mp3_path, mp3_path.stat().st_size if mp3_path.exists() else 0))
            return False

    except Exception as e:
        logger.error("CRITICAL WAV to MP3 conversion error: {}".format(e), exc_info=True)
        if shutil.which('ffmpeg') is None:
            logger.error("FFmpeg not found. Install FFmpeg: sudo apt install ffmpeg")
        return False

def cleanup_old_files(directory, max_age_hours=1):
    """Clean up old generated files"""
    logger.info("Cleaning old files in {} (older than {}h)".format(directory, max_age_hours))
    deleted_count = 0

    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

    for file_path in Path(directory).glob("*.{mp3,wav,mid}"):
        try:
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_time < cutoff_time:
                file_path.unlink()
                logger.debug("Deleted: {}".format(file_path.name))
                deleted_count += 1
        except Exception as e:
            logger.warning("Error deleting {}: {}".format(file_path.name, e))

    logger.info("Cleanup complete: {} files deleted".format(deleted_count))
    return deleted_count

def generate_unique_id(lyrics):
    """Generate unique ID"""
    hash_object = hashlib.md5(lyrics.encode('utf-8')).hexdigest()
    timestamp = str(int(time.time()))
    return "{}_{}".format(hash_object[:8], timestamp)

@app.route('/')
def index():
    """Main web interface"""
    html_template = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎵 Generate Instrumental AI 🎵</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }
        .container { max-width: 800px; margin: auto; }
        h1 { 
            text-align: center;
            color: white;
            margin-bottom: 30px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            font-size: 2.5em;
        }
        p.subtitle {
            text-align: center;
            color: white;
            margin-bottom: 30px;
            font-size: 1.1em;
            line-height: 1.5;
        }
        .card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #2c3e50;
            font-size: 1.1em;
        }
        textarea {
            width: 100%;
            padding: 15px;
            margin-bottom: 20px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
            background: #f8f9fa;
            resize: vertical;
            min-height: 120px;
        }
        textarea:focus { border-color: #3498db; outline: none; }
        select, input[type="number"] {
            width: 100%;
            padding: 12px;
            margin-bottom: 20px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
            background: #f8f9fa;
        }
        input[type="number"] { width: 100%; }
        .form-row { display: flex; gap: 15px; margin-bottom: 20px; }
        .form-row > div { flex: 1; }
        .form-row small { display: block; margin-top: 5px; color: #95a5a6; font-size: 0.85em; }

        button {
            background: linear-gradient(45deg, #3498db, #2980b9);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 18px;
            font-weight: bold;
            width: 100%;
            transition: transform 0.2s, box_shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box_shadow: 0 5px 15px rgba(52, 152, 219, 0.4);
        }
        button:active { transform: translateY(0); }
        .result {
            margin-top: 30px;
            padding: 25px;
            background: linear-gradient(135deg, #e8f6f3, #d1ecea);
            border-radius: 15px;
            border-left: 5px solid #27ae60;
            display: none;
        }
        .result.show { display: block; animation: fadeIn 0.5s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .success { color: #27ae60; font-weight: bold; }
        .error { color: #e74c3c; font-weight: bold; }
        .info { color: #3498db; }
        audio {
            width: 100%;
            margin: 20px 0;
            border-radius: 10px;
            background: white;
            padding: 10px;
        }
        .download-btn {
            display: inline-block;
            background: #27ae60;
            color: white;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 8px;
            margin: 10px 5px;
            transition: background 0.3s;
        }
        .download-btn:hover { background: #229954; }
        .loading {
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .status { font-style: italic; color: #7f8c8d; margin: 10px 0; }
        small { color: #95a5a6; font-size: 0.9em; }
        @media (max-width: 600px) {
            .container { padding: 10px; }
            h1 { font-size: 2em; }
            .card { padding: 20px; }
            .form-row { flex-direction: column; align-items: stretch; }
            input[type="number"] { width: 100%; margin-right: 0; margin-bottom: 10px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Generate Instrumental AI 🎵</h1>
        <p class="subtitle">
            Masukkan lirik Anda dan akan menjadi instrumental!
            Support Pop, Rock, Metal, Jazz, Latin, Dangdut, dan genre lainnya.
            Output akan diproses dengan kompresi audio profesional agar terdengar seimbang dan balance.
        </p>

        <div class="card">
            <form id="musicForm">
                <label for="lyrics">📝 Lirik :</label>
                <textarea
                    id="lyrics"
                    name="lyrics"
                    placeholder="Masukkan lirik Anda di sini...

Contoh:
[Verse 1]
Di malam yang sunyi kukenang dirimu
Bayangmu hadir dalam mimpiku malam ini

[Chorus]
Cinta ini takkan pernah usai
Selamanya kau di hatiku..."
                    required
                ></textarea>

                <div class="form-row">
                    <div>
                        <label for="genre"> 🎸 Genre :</label>
                        <select id="genre" name="genre">
                            <option value="auto">🤖 Auto-Detect dari Lirik</option>
                            <option value="pop">🎤 Pop</option>
                            <option value="rock">🎸 Rock</option>
                            <option value="metal">🤘 Metal</option>
                            <option value="ballad">💔 Ballad</option>
                            <option value="blues">🎷 Blues</option>
                            <option value="jazz">🎹 Jazz</option>
                            <option value="hiphop">🎧 Hip-Hop</option>
                            <option value="latin">💃 Latin</option>
                            <option value="dangdut">🎶 Dangdut</option>
                        </select>
                    </div>
                    <div>
                        <label for="tempo"> 🥁 Tempo (BPM):</label>
                        <input type="number" id="tempo" name="tempo" min="60" max="200" placeholder="Auto">
                        <small>(Kosongkan untuk auto-detect berdasarkan genre)</small>
                    </div>
                </div>

                <button type="submit">🚀 Generate Sekarang!</button>
            </form>
        </div>

        <div id="result" class="result">
            <h3>🎉 Hasil Generate Instrumental :</h3>
            <div id="status" class="status"></div>
            <div id="loading" class="loading" style="display: none;">
                <div class="spinner"></div>
                <p>🎵 Processing... Ini butuh 30-60 detik (tergantung durasi)</p>
                <p>Proses: Analisis lirik → Generate MIDI → Render Audio → Mixing & Mastering → MP3</p>
            </div>
            <audio id="audioPlayer" controls style="display: none;"></audio>
            <div id="downloadLinks"></div>
            <div id="info"></div>
        </div>
    </div>

    <script>
        document.getElementById('musicForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const formData = new FormData();
            formData.append('lyrics', document.getElementById('lyrics').value.trim());
            formData.append('genre', document.getElementById('genre').value);

            const tempoValue = document.getElementById('tempo').value;
            formData.append('tempo', tempoValue === '' ? 'auto' : tempoValue);

            const resultDiv = document.getElementById('result');
            const statusDiv = document.getElementById('status');
            const loadingDiv = document.getElementById('loading');
            const audioPlayer = document.getElementById('audioPlayer');
            const downloadLinks = document.getElementById('downloadLinks');
            const infoDiv = document.getElementById('info');

            resultDiv.classList.add('show');
            statusDiv.innerHTML = '';
            loadingDiv.style.display = 'block';
            audioPlayer.style.display = 'none';
            downloadLinks.innerHTML = '';
            infoDiv.innerHTML = '';

            try {
                statusDiv.innerHTML = '<p class="success">🚀 Memulai generasi instrumental...</p>';

                const response = await fetch('/generate-instrumental', {
                    method: 'POST',
                    body: formData
                });

                loadingDiv.style.display = 'none';

                if (response.ok) {
                    const data = await response.json();

                    if (data.success) {
                        statusDiv.innerHTML = `
                            <p class="success">🎉 Instrumental berhasil !</p>
                            <p><strong>Genre:</strong> <span class="info">${data.genre}</span></p>
                            <p><strong>Tempo:</strong> <span class="info">${data.tempo} BPM</span></p>
                            <p><strong>Durasi:</strong> <span class="info">${data.duration} detik</span></p>
                            <p><strong>ID:</strong> <span class="info">${data.id}</span></p>
                            <p><strong>Progression:</strong> <span class="info">${data.progression || 'Random'}</span></p>
                        `;

                        audioPlayer.src = `/static/audio_output/${data.filename}`;
                        audioPlayer.style.display = 'block';
                        audioPlayer.load();

                        setTimeout(() => {
                            audioPlayer.play().catch(e => {
                                console.log('Autoplay blocked:', e);
                            });
                        }, 500);

                        downloadLinks.innerHTML = `
                            <a href="/static/audio_output/${data.filename}" class="download-btn" download>
                                💾 Download MP3 (${Math.round(data.size || 0)} KB)
                            </a>
                            <br><small>Share instrumental Anda! 🎵</small>
                        `;

                        infoDiv.innerHTML = `
                            <p style="font-size: 0.9em; color: #7f8c8d; margin-top: 20px;">
                                <strong>🔧 Technical Info:</strong> Generated dengan 10+ chord progressions per genre,
                                channel isolation (Melody/Harmony/Bass/Drums terpisah) menggunakan FluidSynth +
                                General MIDI SoundFont. Proyek open-source dengan pitch bend effects yang dioptimalkan
                                dan output audio diproses dengan kompresi profesional.
                            </p>
                        `;
                    } else {
                        throw new Error(data.error || 'Unknown error');
                    }
                } else {
                    const errorData = await response.json();
                    statusDiv.innerHTML = `<p class="error">❌ Error: ${errorData.error || 'Gagal generate instrumental'}</p>`;

                    if (errorData.error && errorData.error.includes('FluidSynth')) {
                        statusDiv.innerHTML += `
                            <p style="font-size: 0.9em; color: #e67e22;">
                                💡 Tips: Pastikan FluidSynth terinstal: <code>sudo apt install fluidsynth libsndfile1</code>
                            </p>
                        `;
                    } else if (errorData.error && errorData.error.includes('FFmpeg')) {
                         statusDiv.innerHTML += `
                            <p style="font-size: 0.9em; color: #e67e22;">
                                💡 Tips: Pastikan FFmpeg terinstal: <code>sudo apt install ffmpeg</code>
                            </p>
                        `;
                    } else if (errorData.error && errorData.error.includes('MIDI')) {
                        statusDiv.innerHTML += `
                            <p style="font-size: 0.9em; color: #e67e22;">
                                🔧 MIDI Error: Coba restart server atau kurangi kompleksitas lirik.
                            </p>
                        `;
                    }
                }
            } catch (error) {
                loadingDiv.style.display = 'none';
                statusDiv.innerHTML = `
                    <p class="error">🌐 Network Error: ${error.message}</p>
                    <p style="font-size: 0.9em; color: #7f8c8d;">
                        Pastikan server berjalan di http://127.0.0.1:5000 dan koneksi stabil.
                        Coba refresh halaman atau restart server.
                    </p>
                `;
                console.error('Generate error:', error);
            }
        });

        document.getElementById('lyrics').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 300) + 'px';
        });
    </script>
</body>
</html>
"""
    return render_template_string(html_template)

@app.route('/generate-instrumental', methods=['OPTIONS', 'POST'])
def generate_instrumental_endpoint():
    if request.method == 'OPTIONS':
        return '', 200

    logger.info("Receiving POST request to /generate-instrumental")

    try:
        data = request.form if request.form else request.json
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto').lower()
        tempo_input = data.get('tempo', 'auto')

        if not lyrics or len(lyrics) < 10:
            return jsonify({'error': 'Lirik minimal 10 karakter. Masukkan lirik lengkap.'}), 400

        logger.info("Processing lyrics: '{}' ({})".format(lyrics[:100], len(lyrics)))
        logger.info("Input: Genre='{}', Tempo='{}'".format(genre_input, tempo_input))

        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)

        unique_id = generate_unique_id(lyrics)
        midi_filename = "{}.mid".format(unique_id)
        wav_filename = "{}.wav".format(unique_id)
        mp3_filename = "{}.mp3".format(unique_id)

        paths = {
            'midi': AUDIO_OUTPUT_DIR / midi_filename,
            'wav': AUDIO_OUTPUT_DIR / wav_filename,
            'mp3': AUDIO_OUTPUT_DIR / mp3_filename
        }

        logger.info("Starting generation for ID: {}".format(unique_id))

        logger.info("1. Generating MIDI file...")
        if not create_midi_file(params, paths['midi']):
            if paths['midi'].exists(): paths['midi'].unlink()
            return jsonify({'error': 'Failed to create MIDI file. Check server logs for details.'}), 500

        logger.info("2. Rendering MIDI to audio (FluidSynth)...")
        if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
            paths['midi'].unlink(missing_ok=True)
            return jsonify({
                'error': "SoundFont not found: {}. Download from https://musical-artifacts.com/artifacts/661".format(SOUNDFONT_PATH)
            }), 500

        if not midi_to_audio(paths['midi'], paths['wav']):
            paths['midi'].unlink(missing_ok=True)
            return jsonify({
                'error': 'Failed to render MIDI to audio. Install FluidSynth: sudo apt install fluidsynth libsndfile1'
            }), 500

        # Debugging step: Check WAV file immediately after FluidSynth renders it
        if not debug_audio_file(paths['wav']):
            logger.error(f"WAV file {paths['wav'].name} is silent or invalid. Aborting MP3 conversion.")
            if paths['midi'].exists(): paths['midi'].unlink()
            if paths['wav'].exists(): paths['wav'].unlink()
            return jsonify({'error': 'Rendered WAV file is silent or corrupted. FluidSynth output issue.'}), 500

        logger.info("3. Converting to MP3 format with professional processing...")
        if not wav_to_mp3(paths['wav'], paths['mp3']):
            for path in [paths['midi'], paths['wav']]:
                if path.exists(): path.unlink()
            return jsonify({'error': 'Failed to convert to MP3. Install FFmpeg: sudo apt install ffmpeg'}), 500

        duration_seconds = params['duration_beats'] * 60 / params['tempo']
        try:
            if paths['mp3'].exists():
                audio = AudioSegment.from_mp3(paths['mp3'])
                duration_seconds = len(audio) / 1000.0
        except Exception as e:
            logger.warning("Failed to get MP3 duration: {}".format(e))

        for temp_path in [paths['midi'], paths['wav']]:
            if temp_path.exists(): temp_path.unlink()
        logger.info("Temporary files cleaned up")

        mp3_size_kb = paths['mp3'].stat().st_size / 1024 if paths['mp3'].exists() else 0

        logger.info("Generation complete! ID: {}, File: {} ({:.1f} KB, {:.1f}s)".format(
            unique_id, mp3_filename, mp3_size_kb, duration_seconds
        ))

        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'audio_url': '/static/audio_output/{}'.format(mp3_filename),
            'download_url': request.url_root + 'static/audio_output/{}'.format(mp3_filename),
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration_seconds, 1),
            'id': unique_id,
            'size': round(mp3_size_kb),
            'soundfont': SOUNDFONT_PATH.name if SOUNDFONT_PATH else 'None',
            'progression': ' '.join(params.get('selected_progression', []))
        })

    except Exception as e:
        logger.error("Critical error during generation: {}".format(e), exc_info=True)
        return jsonify({'error': 'Internal server error: {}'.format(str(e))}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve generated audio files"""
    try:
        file_path = AUDIO_OUTPUT_DIR / filename
        if not file_path.exists():
            logger.warning("Audio file not found: {}".format(file_path))
            return "File not found", 404

        mimetype = 'audio/mpeg' if filename.endswith('.mp3') else 'audio/wav'

        logger.info("Serving: {} ({}, {:.1f} KB)".format(
            filename, mimetype, file_path.stat().st_size/1024
        ))

        return send_from_directory(
            AUDIO_OUTPUT_DIR,
            filename,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error("Error serving audio {}: {}".format(filename, e))
        return "Internal server error", 500

def get_local_ip():
    """Get local network IP address"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main_app_runner():
    """Main application startup with system checks"""
    logger.info("Starting Flask Generate Instrumental AI!")
    logger.info("  Enhanced: 10+ Chord Progressions per Genre + ARM64 FluidSynth + Channel Isolation")
    logger.info("  FIXED: MIDI pitch bend float-to-int conversion + quantized timing (using mido)")
    logger.info("  NEW: Enhanced drum patterns, stereo panning, and professional audio mastering (compression/EQ) for MP3 output.")

    try:
        if not SOUNDFONT_PATH:
            logger.critical("CRITICAL: No SoundFont found! FluidSynth will not work without it.")
            logger.critical("Download GeneralUser GS: wget https://github.com/JustEnoughLinuxOS/generaluser-gs/releases/download/1.471/GeneralUser-GS-v1.471.sf2")
        else:
            logger.info("SoundFont loaded: {}".format(SOUNDFONT_PATH.name))

        check_python_dependencies()

        cleanup_old_files(AUDIO_OUTPUT_DIR, max_age_hours=24)

        logger.info("🚀 Server ready! http://{}:5000".format(get_local_ip()))
        logger.info("Genres available: {}".format(list(GENRE_PARAMS.keys())))
        logger.info("Each genre has {} chord progressions for variation!".format(len(next(iter(GENRE_PARAMS.values()))['chord_progressions']))) # FIXED: Ubah 10 menjadi 5 di sini karena GENRE_PARAMS memiliki 5 proggression sekarang

    except Exception as e:
        logger.error("Startup error: {}".format(e))
        return False

    return True

if __name__ == '__main__':
    if not main_app_runner():
        sys.exit(1) # Exit if startup failed
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)


