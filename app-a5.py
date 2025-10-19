import os
import sys
import time
import random
import logging
import hashlib
import shutil
import math  # Tambahan untuk bass line calculation
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from midiutil import MIDIFile
import subprocess
import tempfile
from textblob import TextBlob
import pyphen

# Import pyfluidsynth dengan error handling (opsional, tidak digunakan utama)
try:
    import fluidsynth as pyfluidsynth_lib
    FLUIDSYNTH_BINDING_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_BINDING_AVAILABLE = False

from pydub import AudioSegment

# Konfigurasi logging
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

# Path konfigurasi (Revisi: Deteksi SoundFont otomatis)
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'

# Deteksi SoundFont otomatis (prioritas: GeneralUser GS > FluidR3 > fallback)
SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',
    BASE_DIR / 'GeneralUser GS v1.471.sf2',
    BASE_DIR / 'FluidR3_GM.sf2',
    BASE_DIR / 'Super_Heavy_Guitar_Collection.sf2',  # Fallback terakhir
]

for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        break

if not SOUNDFONT_PATH:
    logger.warning("Tidak ada SoundFont ditemukan. Download GeneralUser GS dari: https://musical-artifacts.com/artifacts/661")

# Buat direktori jika belum ada
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

def check_module(module_name):
    """Check if a module is available"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def check_python_dependencies():
    deps = {
        'Flask-CORS': 'flask_cors' in sys.modules or __import__('flask_cors'),
        'MIDIUtil': 'midiutil' in sys.modules or __import__('midiutil'),
        'TextBlob': 'textblob' in sys.modules or __import__('textblob'),
        'Pyphen': 'pyphen' in sys.modules or __import__('pyphen'),
        'Pydub': 'pydub' in sys.modules or check_module('pydub'),
    }
    return [name for name, available in deps.items() if available]

# Dictionary instrumen GM SoundFont (Revisi: Case-insensitive matching)
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

    # Vocals
    'Choir Aahs': 52, 'Voice Oohs': 53, 'Synth Voice': 54, 'Orchestra Hit': 55,

    # Brass
    'Trumpet': 56, 'Trombone': 57, 'Tuba': 58, 'Muted Trumpet': 59,
    'French Horn': 60, 'Brass Section': 61, 'Synth Brass 1': 62, 'Synth Brass 2': 63,

    # Reed
    'Soprano Sax': 64, 'Alto Sax': 65, 'Tenor Sax': 66, 'Baritone Sax': 67, 
    'English Horn': 69, 'Bassoon': 70, 'Clarinet': 71,

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

    # Percussive
    'Tinkle Bell': 112, 'Agogo': 113, 'Steel Drums': 114, 'Woodblock': 115,

    # Sound FX
    'Guitar Fret Noise': 120, 'Breath Noise': 121, 'Seashore': 122, 'Bird Tweet': 123,
    'Telephone Ring': 124, 'Helicopter': 125, 'Applause': 126, 'Gunshot': 127,

    # Indonesian Instruments (aproksimasi)
    'Gamelan': 114, 'Kendang': 115, 'Suling': 75, 'Rebab': 110,
    'Talempong': 14, 'Gambus': 25, 'Mandolin': 27, 'Harmonica': 22,
}

# Dictionary chord dengan notasi MIDI (C4 = 60)
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

    # Seventh chords
    'C7': [60, 64, 67, 70], 'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74],
    'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77],
    'Cm7': [60, 63, 67, 70], 'Fm7': [65, 68, 72, 75], 'Bbmaj7': [70, 74, 77, 81],
    'Cm9': [60, 63, 67, 70, 74], 'Fm9': [65, 68, 72, 75, 79],
    'Ebmaj7': [63, 67, 70, 74], 'Gmaj7': [67, 71, 74, 78], 'Cmaj7': [60, 64, 67, 71],

    # Suspended chords
    'Csus4': [60, 65, 67], 'Dsus4': [62, 67, 69], 'Esus4': [64, 69, 71],
    'Fsus4': [65, 70, 72], 'Gsus4': [67, 72, 74], 'Asus4': [69, 74, 76],

    # Diminished chords
    'Cdim': [60, 63, 66], 'Ddim': [62, 65, 68], 'Edim': [64, 67, 70],
    'Fdim': [65, 68, 71], 'Gdim': [67, 70, 73], 'Adim': [69, 72, 75],

    # Augmented chords
    'Caug': [60, 64, 68], 'Daug': [62, 66, 70], 'Eaug': [64, 68, 72],
    'Faug': [65, 69, 73], 'Gaug': [67, 71, 75], 'Aaug': [69, 73, 77],
}

# Dictionary skala untuk berbagai genre
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'locrian': [0, 1, 3, 5, 6, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 3, 5, 7, 10],
    'latin': [0, 2, 4, 5, 7, 9, 10],
    'dangdut': [0,7, 8, 11],
}

# Parameter musik berdasarkan genre
GENRE_PARAMS = {
    'pop': {
        'tempo': 126, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': ['Soprano Sax', 'Clean Electric Guitar', 'Electric Piano 1'],
            'harmony': ['String Ensemble 1', 'New Age Pad', 'Electric Piano 2'],
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
        },
        'drums_enabled': True,
        'chord_progression': ['C', 'G', 'Am', 'F'],
        'duration_beats': 128,
        'mood': 'happy'
    },
    'rock': {
        'tempo': 135, 'key': 'E', 'scale': 'major',
        'instruments': {
            'melody': ['Distortion Guitar', 'Rock Organ'],
            'harmony': ['Overdriven Guitar', 'Brass Section', 'Rock Organ'],
            'bass': ['Electric Bass pick', 'Fretless Bass'],
        },
        'drums_enabled':ion': ['E', 'A', 'B', 'C#m'],
        'duration_beats': 128,
        'mood': 'energetic'
    },
    'metal': {
        'tempo': 120, 'key': 'E', 'scale': 'minor',
        'instruments': {
            'melody': ['Distortion Guitar'],
            'harmony': ['Distortion Guitar', 'Overdriven Guitar', 'String Ensemble 1'],
            'bass': ['Electric Bass pick', 'Synth Bass 1'],
        },
        'drums_enabled': True,
        'chord_progression': ['Em', 'G', 'D', 'A'],
        'duration_beats': 128,
        'mood': 'intense'
    },
    'ballad': {
        'tempo': 72, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': ['Nylon String Guitar', 'Violin', 'Cello'],
            'harmony': ['String Ensemble 1', 'Warm Pad', 'Electric Piano 1'],
            'bass': ['Acoustic Bass', 'Fretless Bass'],
        },
        'drums_enabled': False,
        'chord_progression': ['C', 'G', 'Am', 'F'],
        'duration_beats': 128,
        'mood': 'emotional'
    },
    'blues': {
        'tempo': 100, 'key': 'A', 'scale': 'blues',
        'instruments': {
            'melody': ['Tenor Sax', 'Jazz Electric Guitar', 'Harmonica'],
            'harmony': ['Electric Piano 1', 'Drawbar Organ', 'Brass Section'],
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
        },
        'drums_enabled': True,
        'chord_progression': ['C7', 'F7', 'G7'],
        'duration_beats': 128,
        'mood': 'soulful'
    },
    'jazz': {
        'tempo': 140, 'key': 'C', 'scale': 'dorian',
        'instruments': {
            'melody': ['Tenor Sax', 'Jazz Electric Guitar'],
            'harmony': ['Electric Piano 1', 'Brass Section', 'String Ensemble 1'],
            'bass': ['Acoustic Bass', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progression': ['Cm7', 'Fm7', 'Bbmaj7', 'Ebmaj7'],
        'duration_beats': 128,
        'mood': 'sophisticated'
    },
    'hiphop': {
        'tempo': 97, 'key': 'Cm', 'scale': 'minor',
        'instruments': {
            'melody': ['Square Wave', 'Electric Piano 2'],
            'harmony': ['Poly Synth Pad', 'Synth Bass 1'],
            'bass': ['Synth Bass 1', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progression': ['Cm', 'Ab', 'Bb', 'Fm'],
        'duration_beats': 128,
        'mood': 'urban'
    },
    'latin': {
        'tempo': 91, 'key': 'G', 'scale': 'latin',
        'instruments': {
            'melody': ['Nylon String Guitar', 'Flute'],
            'harmony': ['Acoustic', 'String Ensemble 1', 'Brass Section'],
            'bass': ['Acoustic Bass', 'Electric Bass finger'],
        },
        'drums_enabled': True,
        'chord_progression': ['Am', 'D7', 'Gmaj7', 'Cmaj7'],
        'duration_beats': 128,
        'mood': 'rhythmic'
    },
    'dangdut': {
        'tempo': 110, 'key': 'Am', 'scale': 'dangdut',
        'instruments': {
            'melody': ['Distortion Guitar', 'Violin', 'String Ensemble 1'],
            'harmony': ['Nylon String Guitar', 'String Ensemble 1', 'Electric Piano 1'],
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
        },
        'drums_enabled': True,
        'chord_progression': ['Am', 'Dm', 'G', 'C'],
        'duration_beats': 128,
        'mood':re_from_lyrics(lyrics):
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'party', 'fun', 'happy', 'tonight', 'forever', 'together'],
        'rock': ['rock', 'guitar', 'energy', 'power', 'fire', 'wild', 'roll', 'scream', 'freedom'],
        'metal': ['metal', 'heavy', 'dark', 'scream', 'thunder', 'steel', 'rage', 'shadow', 'death'],
        'ballad': ['sad', 'love', 'heartbreak', 'memory', 'gentle', 'soft', 'tears', 'alone', 'forever'],
        'blues': ['soul', 'heartache', 'guitar', 'night', 'trouble', 'baby', 'lonely'],
        'jazz': ['jazz', 'smooth', 'night', 'sax', 'cool', 'swing', 'harmony', 'blue', 'lounge'],
        'hiphop': ['rap', 'street', 'beat', 'flow', 'rhythm', 'hustle', 'city', 'rhyme', 'crew'],
        'latin': ['latin', 'bossanova', 'salsa', 'rhythm', 'dance', 'passion', 'fiesta', 'caliente', 'amor', 'despacito'],
        'dangdut': ['dangdut', 'tradisional', 'cinta', 'hati', 'kenangan', 'indonesia', 'rindu', 'sayang', 'melayu', 'koplo']
    }

    blob = TextBlob(lyrics.lower())
    words = set(blob.words)

    scores = {genre: sum(1 for keyword in kw_list if keyword in words)
              for genre, kw_list in keywords.items()}

    detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
    logger.info(f"Genre terdeteksi dari kata kunci: '{detected_genre}'")
    return detected_genre

def find_best_instrument(choice_list):
    """Fuzzy matching untuk instrumen (case-insensitive + partial match)"""
    if not isinstance(choice_list, list):
        choice_list = [choice_list]
    
    for choice in choice_list:
        choice_lower = choice.lower().strip()
        # Exact match (case-insensitive)
        for instr, num in INSTRUMENTS.items():
            if choice_lower == instr.lower():
                return instr
        # Partial match
        for instr, num in INSTRUMENTS.items():
            if choice_lower in instr.lower() or any(word in instr.lower() for word in choice_lower.split()):
                return instr
    
    # Fallback berdasarkan kategori
    if any(word in choice_lower for word in ['guitar', 'lead', 'solo']):
        return 'Distortion Guitar'
    elif any(word in choice_lower for word in ['piano', 'key']):
        return 'Acoustic Grand Piano'
    elif any(word in choice_lower for word in ['string', 'pad', 'chord']):
        return 'String Ensemble 1'
    elif any(word in choice_lower for word in ['bass']):
        return 'Acoustic Bass'
    else:
        return 'Acoustic Grand Piano'

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy()

    # Override tempo jika user input spesifik
    if user_tempo_input != 'auto':
        try:
            params['tempo'] = int(user_tempo_input)
            if not (60 <= params['tempo'] <= 200):
                logger.warning(f"Tempo di luar jangkauan (60-200 BPM): {user_tempo_input}, menggunakan default.")
                params['tempo'] = GENRE_PARAMS[genre.lower()]['tempo']
        except ValueError:
            logger.warning(f"Tempo input tidak valid: '{user_tempo_input}', menggunakan default.")
            params['tempo'] = GENRE_PARAMS[genre.lower()]['tempo']

    # Analisis sentimen untuk mood adjustment
    blob = TextBlob(lyrics)
    sentiment = blob.sentiment.polarity

    if sentiment < -0.3:
        params['mood'] = 'sad'
        params['scale'] = 'minor'
    elif sentiment > 0.3:
        params['mood'] = 'happy'
        params['scale'] = 'major'

    # Pilih instrumen dengan fuzzy matching
    for category, instrument_choices in params['instruments'].items():
        selected = find_best_instrument(instrument_choices)
        params['instruments'][category] = selected
        program_num = INSTRUMENTS.get(selected, 0)
        logger.info(f"{category.capitalize()} instrument: {selected} (Program {program_num})")

    # Generate chord progression
    base_chords = params['chord_progression']
    selected_chords = []
    for chord_name in base_chords:
        if chord_name in CHORDS:
            selected}' (Mood: {params['mood']}): Tempo={params['tempo']}BPM, Durasi={params['duration_beats']} beats")
    return params

def get_scale_notes(key, scale_name):
    root_midi = CHORDS.get(key, [60])[0]
    scale_intervals = SCALES.get(scale_name, SCALES['major'])
    return [root_midi + interval for interval in scale_intervals]

def generate_melody(params):
    scale_notes = get_scale_notes(params['key'], params['scale'])
    duration_beats = params['duration_beats']

    melody = []

    # Pattern melodi berdasarkan mood
    if params['mood'] == 'sad':
        patterns = [[1, 0.5, 1, 0.5, 2], [0.5, 0.5, 1, 1.5, 1], [1, 1, 0.5, 0.5, 2]]
        velocities = [60, 70]
    elif params['mood'] == 'energetic':
        patterns = [[0.5, 0.5, 1, 0.5, 0.5, 1], [0.5, 0.5, 0.5, 0.5, 1, 2], [1, 1, 1, 1]]
        velocities = [90, 100]
    elif params['mood'] == 'rhythmic' or params['genre'] in ['latin', 'dangdut']:
        patterns = [[0.5, 0.5, 1, 0.5, 0.5, 1], [1, 0.5, 0.5, 1, 1], [0.5, 1, 0.5, 1, 1]]
        velocities = [80, 90]
    else:
        patterns = [[1, 1, 0.5, 0.5, 1.5], [0.5, 1, 1.5, 1], [1, 1, 2]]
        velocities = [70, 85]

    current_pattern = random.choice(patterns)
    current_velocity = random.choice(velocities)

    total_beats_generated = 0
    time_pos = 0.0
    while total_beats_generated < duration_beats:
        for beat_duration_segment in current_pattern:
            if total_beats_generated + beat_duration_segment > duration_beats:
                beat_duration_segment = duration_beats - total_beats_generated
                if beat_duration_segment <= 0.001: 
                    break

            note_idx = random.randint(0, len(scale_notes) - 1)
            octave_shift = random.choice([-12, 0, 12])
            pitch = scale_notes[note_idx] + octave_shift
            pitch = max(36, min(84, pitch))  # Batasi range untuk suara yang lebih natural

            melody.append((pitch, time_pos, beat_duration_segment, current_velocity))
            time_pos += beat_duration_segment
            total_beats_generated += beat_duration_segment
            if total_beats_generated >= duration_beats:
                break

        # Ganti pattern setiap 16 beats untuk variasi
        if total_beats_generated > 16 and (total_beats_generated % 16) < 1:
            current_pattern = random.choice(patterns)
            current_velocity = random.choice(velocities)

    return melody

def generate_harmony(params):
    chords = params['chords']
    duration_beats = params['duration_beats']

    harmony = []

    beats_per_chord = duration_beats // len(chords)

    if params['mood'] in ['sad', 'emotional']:
        velocity = 50
    elif params['mood'] in ['energetic', 'intense']:
        velocity = 70
    else:
        velocity = 60

    current_beat = 0.0
    for i, chord_notes in enumerate(chords):
        chord_duration = beats_per_chord
        if i == len(chords) - 1:
            chord_duration = duration_beats - current_beat

        if chord_duration <= 0.001:
            break

        # Mainkan semua note chord secara bersamaan
        for note in chord_notes:
            # Batasi octave untuk harmony (lebih rendah dari melody)
            harmony_note = max(36, min(72, note))
            harmony.append((harmony_note, current_beat, chord_duration, velocity))

        current_beat += chord_duration

    return harmony

def generate_bass_line(params):
    chords = params['chords']
    duration_beats = params['duration_beats']

    bass_line = []

    beats_per_chord = duration_beats // len(chords)

    if params['mood'] in ['sad', 'emotional']:
        velocity = 70
    elif params['mood'] in ['energetic', 'intense']:
        velocity = 100
    else:
        velocity = 85

    current_beat = 0.0
    for i, chord_notes in enumerate(chords):
        root_note = chord_notes[0] - 24  # Bass satu octave di bawah
        root_note = max(24, 48))  # Batasi range bass

        chord_duration = beats_per_chord
        if i == len(chords) - 1:
            chord_duration = duration_beats - current_beat

        if chord_duration <= 0.001:
            break

        # Gunakan untuk integer beats
        num_beats = math.ceil(chord_duration)
        for beat_in_chord in range(min(num_beats, int(chord_duration))):
            # Root note pada beat utama
            bass_line.append((root_note, current_beat + beat_in_chord, 1.0, velocity))
            
            # Fifth (interval 7 semitone) pada off-beat jika memungkinkan
            if beat_in_chord + 0.5 < chord_duration:
                fifth_note = root_note + 7
                if fifth_note <= 48:  # Pastikan tidak terlalu tinggi untuk bass
                    bass_line.append((fifth_note, current_beat + beat_in_chord + 0.5, 0.5, velocity - 15))
                else:
                    # Fallback ke root jika fifth terlalu tinggi
                    bass_line.append((root_note, current_beat + beat_in_chord + 0.5, 0.5, velocity - 15))

        current_beat += chord_duration

    return bass_line

def create_midi_file(params, output_path):
    tempo = params['tempo']
    duration_beats = params['duration_beats']

    # 4 tracks untuk channel isolation: Melody(0), Harmony(1), Bass(2), Drums(9)
    midi = MIDIFile(4, ticks_per_beat=120)

    # Set tempo untuk semua tracks
    for i in range(4):
        midi.addTempo(i, 0, tempo)

    # Track 0: Melody (Channel 0)
    melody_instrument = params['instruments']['melody']
    if melody_instrument:
        program_num = INSTRUMENTS.get(melody_instrument, 0)
        midi.addProgramChange(0, 0, 0, program_num)
        logger.info(f"Melody track: {melody_instrument} (Program {program_num}, Channel 0)")

        melody_notes = generate_melody(params)
        for pitch, time_pos, duration, velocity in melody_notes:
            final_velocity = min(127, int(velocity * 1.2))  # Boost melody
            safe_duration = min(duration, 4.0)  # Max 4 beats per note
            if safe_duration > 0.25:  # Min duration untuk menghindari noise
                midi.addNote(0, 0, pitch, time_pos, safe_duration, final_velocity)

    # Track 1: Harmony/Chords (Channel 1)
    harmony_instrument = params['instruments']['harmony']
    if harmony_instrument:
        program_num = INSTRUMENTS.get(harmony_instrument, 48)
        midi.add 1, 0, program_num)
        logger.info(f"Harmony track: {harmony_instrument} (Program {program_num}, Channel 1)")

        harmony_data = generate_harmony(params)
        for pitch, start_beat, duration, velocity in harmony_data:
            final_velocity = min(127, int(velocity * 0.6))  # Harmony lebih lembut
            safe_duration = min(duration, 4.0)
            if safe_duration > 0.25:
                midi.addNote(1, 1, pitch, start_beat, safe_duration, final_velocity)

    # Track 2: Bass (Channel 2)
    bass_instrument = params['instruments']['bass']
    if bass_instrument:
        program_num = INSTRUMENTS.get(bass_instrument, 33)
        midi.addProgramChange(2, 2, 0, program_num)
        logger.info(f"Bass track: {bass_instrument} (Program {program_num}, Channel 2)")

        bass_notes = generate_bass_line(params)
        for pitch, start_beat velocity in bass_notes:
            final_velocity = min(127, int(velocity * 1.1))  # Bass agak kuat
            safe_duration = min(duration, 2.0)
            if safe_duration > 0.25:
                midi.addNote(2, 2, pitch, start_beat, safe_duration, final_velocity)

    # Track 3: Drums (Channel 9 - Standard GM Drum Kit)
    if params['drums_enabled']:
        # Drums selalu di channel 9, program 0 (standard kit)
        midi.addProgramChange(3,  0, 0)
        logger.info("Drums track: Standard GM Kit (Channel 9)")

        # Basic rock/4/4 drum pattern
        for beat_pos in range(int(duration_beats)):
            # Kick drum (note  1 & 3
            if beat_pos % 4 == 0 or beat_pos % 4 == 2:
                midi.addNote(3, 9, 36, beat_pos, 0.5, 110)  # Kick
            
            # Snare drum (note 38) pada beat 2 & 4
            if beat_pos % 4 == 1 or beat_pos % 4 == 3:
                midi.addNote(3, 9, 38, beat_pos, 0.5, 95)   # Snare
            
            # Hi-hat (note 42) setiap beat
            midi.addNote(3, 9, 42, beat_pos, 0.25, 75)    # Closed Hi-hat

            # Tambahan percussion untuk genre tertentu
            if params['genre'] in ['latin', 'dangdut'] and beat_pos % 2 == 0:
                # Tambah conga/tom untuk rhythmic feel
                perc_note = random.choice([43, 45, 49])  # Low/Mid/High Tom
                midi.addNote(3, 9, perc_note, beat_pos + 0.25, 0.25, 60)

    # Write MIDI file
    try:
        with open(output_path, 'wb') as f:
            midi.writeFile(f)
        logger.info(f"MIDI generated dengan channel terpisah: {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"Error writing MIDI file: {e}")
        return False

def midi_to_audio_pyfluidsynth(midi_path, output_wav_path, soundfont_path):
    """Fallback menggunakan pyfluidsynth (tidak direkomendasikan untuk ARM64)"""
    if not FLUIDSYNTH_BINDING_AVAILABLE:
        logger.warning("pyfluidsynth tidak tersedia, menggunakan subprocess")
        return False

    try:
        fs = pyfluidsynth_lib.Synth()
        fs.start(driver='alsa')  # Atau 'pulseaudio' jika tersedia

        # Load SoundFont
        sfid = fs.sfload(str(soundfont_path))
        if sfid == pyfluidsynth_lib.ERROR_CODE(directory).glob("*.{mp3,wav,mid}"):
        try:
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_time < cutoff_time:
                file_path.unlink()
                logger.debug(f"  - Dihapus: {file_path.name}")
                deleted_count += 1
        except Exception as e:
            logger.warning(f"Error hapus {file_path.name}: {e}")

    logger.info(f"🧹 Pembersihan selesai: {deleted_count} file dihapus")
    return deleted_count

def generate_unique_id(lyrics):
    """Generate unique ID berdasarkan hash lirik + timestamp"""
    hash_object = hashlib.md5(lyrics.encode('utf-8')).hexdigest()
    timestamp = str(int(time.time()))
    return f"{hash_object[:8]}_{timestamp}"

@app.route('/')
def index():
    """Main web interface"""
    html_template = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎵 Flask Generate Instrumental 🎵</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
                color: #333;
            }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { 
                text-align: center; 
                color: white; 
                margin-bottom: 30px; 
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                font-size: 2.5em;
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
                height: 200px;
                padding: 15px;
                border: 2px solid #ddd;
                border-radius: 10px;
                font-size: 16px;
                resize: vertical;
                font-family: inherit;
                transition: border-color 0.3s;
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
            input[type="number"] { width: 200px; display: inline-block; margin-right: 10px; }
            .form-row { display: flex; gap: 15px; align-items: end; }
            .form-row label { margin-bottom: 0; }
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
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover { 
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(52, 152, 219, 0.4);
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
           8db; }
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
                border600px) {
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
            <p style="text-align: center; color: white; margin-bottom: 30px;">
                Masukkan lirik Anda dan AI akan generate instrumental musik otomatis! 
                Support Pop, Rock, Metal, Jazz, Latin, Dangdut, dan lainnya.
            </p>

            <div class="card">
                <form id="musicForm">
                    <label for="lyrics">📝 Lirik Lagu:</label>
                    <textarea 
                        id="lyrics" 
                        name="lyrics" 
                        placeholder="Masukkan lirik lagu Anda di sini...

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
                        <div style="flex: 1;">
                            <label for="genre">🎸 Genre Musik:</label>
                            <select id="genre" name="genre">
                                <option value="auto">🤖 Auto-Detect dari Lirik</option>
                                <option value="pop">🎤 Pop</option>
                                <option value="rock">🎸 Rock</option>
                                <option value="metal">🤘 Metal</="ballad">💔 Ballad</option>
                                <">🎷 Blues</option>
                                <option value="jazz">🎹 Jazz</option>
                                <option value="hiphop">🎧 Hip-Hop</option>
                                <option value="latin">💃 Latin</option>
                                <option value="dangdut">🎶 Dangdut</option>
                            </select>
                        </div>
                        <div style="flex: 1;">
                            <label for="tempo">🥁 Tempo (BPM):</label>
                            <input type="number" id="tempo" name="tempo" min="60" max="200" placeholder="Auto">
                            <small>(Kosongkan untuk auto-detect berdasarkan genre)</small>
                        </div>
                    </div>

                    <button type="submit">🚀 Generate Instrumental Sekarang!</button>
                </form>
            </div>

            <div id="result" class="result">
                <h3>🎉 Hasil Generasi Musik:</h3>
                <div id="status" class="status"></div>
                <div id="loading" class="loading" style="display: none;">
                    <div class="spinner"></div>
                    <p>🎵 AI sedang mengkomposisi musik Anda... Ini butuh 30-60 detik</p>
                    <p>Proses: Analisis lirik → Generate melody → Harmony → Mixing</p>
                </div>
                <audio id="audioPlayer" controls style="display: none;"></audio>
                <div id="downloadLinks"></div>
                <div id="info"></div>
            </div>
        </div>

        <script>
            document.getElementById('musicForm').addEventListener('submit', async function(e) {
                e.preventDefault();

                // Get form data
                const formData = new FormData();
                formData.append('lyrics', document.getElementById('lyrics').value.trim());
                formData.append('genre', document.getElementById('genre').value);
                
                const tempoValue = document.getElementById('tempo').value;
                formData.append('tempo', tempoValue === '' ? 'auto' : tempoValue);

                // UI updates
                const resultDiv = document.getElementById('result');
                const statusDiv = document.getElementById('status');
                const loadingDiv = document.getElementById('loading');
                const audioPlayer = document.getElementById('audioPlayer');
                const downloadLinks = document.getElementById('downloadLinks');
                const infoDiv = document.getElementById('info');

                resultDiv.classList.add('show');
                statusDiv.innerHTML = '';
                loadingDiv.style.display = 'block';
                audioPlayernone';
                downloadLinks.innerHTML = '';
                infoDiv.innerHTML = '';

                try {
                    // Show processing status
                    statusDiv.innerHTML = '<p class="success">🚀 Memulai generasi instrumental...</p>';
                    
                    const response = await fetch('/generate-instrumental', {
                        method: 'POST',
                        body: formData
                    });

                    loadingDiv.style.display = 'none';

                    if (response.ok) {
                        const.json();
                        
                        if (data.success) {
                            statusDiv.innerHTML = `
                                <p class="success">🎉 Instrumental berhasil digenerate!</p>
                                <p><strong>Genre:</strong> <span class="info">${data.genre}</span></p>
                                <p><strong>Tempo:</strong> <span class="info">${data.tempo} BPM</span></p>
                                <p><strong>Durasi:</strong> <span class="info">${data.duration} detik</span></p>
                                <p><strong>ID:</strong> <span class="info">${data.id}</span></p>
                            `;

                            // Setup audio player
                            audioPlayer.src = `/static/audio_output/${data.filename}`;
                            audioPlayer.style.display = 'block';
                            audioPlayer.load();
                            
                            // Auto-play                            setTimeout(() => {
                                audioPlayer.play().catch(e => {
                                    console.log('Autoplay blocked:', e);
                                });
                            }, 500);

                            // Download links
                            downloadLinks.innerHTML = `
                                <a href="/static/audio_output/${data.filename}" class="download-btn" download>
                                    💾 Download MP3 (${Math.round(data.size || 0)} KB)
                                </a>
                                <br><small>Share hasil Anda di media sosial! 🎵</small>
                            `;

                            // Additional info
                            infoDiv.innerHTML = `
                                <p style="font-size: 0.9em; color: #7f8c8d; margin-top: 20px;">
                                    <strong>🔧 Technical Info:</strong> Generated dengan channel isolation (Melody/Harmony/Bass/Drums terpisah) 
                                    menggunakan FluidSynth + General MIDI SoundFont. Proyek open-source di GitHub.
                                </p>
                            `;
                        } else {
                            throw new Error(data.error || 'Unknown error');
                        }
                    } else const errorData = await response.json();
                        statusDiv.innerHTML = `<p class="error">❌ Error: ${errorData.error || 'Gagal generate instrumental'}</p>`;
                        
                        if (errorData.error?.includes('FluidSynth')) {
                            statusDiv.innerHTML += `
                                <p style="font-size: 0.9em; color: #e67e22;">
                                    💡 Tips: Pastikan FluidSynth terinstall (sudo apt install fluidsynth) dan SoundFont tersedia.
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

            // Auto-resize textarea
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

    logger.info("🌐 Menerima request POST /generate-instrumental")

    try:
        # Parse input
        data = request.form if request.form else request.json
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto'). 'auto')

        if not lyrics or len(lyrics) < 10:
            return jsonify({'error': 'Lirik minimal 10 karakter. Masukkan lirik lengkap untuk analisis genre/mood.'}), 400

        logger.info(f"📝 Lirik: '{lyrics[:100]}...' ({len(lyrics)} chars)")
        logger.info(f"🎸 Input: Genre='{genre_input}', Tempo='{tempo_input}'")

        # Detect genre dan generate params
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)

        # Generate unique filename
        unique_id = generate_unique_id(lyrics)
        midi_filename = f"{unique_id}.mid"
        wav_filename = f"{unique_id}.wav"
        mp3_filename = f"{unique_id}.mp3"

        paths = {
            'midi': AUDIO_OUTPUT_DIR / midi_filename,
            'wav': AUDIO_OUTPUT_DIR / wav_filename,
            'mp3': AUDIO_OUTPUT_DIR / mp3_filename
        }

        logger.info(f"🎼 Mulai generate untuk ID: {unique_id}")

        # Step 1: Generate MIDI
        logger.info("1️⃣ Generating MIDI file...")
        if not create_midi_file(params, paths['midi']):
            return jsonify({'error': 'Gagal membuat file MIDI. Cek log untuk detail.'}), 500

        # Step 2: Render ke WAV dengan FluidSynth
        logger.info("2️⃣ Rendering MIDI ke audio (FluidSynth)...")
        if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
            paths['midi'].unlink(missing_ok=True)
            return jsonify({
                'error': f'SoundFont tidak ditemukan: {SOUNDFONT_PATH}. Download dari https://musical-artifacts.com/661'
            }), 500

        if not midi_to_audio(paths['midi'], paths['wav']):
            paths['midi'].unlink(missing_ok=True)
            return jsonify({
                'error': 'Gagal render MIDI ke audio. Pastikan FluidSynth terinstall: sudo apt install fluidsynth libsndfile1'
            }), 500

        # Step 3: Konversi ke MP3
        logger.info("3️⃣ Converting ke MP3 format...")
        if not wav_to_mp3(paths['wav'], paths['mp3']):
            # Cleanup partial files
            for path in [paths['midi'], paths['wav']]:
                if path.exists():
                    path.unlink()
            return jsonify({'error': 'Gagal konversi ke MP3. Pastikan FFmpeg terinstall: sudo apt install ffmpeg'}), 500

        # Step 4: Calculate duration
        duration_seconds = params['duration_beats'] * 60 / params['tempo']  # Estimasi
        try:
            if paths['mp3'].exists():
                audio = AudioSegment.from_mp3(paths['mp3'])
                duration_seconds0.0  # Durasi aktual
        except Exception as e:
            logger.warning(f"Gagal hitung durasi MP3: {e}")

        # Step 5: Cleanup temporary files
        for temp_path in [paths['midi'], paths['wav']]:
            if temp_path.exists():
                temp_path.unlink()
        logger.info("🧹 Temporary files cleaned up")

        # Get file size
        mp3_size_kb = paths['mp3'].stat().st_size / 1024 if paths['mp3'].exists() else 0

        logger.info(f"✅ Generate selesai! ID: {unique_id}, File: {mp3_filename} ({mp3_size_kb:.1f} KB)")

        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'audio_url': f'/static/audio_output/{mp3_filename}',
            'download_url': request.url_root + f'static/audio_output/{mp3_filename}',
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration_seconds, 1),
            'id': unique_id,
            'size': round(mp3_size_kb),
            'soundfont': SOUNDFONT_PATH.name if SOUNDFONT_PATH else 'None'
        })

    except Exception as e:
        logger.error(f"💥 Critical error saat generate: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve audio files"""
    try:
        file_path = AUDIO_OUTPUT_DIR / filename
        if not file_path.exists():
            logger.warning(f"File audio tidak ditemukan: {file_path}")
            return "File not found", 404

        # Set correct mimetype
        mimetype = 'audio/mpeg' if filename.endswith('.mp3') else 'audio/wav'
        
        logger.info(f"📱 Serving: {filename} ({mimetype}, {file_path.stat().st_size/1024:.1f} KB)")

        return send_from_directory(
            AUDIO_OUTPUT_DIR,
            filename,
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
            cache_timeout=3600  # 1 hour cache
        )

    except Exception as e:
        logger.error(f"Error serving audio {filename}: {e}")
        return "Internal server error", 500

