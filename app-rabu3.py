import os
import sys
import time
import random
import logging
import hashlib
import shutil
import math
import operator
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

# Konfigurasi logging dengan level yang lebih detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout) 
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
    'latin': [0, 2, 4, 5, 7, 9, 10],
    'dangdut': [0, 1, 4, 5, 7, 8, 11],
}

# Standard GM Drum Notes (channel 9)
DRUM_NOTES = {
    'kick': 36, 'snare': 38, 'hat_closed': 42, 'ride': 51, 'crash': 49,
    'tom_high': 47, 'tom_mid': 45, 'tom_low': 43,
}

# Genre parameters - OPTIMIZED untuk performa
GENRE_PARAMS = {
    'pop': {
        'tempo': 126, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Clean Electric Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Electric Bass finger',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['C', 'F', 'Am', 'G'],
            ['G', 'C', 'Am', 'F'], ['F', 'C', 'G', 'Am'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'melodic', 'mood': 'happy'
    },
    'rock': {
        'tempo': 135, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Electric Bass pick',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['E', 'D', 'A', 'E'], ['A', 'G', 'D', 'A'], ['Em', 'G', 'D', 'A'],
            ['E5', 'A5', 'B5', 'E5'], ['C5', 'G5', 'A5', 'F5'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'driving', 'mood': 'energetic'
    },
    'metal': {
        'tempo': 120, 'key': 'E', 'scale': 'minor',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Electric Bass pick',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['E5', 'G5', 'D5', 'A5'], ['Em', 'C', 'G', 'D'], ['Am', 'Em', 'F', 'G'],
            ['D5', 'C5', 'G5', 'A5'], ['B5', 'A5', 'G5', 'F#5'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'heavy', 'mood': 'intense'
    },
    'ballad': {
        'tempo': 72, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Warm Pad',
            'bass': 'Acoustic Bass',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['F', 'C', 'Dm', 'G'],
            ['C', 'Am', 'G', 'F'], ['Em', 'Am', 'Dm', 'G'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'sustained', 'mood': 'emotional'
    },
    'blues': {
        'tempo': 100, 'key': 'A', 'scale': 'blues',
        'instruments': {
            'melody': 'Tenor Sax',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Brass Section',
            'bass': 'Acoustic Bass',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['A7', 'D7', 'E7'], ['G7', 'C7', 'D7'], ['E7', 'A7', 'B7'],
        ],
        'base_duration_beats_per_section': {'intro': 12, 'verse': 12, 'pre_chorus': 8, 'chorus': 12, 'bridge': 12, 'interlude': 8, 'outro': 8},
        'bass_style': 'walking', 'mood': 'soulful'
    },
    'jazz': {
        'tempo': 140, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Tenor Sax',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Brass Section',
            'bass': 'Acoustic Bass',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'], ['Cm7', 'F7', 'Bbmaj7'], ['Am7', 'D7', 'Gmaj7'],
            ['Dm7', 'G7', 'Am7', 'D7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'walking', 'mood': 'sophisticated'
    },
    'hiphop': {
        'tempo': 97, 'key': 'Cm', 'scale': 'minor',
        'instruments': {
            'melody': 'Electric Piano 2',
            'rhythm_primary': 'Poly Synth Pad',
            'rhythm_secondary': 'Synth Bass 1',
            'bass': 'Synth Bass 1',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Cm', 'Ab', 'Bb', 'Fm'], ['Fm', 'Ab', 'Bb', 'Eb'], ['Eb', 'Bb', 'Cm', 'Ab'],
            ['Cm', 'Eb', 'Ab', 'G'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'syncopated', 'mood': 'urban'
    },
    'latin': {
        'tempo': 91, 'key': 'G', 'scale': 'latin',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Acoustic Bass',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Am', 'D7', 'Gmaj7', 'Cmaj7'], ['G', 'Bm', 'Em', 'A7'], ['Dm', 'G7', 'Cmaj7', 'Fmaj7'],
            ['Em', 'Am', 'D7', 'Gmaj7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'tumbao', 'mood': 'rhythmic'
    },
    'dangdut': {
        'tempo': 140, 'key': 'Am', 'scale': 'dangdut',
        'instruments': {
            'melody': 'Suling',
            'rhythm_primary': 'Gamelan',
            'rhythm_secondary': 'Clean Electric Guitar',
            'bass': 'Electric Bass finger',
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['Am', 'E7', 'Am', 'E7'], ['Am', 'Dm', 'E7', 'Am'], ['Dm', 'Am', 'E7', 'Am'],
            ['Am', 'G', 'F', 'E7'],
        ],
        'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8},
        'bass_style': 'offbeat_syncopated', 'mood': 'traditional'
    }
}

def chord_names_to_midi_notes(chord_names, key='C'):
    """Convert list of chord names to MIDI note numbers - FIXED"""
    if not isinstance(chord_names, list):
        logger.error(f"chord_names is not a list: {type(chord_names)}")
        return [CHORDS['C']]
    
    midi_chords = []
    for i, chord_name in enumerate(chord_names):
        if isinstance(chord_name, str) and chord_name in CHORDS:
            midi_chords.append(CHORDS[chord_name])
        elif isinstance(chord_name, list) and all(isinstance(n, int) for n in chord_name):
            # Already MIDI notes, validate range
            valid_chord = [max(0, min(127, int(n))) for n in chord_name]
            midi_chords.append(valid_chord)
        else:
            logger.warning(f"Chord {i} '{chord_name}' not found in CHORDS. Using C major as fallback.")
            midi_chords.append(CHORDS['C'])
    
    return midi_chords

def select_progression(params, lyrics=""):
    """Select chord progression based on mood and sentiment analysis - OPTIMIZED"""
    progressions = params['chord_progressions']
    
    if lyrics and len(lyrics.strip()) > 0:
        try:
            blob = TextBlob(lyrics)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.1: # Happy mood
                major_progressions = [prog for prog in progressions 
                                    if all(not c.lower().startswith('m') and 'dim' not in c and 'sus' not in c 
                                         for c in prog)]
                if major_progressions:
                    return random.choice(major_progressions)
            
            elif polarity < -0.1: # Sad mood
                minor_progressions = [prog for prog in progressions 
                                    if all(c.lower().startswith('m') or 'dim' in c for c in prog)]
                if minor_progressions:
                    return random.choice(minor_progressions)
        except Exception as e:
            logger.warning(f"Sentiment analysis error: {e}")
    
    selected = random.choice(progressions)
    logger.info("Selected progression: {} for mood {}".format(selected, params['mood']))
    return selected

def detect_genre_from_lyrics(lyrics):
    """Detect genre from lyrics using keyword matching - OPTIMIZED"""
    if not lyrics or len(lyrics.strip()) == 0:
        return 'pop'
    
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

    try:
        blob = TextBlob(lyrics.lower())
        words = set(blob.words)

        scores = {genre: sum(1 for keyword in kw_list if keyword in words)
                  for genre, kw_list in keywords.items()}

        detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
        logger.info("Genre detected from keywords: '{}'".format(detected_genre))
        return detected_genre
    except Exception as e:
        logger.warning(f"Genre detection error: {e}")
        return 'pop'

def find_best_instrument(choice, is_rock_metal=False):
    """Fuzzy matching for instruments - SIMPLIFIED untuk performa"""
    if not choice:
        return 'Acoustic Grand Piano'
    
    if isinstance(choice, list):
        choice = choice[0]  # Ambil yang pertama
    
    choice_lower = str(choice).lower().strip()
    
    if is_rock_metal and 'power chord' in choice_lower:
        return 'Overdriven Guitar'
    
    for instr_name, num in INSTRUMENTS.items():
        if choice_lower in instr_name.lower():
            return instr_name
    
    logger.warning(f"No good instrument match for '{choice}', falling back to Acoustic Grand Piano.")
    return 'Acoustic Grand Piano'

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    """Generate instrumental parameters - OPTIMIZED dengan error handling"""
    try:
        params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy()
        params['genre'] = genre

        # Handle tempo input
        if user_tempo_input != 'auto':
            try:
                tempo_val = int(user_tempo_input)
                if 60 <= tempo_val <= 200:
                    params['tempo'] = tempo_val
                else:
                    logger.warning("Tempo out of range (60-200 BPM): {}, using default.".format(user_tempo_input))
            except ValueError:
                logger.warning("Invalid tempo input: '{}', using default.".format(user_tempo_input))

        # Sentiment analysis
        if lyrics and len(lyrics.strip()) > 0:
            try:
                blob = TextBlob(lyrics)
                sentiment = blob.sentiment.polarity

                if sentiment < -0.3:
                    params['mood'] = 'sad'
                    params['scale'] = 'minor'
                elif sentiment > 0.3:
                    params['mood'] = 'happy'
                    params['scale'] = 'major'
            except Exception as e:
                logger.warning(f"Sentiment analysis error: {e}")
        
        # Ensure valid scale
        if params['scale'] not in SCALES:
            params['scale'] = 'major'

        # Select instruments
        is_rock_metal = params['genre'] in ['rock', 'metal']
        for category in ['melody', 'rhythm_primary', 'rhythm_secondary', 'bass']:
            params['instruments'][category] = find_best_instrument(
                params['instruments'][category], is_rock_metal
            )

        # Log instruments
        for category, instrument_name in params['instruments'].items():
            program_num = INSTRUMENTS.get(instrument_name, 0)
            logger.info("{} instrument: {} (Program {})".format(
                category.capitalize(), instrument_name, program_num
            ))

        # FIXED: Convert chord names to MIDI notes IMMEDIATELY
        selected_progression_names = select_progression(params, lyrics)
        params['chords'] = chord_names_to_midi_notes(selected_progression_names)
        params['selected_progression'] = selected_progression_names

        logger.info("Parameter instrumental untuk {} (Mood: {}): Tempo={}BPM, Progression={}".format(
            genre, params['mood'], params['tempo'], selected_progression_names
        ))

        return params

    except Exception as e:
        logger.error(f"Error in get_music_params_from_lyrics: {e}")
        # Fallback to default pop parameters
        default_params = GENRE_PARAMS['pop'].copy()
        default_params['chords'] = [CHORDS['C']]
        default_params['selected_progression'] = ['C']
        return default_params

def get_scale_notes(key, scale_name):
    """Get scale notes based on key and scale type - FIXED"""
    try:
        if key not in CHORDS:
            key = 'C'
        root_midi = CHORDS[key][0]
        scale_intervals = SCALES.get(scale_name, SCALES['major'])
        return [root_midi + interval for interval in scale_intervals]
    except Exception as e:
        logger.error(f"Error in get_scale_notes: {e}")
        return [60, 62, 64, 65, 67, 69, 71]  # C major scale

def generate_melody_section(params, section_beats, current_chord_progression, is_solo=False, add_expressive_effects=True):
    """Generates melody for a single section - FULLY FIXED"""
    try:
        scale_notes = get_scale_notes(params['key'], params['scale'])
        melody_events = []
        pitch_bend_events = []

        # FIXED: Validate and convert chord progression to MIDI notes if needed
        if not isinstance(current_chord_progression, list) or len(current_chord_progression) == 0:
            logger.warning("Invalid chord progression for melody, using C major")
            current_chord_progression = [CHORDS['C']]

        # Ensure all chords are lists of integers
        validated_chords = []
        for i, chord in enumerate(current_chord_progression):
            if isinstance(chord, str) and chord in CHORDS:
                # Convert string chord name to MIDI notes
                validated_chords.append(CHORDS[chord])
                logger.debug(f"Converted string chord '{chord}' to MIDI notes")
            elif isinstance(chord, list) and len(chord) > 0:
                # Validate existing MIDI notes
                valid_notes = []
                for note in chord:
                    if isinstance(note, (int, float)):
                        valid_notes.append(max(0, min(127, int(round(note)))))
                    else:
                        logger.warning(f"Invalid note {note} in chord {i}, using 60")
                        valid_notes.append(60)
                validated_chords.append(valid_notes)
            else:
                logger.warning(f"Chord {i} is invalid: {chord}, using C major")
                validated_chords.append(CHORDS['C'])

        current_chord_progression = validated_chords

        # Melody patterns based on mood - SIMPLIFIED untuk performa
        if params['mood'] == 'sad':
            patterns = [[4, 2, 2, 8], [2, 2, 4, 6, 4]]
            velocities = [60, 70]
        elif params['mood'] == 'energetic':
            patterns = [[2, 2, 4, 2, 2, 4], [2, 2, 2, 2, 4, 8]]
            velocities = [90, 100]
        elif params['genre'] in ['latin', 'dangdut']:
            patterns = [[2, 2, 4, 2, 4], [4, 2, 2, 4, 4]]
            velocities = [80, 90]
        else:  # happy, default
            patterns = [[2, 2, 6], [4, 6, 4], [4, 4, 8]]
            velocities = [70, 85]

        # Guitar-specific patterns
        if "Guitar" in params['instruments']['melody']:
            patterns = [[2, 2, 4, 4], [4, 4, 2, 2], [8, 4, 4]]
            velocities = [100, 115]

        if is_solo:
            patterns = [[1, 1, 1, 1, 2, 2, 4], [2, 1, 1, 2, 1, 1, 2]]
            velocities = [110, 127]

        current_pattern = random.choice(patterns)
        current_velocity = random.choice(velocities)

        time_pos_beats = 0.0
        pattern_idx = 0
        quarter_to_beat = 0.25
        max_notes = int(section_beats * 4)  # Limit notes untuk performa
        note_count = 0

        while time_pos_beats < section_beats and note_count < max_notes:
            if pattern_idx >= len(current_pattern):
                current_pattern = random.choice(patterns)
                pattern_idx = 0

            pattern_quarter_duration = current_pattern[pattern_idx]
            beat_duration = pattern_quarter_duration * quarter_to_beat
            
            if time_pos_beats + beat_duration > section_beats:
                beat_duration = section_beats - time_pos_beats
                if beat_duration < 0.01:
                    break

            # FIXED: Safe chord selection
            chord_index = 0
            if len(current_chord_progression) > 0:
                chord_index = min(int((time_pos_beats / section_beats) * len(current_chord_progression)), 
                                len(current_chord_progression) - 1)
                current_chord = current_chord_progression[chord_index]
            else:
                current_chord = CHORDS['C']

            # FIXED: Safe pitch calculation using operator.mod
            try:
                chord_root_classes = [operator.mod(int(note), 12) for note in current_chord]
                possible_pitches = [p for p in scale_notes if operator.mod(int(p), 12) in chord_root_classes]
            except Exception as e:
                logger.error(f"Error calculating pitches: {e}")
                possible_pitches = scale_notes

            if not possible_pitches:
                possible_pitches = scale_notes

            # Generate note
            octave_range = random.choice([0, 12])
            note_index = random.randint(0, len(possible_pitches) - 1)
            pitch = possible_pitches[note_index] + octave_range
            pitch = max(48, min(pitch, 84))
            
            velocity = current_velocity + random.randint(-10, 10)
            velocity = max(40, min(velocity, 127))
            
            melody_events.append((int(pitch), time_pos_beats, beat_duration, int(velocity)))
            note_count += 1

            # Simplified expressive effects untuk performa
            if add_expressive_effects and beat_duration >= 1.0 and random.random() < 0.2:
                # Simple vibrato
                vibrato_time = time_pos_beats + beat_duration * 0.3
                if vibrato_time < time_pos_beats + beat_duration:
                    pitch_bend_events.append((vibrato_time, 500))
                    pitch_bend_events.append((vibrato_time + 0.1, -500))

            time_pos_beats += beat_duration
            pattern_idx += 1

        # Simplified pitch bend cleanup
        if pitch_bend_events:
            pitch_bend_events.sort(key=lambda x: x[0])
            pitch_bend_events_cleaned = []
            last_time = -1.0
            for event_time, bend_value in pitch_bend_events:
                quantized_time = round(event_time / 0.0625) * 0.0625
                bend_int = max(-8192, min(8191, int(round(bend_value))))
                
                if quantized_time > last_time + 0.03125:
                    pitch_bend_events_cleaned.append((quantized_time, bend_int))
                    last_time = quantized_time
            
            pitch_bend_events = pitch_bend_events_cleaned

        logger.debug(f"Generated {len(melody_events)} melody events for {section_beats} beats")
        return melody_events, pitch_bend_events

    except Exception as e:
        logger.error(f"Critical error in generate_melody_section: {e}", exc_info=True)
        return [], []

# [Fungsi lainnya tetap sama seperti sebelumnya, tapi dengan validasi yang lebih ketat]

def generate_rhythm_primary_section(params, section_beats, current_chord_progression):
    """Generates rhythm - OPTIMIZED dengan validasi"""
    try:
        rhythm_data = []
        time_pos_beats = 0.0
        
        # Validate chord progression
        if not isinstance(current_chord_progression, list) or len(current_chord_progression) == 0:
            current_chord_progression = [CHORDS['C']]
        
        # Convert string chords to MIDI if needed
        validated_chords = []
        for chord in current_chord_progression:
            if isinstance(chord, str) and chord in CHORDS:
                validated_chords.append(CHORDS[chord])
            elif isinstance(chord, list):
                validated_chords.append([max(0, min(127, int(n))) for n in chord])
            else:
                validated_chords.append(CHORDS['C'])
        
        current_chord_progression = validated_chords
        beats_per_chord = section_beats / len(current_chord_progression) if len(current_chord_progression) > 0 else section_beats

        base_velocity = 80
        if params['genre'] in ['rock', 'metal']:
            base_velocity = 100
        elif params['genre'] == 'ballad':
            base_velocity = 70

        is_power_chord = params['genre'] in ['rock', 'metal']

        for i in range(len(current_chord_progression)):
            chord_notes = current_chord_progression[i]
            chord_duration = min(beats_per_chord, section_beats - time_pos_beats)
            if chord_duration < 0.5:
                break

            if is_power_chord and len(chord_notes) > 0:
                # Power chord: root + fifth
                root = chord_notes[0]
                power_notes = [root, root + 7]
                if len(chord_notes) > 2:
                    power_notes.append(root + 12)
                
                # Generate power chord pattern
                for beat_offset in range(0, int(chord_duration), 1):
                    beat_time = time_pos_beats + beat_offset
                    if beat_time >= section_beats:
                        break
                    for note in power_notes:
                        safe_note = max(36, min(84, int(note)))
                        velocity = random.randint(base_velocity, base_velocity + 20)
                        rhythm_data.append((safe_note, beat_time, 0.8, velocity))
            else:
                # Standard chord
                for beat_offset in range(0, int(chord_duration), 2):
                    beat_time = time_pos_beats + beat_offset
                    if beat_time >= section_beats:
                        break
                    for note in chord_notes:
                        safe_note = max(36, min(84, int(note)))
                        velocity = random.randint(base_velocity - 10, base_velocity + 10)
                        rhythm_data.append((safe_note, beat_time, 1.5, velocity))

            time_pos_beats += chord_duration

        return rhythm_data[:int(section_beats * 2)]  # Limit events untuk performa

    except Exception as e:
        logger.error(f"Error in generate_rhythm_primary_section: {e}")
        return []

def generate_rhythm_secondary_section(params, section_beats, current_chord_progression):
    """Generates secondary rhythm - SIMPLIFIED"""
    try:
        rhythm_data = []
        time_pos_beats = 0.0
        
        # Quick validation
        if not isinstance(current_chord_progression, list):
            current_chord_progression = [CHORDS['C']]
        
        beats_per_chord = section_beats / max(1, len(current_chord_progression))
        base_velocity = 70

        for i in range(min(4, len(current_chord_progression))):  # Limit to 4 chords max
            chord_duration = min(beats_per_chord, section_beats - time_pos_beats)
            if chord_duration < 1.0:
                break

            chord_notes = current_chord_progression[i] if i < len(current_chord_progression) else CHORDS['C']
            if not isinstance(chord_notes, list):
                chord_notes = CHORDS['C']

            # Simple sustained chords
            for note in chord_notes[:3]:  # Max 3 notes per chord
                safe_note = max(48, min(72, int(note)))
                velocity = random.randint(base_velocity - 5, base_velocity + 5)
                rhythm_data.append((safe_note, time_pos_beats, chord_duration, velocity))

            time_pos_beats += chord_duration

        return rhythm_data

    except Exception as e:
        logger.error(f"Error in generate_rhythm_secondary_section: {e}")
        return []

def generate_bass_line_section(params, section_beats, current_chord_progression):
    """Generates bass line - OPTIMIZED"""
    try:
        bass_events = []
        time_pos_beats = 0.0
        
        if not isinstance(current_chord_progression, list):
            current_chord_progression = [CHORDS['C']]
        
        beats_per_chord = section_beats / max(1, len(current_chord_progression))
        base_velocity = 100

        bass_style = params.get('bass_style', 'melodic')

        for i in range(len(current_chord_progression)):
            chord_notes = current_chord_progression[i] if i < len(current_chord_progression) else CHORDS['C']
            if not isinstance(chord_notes, list) or len(chord_notes) == 0:
                chord_notes = CHORDS['C']
            
            root_note = max(24, min(48, int(chord_notes[0]) - 24))  # Bass range
            chord_duration = min(beats_per_chord, section_beats - time_pos_beats)
            if chord_duration < 0.5:
                break

            if bass_style in ['walking', 'syncopated']:
                # Walking bass pattern
                for beat_offset in range(0, int(chord_duration), 1):
                    beat_time = time_pos_beats + beat_offset
                    if beat_time >= section_beats:
                        break
                    
                    note = root_note
                    if beat_offset % 2 == 1:  # Off-beat
                        note += random.choice([0, 2, 5, 7])
                    
                    safe_note = max(24, min(60, int(note)))
                    velocity = random.randint(base_velocity - 10, base_velocity + 10)
                    bass_events.append((safe_note, beat_time, 0.8, velocity))
            else:
                # Simple root notes
                for beat_offset in range(0, int(chord_duration), 2):
                    beat_time = time_pos_beats + beat_offset
                    if beat_time >= section_beats:
                        break
                    
                    safe_note = root_note
                    velocity = random.randint(base_velocity - 10, base_velocity + 5)
                    bass_events.append((safe_note, beat_time, 1.5, velocity))

            time_pos_beats += chord_duration

        return bass_events[:int(section_beats * 1.5)]  # Limit events

    except Exception as e:
        logger.error(f"Error in generate_bass_line_section: {e}")
        return []

def generate_drum_pattern_section(params, section_type, section_beats):
    """Generates drum pattern - OPTIMIZED untuk performa"""
    try:
        drum_events = []
        
        # Simplified drum velocities
        kick_vel = min(127, 100 + (20 if section_type in ['chorus', 'outro'] else 0))
        snare_vel = min(127, 90 + (20 if section_type in ['chorus'] else 0))
        hat_vel = 70

        # Basic drum pattern
        for beat_idx in range(0, int(section_beats)):
            beat_time = float(beat_idx)

            # Kick on beats 1 and 3
            if beat_idx % 4 in [0, 2]:
                drum_events.append((DRUM_NOTES['kick'], beat_time, 0.4, random.randint(kick_vel - 10, kick_vel)))

            # Snare on beats 2 and 4
            if beat_idx % 4 in [1, 3]:
                drum_events.append((DRUM_NOTES['snare'], beat_time, 0.4, random.randint(snare_vel - 10, snare_vel)))

            # Hi-hat on eighth notes
            for eighth in [0, 0.5]:
                hat_time = beat_time + eighth
                if hat_time < section_beats:
                    drum_events.append((DRUM_NOTES['hat_closed'], hat_time, 0.2, random.randint(hat_vel - 10, hat_vel)))

            # Occasional fills
            if beat_idx % 8 == 7 and beat_idx < section_beats - 2:  # End of phrase
                fill_time = beat_time + 0.5
                if fill_time < section_beats:
                    drum_events.append((DRUM_NOTES['tom_mid'], fill_time, 0.3, 90))

        # Add crash cymbals for transitions
        if section_type in ['intro', 'chorus', 'outro']:
            if section_type == 'intro' and section_beats > 0:
                drum_events.append((DRUM_NOTES['crash'], 0, 1.0, 127))
            if section_type == 'outro' and section_beats > 1:
                drum_events.append((DRUM_NOTES['crash'], section_beats - 1, 1.0, 127))

        drum_events.sort(key=lambda x: x[1])
        return drum_events[:int(section_beats * 8)]  # Limit drum events

    except Exception as e:
        logger.error(f"Error in generate_drum_pattern_section: {e}")
        return []

def build_song_structure(params):
    """Builds song structure - SIMPLIFIED untuk performa"""
    try:
        target_beats = 240  # Reduced from 432 untuk performa (4 minutes at 120 BPM)
        
        # Simplified structure: Intro -> Verse -> Chorus -> Verse -> Chorus -> Bridge -> Chorus -> Outro
        structure = [
            ('intro', 8, params['chords'][:2] if len(params['chords']) >= 2 else [CHORDS['C']]),
            ('verse', 16, params['chords']),
            ('pre_chorus', 8, params['chords'][-2:]),
            ('chorus', 16, params['chords']),
            ('verse', 16, params['chords']),
            ('pre_chorus', 8, params['chords'][-2:]),
            ('chorus', 16, params['chords']),
            ('bridge', 16, params['chords'][1:3] if len(params['chords']) >= 3 else params['chords']),
            ('chorus', 16, params['chords']),
            ('outro', 8, [params['chords'][-1]] if params['chords'] else [CHORDS['C']])
        ]

        total_beats = sum(section[1] for section in structure)
        if total_beats < target_beats:
            # Add extra chorus if needed
            structure.insert(-2, ('chorus', 16, params['chords']))
            total_beats += 16

        # Ensure all sections have valid chord progressions
        final_structure = []
        for section_type, beats, chords in structure:
            if not isinstance(chords, list) or len(chords) == 0:
                chords = [CHORDS['C']]
            final_structure.append((section_type, beats, chords, section_type == 'bridge'))

        params['duration_beats'] = total_beats
        logger.info(f"Song structure built: {len(final_structure)} sections, total beats: {total_beats}, total seconds: {total_beats * 60 / params['tempo']:.1f}s")
        return final_structure

    except Exception as e:
        logger.error(f"Error in build_song_structure: {e}")
        # Fallback simple structure
        return [('verse', 64, [CHORDS['C']]), ('chorus', 64, [CHORDS['G']]), ('outro', 32, [CHORDS['C']])]

def create_midi_file(params, output_path):
    """Create MIDI file - OPTIMIZED dengan timeout dan error handling"""
    try:
        start_time = time.time()
        tempo = params['tempo']
        ticks_per_beat = 480

        mid = MidiFile(type=1, ticks_per_beat=ticks_per_beat)
        
        # Create tracks
        tracks = {
            'melody': MidiTrack(),
            'rhythm_primary': MidiTrack(),
            'rhythm_secondary': MidiTrack(),
            'bass': MidiTrack(),
            'drums': MidiTrack()
        }
        
        mid.tracks.extend([tracks['melody'], tracks['rhythm_primary'], tracks['rhythm_secondary'], 
                          tracks['bass'], tracks['drums']])

        # Set tempo
        mido_tempo_us = bpm2tempo(tempo)
        tracks['melody'].append(MetaMessage('set_tempo', tempo=mido_tempo_us, time=0))

        def beats_to_ticks(beats):
            return int(round(beats * ticks_per_beat))

        # Setup instruments and controllers - SIMPLIFIED
        # Melody (Channel 0)
        prog = INSTRUMENTS.get(params['instruments']['melody'], 0)
        tracks['melody'].append(Message('program_change', channel=0, program=prog, time=0))
        tracks['melody'].append(Message('control_change', channel=0, control=7, value=100, time=0))  # Volume
        tracks['melody'].append(Message('control_change', channel=0, control=10, value=64, time=0))  # Pan center
        logger.info(f"Melody Track: {params['instruments']['melody']} (Pan: Center)")

        # Rhythm Primary (Channel 1)
        prog = INSTRUMENTS.get(params['instruments']['rhythm_primary'], 0)
        tracks['rhythm_primary'].append(Message('program_change', channel=1, program=prog, time=0))
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=7, value=90, time=0))
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=10, value=90, time=0))  # Pan right
        logger.info(f"Rhythm Primary Track: {params['instruments']['rhythm_primary']} (Pan: Right)")

        # Rhythm Secondary (Channel 2)
        prog = INSTRUMENTS.get(params['instruments']['rhythm_secondary'], 0)
        tracks['rhythm_secondary'].append(Message('program_change', channel=2, program=prog, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=7, value=75, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=10, value=40, time=0))  # Pan left-center
        logger.info(f"Rhythm Secondary Track: {params['instruments']['rhythm_secondary']} (Pan: Left-Center)")

        # Bass (Channel 3)
        prog = INSTRUMENTS.get(params['instruments']['bass'], 0)
        tracks['bass'].append(Message('program_change', channel=3, program=prog, time=0))
        tracks['bass'].append(Message('control_change', channel=3, control=7, value=110, time=0))
        tracks['bass'].append(Message('control_change', channel=3, control=10, value=30, time=0))  # Pan left
        logger.info(f"Bass Track: {params['instruments']['bass']} (Pan: Left)")

        # Drums (Channel 9)
        tracks['drums'].append(Message('control_change', channel=9, control=7, value=120, time=0))
        tracks['drums'].append(Message('control_change', channel=9, control=10, value=64, time=0))  # Pan center
        logger.info("Drums Track: Standard GM Kit (Pan: Center)")

        # Build song structure
        song_structure = build_song_structure(params)
        current_absolute_beat = 0.0

        # Event collections
        all_events = {
            'melody': [],
            'rhythm_primary': [],
            'rhythm_secondary': [],
            'bass': [],
            'drums': [],
            'pitch_bend': []
        }

        # Generate events for each section - WITH TIMEOUT CHECK
        section_start_time = time.time()
        for section_idx, (section_type, section_beats, chord_progression, is_solo) in enumerate(song_structure):
            if time.time() - section_start_time > 30:  # 30 second timeout per section
                logger.warning(f"Section {section_idx} timeout, skipping")
                break

            logger.info(f"Generating section: {section_type} for {section_beats} beats at beat {current_absolute_beat:.1f}")

            try:
                # Melody
                melody_events, pb_events = generate_melody_section(
                    params, section_beats, chord_progression, is_solo
                )
                for pitch, rel_beat, dur, vel in melody_events:
                    time_on = current_absolute_beat + rel_beat
                    time_off = time_on + dur
                    all_events['melody'].append((beats_to_ticks(time_on), 
                                               Message('note_on', channel=0, note=int(pitch), velocity=int(vel), time=0)))
                    all_events['melody'].append((beats_to_ticks(time_off), 
                                               Message('note_off', channel=0, note=int(pitch), velocity=0, time=0)))
                
                for rel_beat, bend_val in pb_events:
                    all_events['pitch_bend'].append((beats_to_ticks(current_absolute_beat + rel_beat),
                                                   Message('pitchwheel', channel=0, pitch=int(bend_val), time=0)))

                # Rhythm Primary
                rhythm_events = generate_rhythm_primary_section(params, section_beats, chord_progression)
                for pitch, rel_beat, dur, vel in rhythm_events:
                    time_on = current_absolute_beat + rel_beat
                    time_off = time_on + dur
                    all_events['rhythm_primary'].append((beats_to_ticks(time_on),
                                                       Message('note_on', channel=1, note=int(pitch), velocity=int(vel), time=0)))
                    all_events['rhythm_primary'].append((beats_to_ticks(time_off),
                                                       Message('note_off', channel=1, note=int(pitch), velocity=0, time=0)))

                # Rhythm Secondary
                secondary_events = generate_rhythm_secondary_section(params, section_beats, chord_progression)
                for pitch, rel_beat, dur, vel in secondary_events:
                    time_on = current_absolute_beat + rel_beat
                    time_off = time_on + dur
                    all_events['rhythm_secondary'].append((beats_to_ticks(time_on),
                                                         Message('note_on', channel=2, note=int(pitch), velocity=int(vel), time=0)))
                    all_events['rhythm_secondary'].append((beats_to_ticks(time_off),
                                                         Message('note_off', channel=2, note=int(pitch), velocity=0, time=0)))

                # Bass
                bass_events = generate_bass_line_section(params, section_beats, chord_progression)
                for pitch, rel_beat, dur, vel in bass_events:
                    time_on = current_absolute_beat + rel_beat
                    time_off = time_on + dur
                    all_events['bass'].append((beats_to_ticks(time_on),
                                             Message('note_on', channel=3, note=int(pitch), velocity=int(vel), time=0)))
                    all_events['bass'].append((beats_to_ticks(time_off),
                                             Message('note_off', channel=3, note=int(pitch), velocity=0, time=0)))

                # Drums
                drum_events = generate_drum_pattern_section(params, section_type, section_beats)
                for note, rel_beat, dur, vel in drum_events:
                    time_on = current_absolute_beat + rel_beat
                    time_off = time_on + dur
                    all_events['drums'].append((beats_to_ticks(time_on),
                                              Message('note_on', channel=9, note=int(note), velocity=int(vel), time=0)))
                    all_events['drums'].append((beats_to_ticks(time_off),
                                              Message('note_off', channel=9, note=int(note), velocity=0, time=0)))

                current_absolute_beat += section_beats

            except Exception as e:
                logger.error(f"Error generating section {section_type}: {e}")
                continue

        # Process events for each track
        def process_track_events(track, events, channel):
            if not events:
                return
            events.sort(key=lambda x: x[0])
            current_tick = 0
            for abs_tick, msg in events:
                delta_tick = max(0, int(abs_tick - current_tick))
                msg.time = delta_tick
                track.append(msg)
                current_tick = abs_tick

        # Add events to tracks
        process_track_events(tracks['melody'], all_events['melody'] + all_events['pitch_bend'], 0)
        process_track_events(tracks['rhythm_primary'], all_events['rhythm_primary'], 1)
        process_track_events(tracks['rhythm_secondary'], all_events['rhythm_secondary'], 2)
        process_track_events(tracks['bass'], all_events['bass'], 3)
        process_track_events(tracks['drums'], all_events['drums'], 9)

        # Add end of track
        total_ticks = beats_to_ticks(current_absolute_beat)
        for track in mid.tracks:
            if len(track) == 0 or not isinstance(track[-1], MetaMessage):
                end_delta = max(0, total_ticks - sum(msg.time for msg in track))
                track.append(MetaMessage('end_of_track', time=end_delta))

        # Save MIDI
        mid.save(output_path)
        generation_time = time.time() - start_time
        logger.info(f"MIDI generated successfully in {generation_time:.1f}s (Total Beats: {current_absolute_beat}): {output_path.name}")
        return True

    except Exception as e:
        logger.error(f"Critical error in create_midi_file: {e}", exc_info=True)
        return False

# [Fungsi audio processing tetap sama seperti sebelumnya]

def midi_to_audio_subprocess(midi_path, output_wav_path, soundfont_path):
    """ARM64-optimized FluidSynth - WITH TIMEOUT"""
    if not soundfont_path.exists() or not midi_path.exists():
        return False

    try:
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-o', 'audio.file.endian=little',
            '-o', 'audio.file.format=s16',
            '-o', 'synth.sample-rate=44100',
            '-o', 'audio.period-size=512',
            '-o', 'audio.periods=4',
            '-o', 'synth.gain=1.2',  # Reduced gain untuk stabilitas
            '-o', 'synth.midi-bank-select=gm',
            '-a', 'null', '-ni',
            str(soundfont_path), str(midi_path)
        ]

        logger.info("Rendering MIDI with FluidSynth...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # 2 minute timeout

        if result.returncode == 0 and output_wav_path.exists() and output_wav_path.stat().st_size > 1000:
            logger.info(f"WAV generated: {output_wav_path.name} ({output_wav_path.stat().st_size/1024:.1f} KB)")
            return True
        else:
            logger.error(f"FluidSynth failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout (120s)")
        return False
    except Exception as e:
        logger.error(f"FluidSynth error: {e}")
        return False

def midi_to_audio(midi_path, output_wav_path):
    """Main MIDI to audio conversion"""
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False

    return midi_to_audio_subprocess(midi_path, output_wav_path, SOUNDFONT_PATH)

def wav_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3 - SIMPLIFIED untuk performa"""
    try:
        if not wav_path.exists() or wav_path.stat().st_size == 0:
            return False

        audio = AudioSegment.from_wav(wav_path)
        
        # Simple processing
        if audio.max_dBFS < -20:
            audio = audio + 20  # Boost if too quiet
        
        # Normalize
        normalized = pydub_normalize(audio, headroom=1.0)
        
        # Export
        normalized.export(mp3_path, format='mp3', bitrate='192k')
        
        if mp3_path.exists() and mp3_path.stat().st_size > 500:
            logger.info(f"MP3 created: {mp3_path.name} ({mp3_path.stat().st_size/1024:.1f} KB)")
            return True
        else:
            return False

    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

def cleanup_old_files(directory, max_age_hours=24):
    """Clean up old files"""
    try:
        logger.info(f"Cleaning old files in {directory}")
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted = 0

        for file_path in Path(directory).glob("*.{mp3,wav,mid}"):
            try:
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                    file_path.unlink()
                    deleted += 1
            except:
                pass

        logger.info(f"Cleanup complete: {deleted} files deleted")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def generate_unique_id(lyrics):
    """Generate unique ID"""
    return f"{hashlib.md5(lyrics.encode()).hexdigest()[:8]}_{int(time.time())}"

@app.route('/')
def index():
    """Main interface with improved timeout handling"""
    html_template = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎵 Generate Instrumental AI 🎵</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        #waveform { min-height: 80px; background: #f7fafc; border-radius: 0.5rem; padding: 0.5rem; }
        #audioSection { display: none; }
        .metadata-grid { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; }
        .metadata-item { display: flex; justify-content: space-between; align-items: center; padding: 0.25rem 0; border-bottom: 1px solid #e2e8f0; }
        .metadata-item:last-child { border-bottom: none; }
        .metadata-label { font-weight: 600; color: #374151; min-width: 120px; }
        .metadata-value { color: #1f2937; font-weight: 500; background: #f3f4f6; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.875rem; }
        #statusMsg { min-height: 1.5em; padding: 0.5rem; background: #f3f4f6; border-radius: 0.25rem; }
    </style>
    <script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"></script>
</head>
<body class="bg-gray-100 min-h-screen flex flex-col items-center justify-center p-4">
    <div class="bg-white p-8 rounded-lg shadow-xl w-full max-w-2xl border border-gray-200">
        <h1 class="text-3xl font-bold text-center mb-6 text-gray-800">🎵 Generate Instrumental AI 🎵</h1>

        <form id="musicForm">
            <div class="mb-4">
                <label for="textInput" class="block text-gray-700 text-sm font-bold mb-2">Lirik/Deskripsi:</label>
                <textarea id="textInput" rows="6" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Masukkan lirik atau deskripsi..."></textarea>
                <p id="charCount" class="text-xs text-gray-500 text-right mt-1">0 karakter</p>
            </div>

            <div class="mb-4">
                <label for="genreSelect" class="block text-gray-700 text-sm font-bold mb-2">Genre:</label>
                <select id="genreSelect" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="auto">🤖 Otomatis</option>
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

            <div class="mb-6">
                <label for="tempoInput" class="block text-gray-700 text-sm font-bold mb-2">Tempo (BPM):</label>
                <input type="number" id="tempoInput" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Auto (60-200)" min="60" max="200">
                <small class="text-gray-500">Kosongkan untuk tempo otomatis</small>
            </div>

            <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-bold hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 transition">
                <svg id="spinner" class="animate-spin -ml-1 mr-3 h-5 w-5 inline hidden" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                🚀 Generate Instrumental (3-4 menit)
            </button>
        </form>

        <div id="statusMsg" class="text-center text-sm mb-4 hidden"></div>

        <div id="audioSection" class="hidden">
            <h2 class="text-xl font-bold text-gray-800 mb-4">🎵 Hasil Instrumental 🎵</h2>
            
            <div class="metadata-grid">
                <h3 class="text-sm font-semibold text-gray-700 mb-2">Informasi:</h3>
                <div class="metadata-item"><span class="metadata-label">Genre:</span><span id="genreDisplay" class="metadata-value">N/A</span></div>
                <div class="metadata-item"><span class="metadata-label">Tempo:</span><span id="tempoDisplay" class="metadata-value">N/A</span></div>
                <div class="metadata-item"><span class="metadata-label">Durasi:</span><span id="durationDisplay" class="metadata-value">N/A</span></div>
                <div class="metadata-item"><span class="metadata-label">Ukuran:</span><span id="sizeDisplay" class="metadata-value">N/A</span></div>
            </div>

            <div id="waveform" class="mb-4"></div>
            <audio id="audioPlayer" class="w-full mb-4" controls></audio>
            
            <button id="downloadBtn" class="w-full bg-green-600 text-white py-3 px-4 rounded-lg font-bold hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 disabled:opacity-50" disabled>
                💾 Download MP3
            </button>
        </div>
    </div>

    <script>
        let wavesurfer = null;
        const form = document.getElementById('musicForm');
        const textInput = document.getElementById('textInput');
        const statusMsg = document.getElementById('statusMsg');
        const generateBtn = document.getElementById('generateBtn');
        const spinner = document.getElementById('spinner');
        const audioSection = document.getElementById('audioSection');
        const audioPlayer = document.getElementById('audioPlayer');
        const downloadBtn = document.getElementById('downloadBtn');
        const waveform = document.getElementById('waveform');

        // Character counter
        textInput.addEventListener('input', () => {
            document.getElementById('charCount').textContent = `${textInput.value.length} karakter`;
        });

        // Form submission with 7-minute timeout
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData();
            formData.append('lyrics', textInput.value.trim());
            formData.append('genre', document.getElementById('genreSelect').value);
            formData.append('tempo', document.getElementById('tempoInput').value || 'auto');

            // Reset UI
            statusMsg.classList.remove('hidden');
            statusMsg.innerHTML = '<p class="text-blue-600">🚀 Memulai generate instrumental... (Estimasi: 2-4 menit)</p>';
            generateBtn.disabled = true;
            spinner.classList.remove('hidden');
            audioSection.style.display = 'none';
            if (wavesurfer) {
                wavesurfer.destroy();
                wavesurfer = null;
            }

            const controller = new AbortController();
            const timeoutId = setTimeout(() => {
                controller.abort();
                statusMsg.innerHTML = `
                    <p class="text-red-600">⏰ Proses melebihi batas waktu (7 menit)</p>
                    <p class="text-sm text-gray-600 mt-1">Server mungkin masih memproses. Coba refresh halaman dalam 1-2 menit atau kurangi panjang lirik.</p>
                `;
                generateBtn.disabled = false;
                spinner.classList.add('hidden');
            }, 7 * 60 * 1000); // 7 minutes

            try {
                const response = await fetch('/generate-instrumental', {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);
                spinner.classList.add('hidden');

                if (response.ok) {
                    const data = await response.json();
                    
                    if (data.success) {
                        statusMsg.innerHTML = '<p class="text-green-600">🎉 Instrumental berhasil dibuat!</p>';
                        audioSection.style.display = 'block';
                        
                        // Update metadata
                        document.getElementById('genreDisplay').textContent = data.genre || 'N/A';
                        document.getElementById('tempoDisplay').textContent = `${data.tempo || 'N/A'} BPM`;
                        document.getElementById('durationDisplay').textContent = `${data.duration || 'N/A'} detik`;
                        document.getElementById('sizeDisplay').textContent = `${data.size || 'N/A'} KB`;
                        
                        // Setup audio
                        audioPlayer.src = `/static/audio_output/${data.filename}`;
                        audioPlayer.load();
                        downloadBtn.disabled = false;
                        
                        downloadBtn.onclick = () => {
                            const link = document.createElement('a');
                            link.href = `/static/audio_output/${data.filename}`;
                            link.download = `instrumental_${data.id}.mp3`;
                            link.click();
                        };

                        // Initialize wavesurfer if available
                        if (typeof Wavesurfer !== 'undefined') {
                            wavesurfer = Wavesurfer.create({
                                container: '#waveform',
                                waveColor: '#4f46e5',
                                progressColor: '#10b981',
                                height: 80,
                                barWidth: 2,
                                normalize: true
                            });
                            
                            wavesurfer.load(audioPlayer.src);
                            wavesurfer.on('ready', () => {
                                console.log('Waveform loaded');
                            });
                        }

                    } else {
                        statusMsg.innerHTML = `<p class="text-red-600">❌ ${data.error || 'Gagal generate'}</p>`;
                    }
                } else {
                    const errorData = await response.json();
                    statusMsg.innerHTML = `<p class="text-red-600">❌ Server Error: ${errorData.error || 'Unknown error'}</p>`;
                }
            } catch (error) {
                clearTimeout(timeoutId);
                spinner.classList.add('hidden');
                generateBtn.disabled = false;
                
                if (error.name === 'AbortError') {
                    statusMsg.innerHTML = `
                        <p class="text-yellow-600">⏰ Timeout (7 menit)</p>
                        <p class="text-sm text-gray-600 mt-1">Proses mungkin masih berjalan. Tunggu 1-2 menit lalu refresh.</p>
                    `;
                } else {
                    statusMsg.innerHTML = `<p class="text-red-600">🌐 Network Error: ${error.message}</p>`;
                }
            }
            
            generateBtn.disabled = false;
        });
    </script>
</body>
</html>
"""
    return render_template_string(html_template)

@app.route('/generate-instrumental', methods=['OPTIONS', 'POST'])
def generate_instrumental_endpoint():
    """Main endpoint - WITH COMPREHENSIVE ERROR HANDLING"""
    if request.method == 'OPTIONS':
        return '', 200

    start_time = time.time()
    logger.info("Receiving POST request to /generate-instrumental")

    try:
        data = request.form if request.form else request.json
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto').lower()
        tempo_input = data.get('tempo', 'auto')

        if not lyrics or len(lyrics) < 5:  # Reduced minimum length
            return jsonify({'error': 'Lirik minimal 5 karakter'}), 400

        logger.info(f"Processing lyrics: '{lyrics[:50]}...' ({len(lyrics)} chars)")
        logger.info(f"Input: Genre='{genre_input}', Tempo='{tempo_input}'")

        # Detect genre and get parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)

        # Generate unique ID and paths
        unique_id = generate_unique_id(lyrics)
        midi_filename = f"{unique_id}.mid"
        wav_filename = f"{unique_id}.wav"
        mp3_filename = f"{unique_id}.mp3"

        paths = {
            'midi': AUDIO_OUTPUT_DIR / midi_filename,
            'wav': AUDIO_OUTPUT_DIR / wav_filename,
            'mp3': AUDIO_OUTPUT_DIR / mp3_filename
        }

        logger.info(f"Starting generation for ID: {unique_id}")

        # Step 1: Generate MIDI (timeout: 60s)
        logger.info("1. Generating MIDI file...")
        if not create_midi_file(params, paths['midi']):
            if paths['midi'].exists():
                paths['midi'].unlink(missing_ok=True)
            return jsonify({'error': 'Gagal membuat file MIDI. Coba lirik yang lebih sederhana.'}), 500

        # Step 2: Render to audio (timeout: 120s)
        logger.info("2. Rendering MIDI to audio...")
        if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
            paths['midi'].unlink(missing_ok=True)
            return jsonify({'error': 'SoundFont tidak ditemukan'}), 500

        if not midi_to_audio(paths['midi'], paths['wav']):
            paths['midi'].unlink(missing_ok=True)
            return jsonify({'error': 'Gagal render audio. Pastikan FluidSynth terinstall.'}), 500

        # Step 3: Convert to MP3 (timeout: 30s)
        logger.info("3. Converting to MP3...")
        if not wav_to_mp3(paths['wav'], paths['mp3']):
            for path in [paths['midi'], paths['wav']]:
                if path.exists():
                    path.unlink(missing_ok=True)
            return jsonify({'error': 'Gagal konversi MP3. Pastikan FFmpeg terinstall.'}), 500

        # Cleanup temporary files
        for temp_path in [paths['midi'], paths['wav']]:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

        # Calculate duration
        duration_seconds = params['duration_beats'] * 60 / params['tempo']
        try:
            if paths['mp3'].exists():
                test_audio = AudioSegment.from_mp3(paths['mp3'])
                duration_seconds = len(test_audio) / 1000.0
        except:
            pass

        total_time = time.time() - start_time
        mp3_size_kb = paths['mp3'].stat().st_size / 1024 if paths['mp3'].exists() else 0

        logger.info(f"Generation complete in {total_time:.1f}s! ID: {unique_id}, File: {mp3_filename} ({mp3_size_kb:.1f} KB, {duration_seconds:.1f}s)")

        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration_seconds, 1),
            'id': unique_id,
            'size': round(mp3_size_kb),
            'progression': ' '.join(params.get('selected_progression', ['C']))
        })

    except Exception as e:
        logger.error(f"Critical generation error: {e}", exc_info=True)
        # Cleanup any partial files
        for path in paths.values():
            if path and path.exists():
                try:
                    path.unlink()
                except:
                    pass
        return jsonify({'error': f'Error internal: {str(e)[:100]}'}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve audio files"""
    try:
        file_path = AUDIO_OUTPUT_DIR / filename
        if not file_path.exists():
            return "File not found", 404

        mimetype = 'audio/mpeg' if filename.endswith('.mp3') else 'audio/wav'
        return send_from_directory(AUDIO_OUTPUT_DIR, filename, mimetype=mimetype, as_attachment=True)
    except Exception as e:
        logger.error(f"Error serving {filename}: {e}")
        return "Server error", 500

def get_local_ip():
    """Get local IP"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def main_app_runner():
    """Startup with system checks"""
    logger.info("Starting Flask Generate Instrumental AI! 🚀")
    logger.info("  ✅ FIXED: Chord progression handling + Performance optimization")
    logger.info("  ✅ NEW: 7-minute timeout + Memory-efficient generation")
    logger.info("  ✅ ARM64: Optimized for mobile/ARM devices")

    try:
        if SOUNDFONT_PATH:
            logger.info(f"✅ SoundFont: {SOUNDFONT_PATH.name}")
        else:
            logger.warning("⚠️  No SoundFont found - download required")

        check_python_dependencies()
        cleanup_old_files(AUDIO_OUTPUT_DIR, max_age_hours=24)

        logger.info(f"🚀 Server ready! http://{get_local_ip()}:5000")
        logger.info(f"Available genres: {list(GENRE_PARAMS.keys())}")
        logger.info("💡 Tip: Generation takes 2-4 minutes. Be patient! ⏳")

    except Exception as e:
        logger.error(f"Startup error: {e}")
        return False

    return True

if __name__ == '__main__':
    if main_app_runner():
        try:
            app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
    else:
        sys.exit(1)