def get_local_ip():
    """Get local network IP"""
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
    """Main application runner dengan startup checks"""
    logger.info("🚀 Memulai Flask Generate Instrumental AI!")
    logger.info("   🎼 Revisi: ARM64 FluidSynth Fix + Channel Isolation + Smart Instrument Matching")

    try:
        # Check SoundFont
        if not SOUNDFONT_PATH:
            logger.critical("❌ CRITICAL: SoundFont tidak ditemukan!")
            logger.critical("   Download GeneralUser GS: wget https://github.com/JustEnoughLinuxOS/generaluser-gs/releases/download/1.471/GeneralUser-GS-v1.471.sf2")
            logger.critical("   Letakkan di folder yang sama dengan app.py")
            sys.exit(1)
        else:
            logger.info(f"✅ SoundFont: {SOUNDFONT_PATH.name} ({SOUNDFONT_PATH.stat().st_size/1024/1024:.1f} MB)")

        # Check dependencies
        available_deps = check_python_dependencies()
        logger.info(f"📦 Python deps OK: {', '.join(available_deps)}")
        
        if len(available_deps) < 5:
            logger.critical("❌ Missing Python dependencies!")
            logger.critical("   Install: pip install flask-cors MIDIUtil textblob pyphen pydub")
            sys.exit(1)

        # Check system executables
        fluidsynth_path = shutil.which('fluidsyn shutil.which('ffmpeg')
        
        logger.info(f"🔧 FluidSynth: {'✅ ' + fluidsynth_path if fluidsynth_path else '❌ Not found'}")
        logger.info(f"🔧 FFmpeg: {'✅ ' + ffmpeg_path if ffmpeg_path else '❌ Not found'}")
        
        if not fluidsynth_path:
            logger.critical("❌ Install FluidSynth: sudo apt update && sudo apt install fluidsynth libsndfile1")
            sys.exit(1)
        if not ffmpeg_path:
            logger.critical("❌ Install FFmpeg: sudo apt install ffmpeg")
            sys.exit(1)

        # Version check
        try:
            result = subprocess.run(['fluidsynth', '-v'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"📊 FluidSynth version: {result.stdout.strip()}")
            else:
                logger.warning("Tidak bisa cek versi FluidSynth")
        except:
            logger.warning("Tidak bisa cek versi FluidSynth")

        # Cleanup old files
        cleanup_old_files(AUDIO_OUTPUT_DIR)

        # Network info
        local_ip = get_local_ip()
        logger.info("🌐 Server ready:")
        logger.info(f"   🖥️  Local: http://127.0.0.1:5000")
        logger.info(f"   🌍 Network: http://{local_ip}:5000")
        logger.info("   🚀 Public: gunakan ngrok atau pinggy -p 5000")
        logger.info("   🛑 Stop: Ctrl+C")
        logger.info("   🔒 CORS enabled untuk development")

        # Start Flask server
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True,
            threaded=True,
            use_reloader=True
        )

    except KeyboardInterrupt:
        logger.info("\n👋 Server dihentikan oleh user (Ctrl+C)")
        sys.exit e:
        logger.critical(f"💥 Fatal startup error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main_app_runner()

