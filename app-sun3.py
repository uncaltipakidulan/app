import os
import sys
import time
import random
import logging
import hashlib
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from midiutil import MIDIFile
import subprocess
import tempfile
from textblob import TextBlob
import pyphen

# --- START KONFIGURASI APLIKASI ---
SOUNDFONT_PATH = Path(r'C:\Users\NM\SoundFonts\GeneralUser-GS-v1.471.sf2')
FLUIDSYNTH_EXE = "fluidsynth"
FFMPEG_EXE = "ffmpeg"
# --- END KONFIGURASI APLIKASI ---

# --- START REVISI WINDOWS 8.1: Unicode Handling & Logging ---
import io

def get_console_encoding():
    try:
        if sys.stdout.encoding:
            return sys.stdout.encoding.lower()
    except Exception:
        pass
    for enc in ['utf-8', 'cp65001', 'latin-1']:
        try:
            "test_string".encode(enc)
            return enc
        except LookupError:
            continue
    return 'latin-1'

CONSOLE_ENCODING = get_console_encoding()
if CONSOLE_ENCODING != 'utf-8':
    print(f"Peringatan: Konsol menggunakan encoding '{CONSOLE_ENCODING}'. Karakter Unicode mungkin tidak ditampilkan dengan benar.")

class WindowsSafeStreamHandler(logging.StreamHandler):
    def __init__(self, stream=None, encoding=None):
        if stream is None:
            stream = sys.stderr
        
        if encoding is None:
            encoding = CONSOLE_ENCODING

        if hasattr(stream, 'buffer') and hasattr(stream.buffer, 'write'):
            super().__init__(io.TextIOWrapper(stream.buffer, encoding=encoding, errors='replace'))
        else:
            super().__init__(stream)
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8', errors='replace'),
        WindowsSafeStreamHandler(sys.stdout, encoding=CONSOLE_ENCODING)
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"🚀 Memulai Flask Generate Instrumental (Python {sys.version.split()[0]} di {sys.platform})!")
# --- END REVISI WINDOWS 8.1 ---

try:
    import fluidsynth as pyfluidsynth_lib
    FLUIDSYNTH_BINDING_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_BINDING_AVAILABLE = False
    logger.warning("pyfluidsynth binding tidak ditemukan.")

from pydub import AudioSegment
from pydub.effects import compress_dynamic_range

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# ========== INSTRUMENTS DICTIONARY ==========
INSTRUMENTS = {
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3, 'Electric Piano 1': 4, 'Electric Piano 2': 5,
    'Harpsichord': 6, 'Clavinet': 7, 'Celesta': 8, 'Glockenspiel': 9,
    'Music Box': 10, 'Vibraphone': 11, 'Marimba': 12, 'Xylophone': 13,
    'Tubular Bells': 14, 'Dulcimer': 15, 'Drawbar Organ': 16, 'Percussive Organ': 17,
    'Rock Organ': 18, 'Church Organ': 19, 'Reed Organ': 20, 'Pipe Organ': 21,
    'Accordion': 22, 'Harmonica': 23, 'Tango Accordion': 24,
    'Nylon String Guitar': 25, 'Steel String Guitar': 26, 'Jazz Electric Guitar': 27,
    'Clean Electric Guitar': 28, 'Muted Electric Guitar': 29, 'Overdriven Guitar': 30,
    'Distortion Guitar': 31, 'Guitar Harmonics': 32, 'Acoustic Bass': 33,
    'Electric Bass finger': 34, 'Electric Bass pick': 35, 'Fretless Bass': 36,
    'Slap Bass 1': 37, 'Slap Bass 2': 38, 'Synth Bass 1': 39, 'Synth Bass 2': 40,
    'Violin': 41, 'Viola': 42, 'Cello': 43, 'Contrabass': 44, 'Tremolo Strings': 45,
    'Pizzicato Strings': 46, 'Orchestral Strings': 47, 'Timpani': 48,
    'String Ensemble 1': 49, 'String Ensemble 2': 50, 'Synth Strings 1': 51,
    'Synth Strings 2': 52, 'Choir Aahs': 53, 'Voice Oohs': 54, 'Synth Voice': 55,
    'Orchestra Hit': 56, 'Trumpet': 57, 'Trombone': 58, 'Tuba': 59, 'Muted Trumpet': 60,
    'French Horn': 61, 'Brass Section': 62, 'Synth Brass 1': 63, 'Synth Brass 2': 64,
    'Soprano Sax': 65, 'Alto Sax': 66, 'Tenor Sax': 67, 'Baritone Sax': 68,
    'Oboe': 69, 'English Horn': 70, 'Bassoon': 71, 'Clarinet': 72,
    'Piccolo': 73, 'Flute': 74, 'Recorder': 75, 'Pan Flute': 76,
    'Blown Bottle': 77, 'Shakuhachi': 78, 'Whistle': 79, 'Ocarina': 80,
    'Square Wave': 81, 'Sawtooth Wave': 82, 'Calliope Lead': 83, 'Chiff Lead': 84,
    'Charang': 85, 'Voice Lead': 86, 'Fifth Saw Wave': 87, 'Bass & Lead': 88,
    'New Age Pad': 89, 'Warm Pad': 90, 'Poly Synth Pad': 91, 'Choir Pad': 92,
    'Bowed Glass Pad': 93, 'Metallic Pad': 94, 'Halo Pad': 95, 'Sweep Pad': 96,
    'Rain': 97, 'Soundtrack': 98, 'Crystal': 99, 'Atmosphere': 100,
    'Brightness': 101, 'Goblins': 102, 'Echoes': 103, 'Sci-Fi': 104,
    'Sitar': 105, 'Banjo': 106, 'Shamisen': 107, 'Koto': 108,
    'Kalimba': 109, 'Bagpipe': 110, 'Fiddle': 111, 'Shanai': 112,
    'Tinkle Bell': 113, 'Agogo': 114, 'Steel Drums': 115, 'Woodblock': 116,
    'Taiko Drum': 117, 'Melodic Tom': 118, 'Synth Drum': 119, 'Reverse Cymbal': 120,
    'Guitar Fret Noise': 121, 'Breath Noise': 122, 'Seashore': 123, 'Bird Tweet': 124,
    'Telephone Ring': 125, 'Helicopter': 126, 'Applause': 127
}

# ========== MELODY INSTRUMENTS BY GENRE ==========
MELODY_INSTRUMENTS_BY_GENRE = {
    # Pop genres - saxophone, acoustic guitar, piano
    'pop': ['Soprano Sax', 'Alto Sax', 'Tenor Sax', 'Nylon String Guitar', 'Steel String Guitar', 'Clean Electric Guitar', 'Acoustic Grand Piano'],
    'poprock': ['Tenor Sax', 'Clean Electric Guitar', 'Nylon String Guitar', 'Acoustic Grand Piano'],
    'popwaltz': ['Flute', 'Violin', 'Nylon String Guitar', 'Acoustic Grand Piano'],
    'slow waltz': ['Flute', 'Violin', 'Cello', 'Acoustic Grand Piano'],
    'fast waltz': ['Flute', 'Violin', 'Nylon String Guitar', 'Acoustic Grand Piano'],
    
    # Rock genres - distortion guitar, organ, strings
    'rock': ['Distortion Guitar', 'Overdriven Guitar', 'Rock Organ', 'String Ensemble 1'],
    'rock 60\'s': ['Overdriven Guitar', 'Rock Organ', 'Hammond Organ', 'String Ensemble 1'],
    'rock 70\'s': ['Distortion Guitar', 'Overdriven Guitar', 'Rock Organ', 'String Ensemble 1'],
    'rock 80\'s': ['Overdriven Guitar', 'Distortion Guitar', 'Rock Organ', 'Synth Strings 1'],
    'hard rock': ['Distortion Guitar', 'Overdriven Guitar', 'Rock Organ'],
    'march rock': ['Distortion Guitar', 'Overdriven Guitar', 'Brass Section', 'Rock Organ'],
    
    # Metal genres - distortion guitar, organ
    'metal': ['Distortion Guitar', 'Overdriven Guitar', 'Rock Organ'],
    'progressive metal': ['Distortion Guitar', 'Overdriven Guitar', 'Synth Lead', 'Rock Organ'],
    
    # Ballad genres - violin, cello, acoustic guitar, piano
    'slow rock': ['Violin', 'Cello', 'Clean Electric Guitar', 'Nylon String Guitar', 'Acoustic Grand Piano'],
    'piano rock ballad': ['Acoustic Grand Piano', 'Violin', 'Cello', 'Nylon String Guitar'],
    'guitar rock ballad': ['Clean Electric Guitar', 'Nylon String Guitar', 'Violin', 'Acoustic Grand Piano'],
    
    # Jazz & Blues - saxophone, vibraphone, organ
    'jazz': ['Tenor Sax', 'Alto Sax', 'Soprano Sax', 'Vibraphone', 'Jazz Electric Guitar'],
    'blues': ['Tenor Sax', 'Harmonica', 'Vibraphone', 'Clean Electric Guitar'],
    
    # Latin - flute, brass, strings
    'latin': ['Flute', 'Pan Flute', 'Brass Section', 'Trumpet', 'Nylon String Guitar'],
    
    # Traditional - violin, strings, organ
    'dangdut': ['Violin', 'String Ensemble 1', 'Nylon String Guitar', 'Rock Organ'],
    
    # March - brass, organ
    'march': ['Brass Section', 'Trumpet', 'French Horn', 'Tuba', 'Rock Organ'],
    
    # Default fallback
    'default': ['Acoustic Grand Piano', 'Violin', 'Flute']
}

# ========== EFFECTS CONFIGURATION ==========
MELODY_EFFECTS = {
    # Saxophone effects - reverb, vibrato
    'Soprano Sax': {'reverb': 40, 'vibrato': 20, 'delay': 15},
    'Alto Sax': {'reverb': 35, 'vibrato': 25, 'delay': 10},
    'Tenor Sax': {'reverb': 45, 'vibrato': 30, 'delay': 20},
    'Baritone Sax': {'reverb': 50, 'vibrato': 15, 'delay': 25},
    
    # Guitar effects - delay, reverb
    'Nylon String Guitar': {'reverb': 30, 'vibrato': 10, 'delay': 25},
    'Steel String Guitar': {'reverb': 25, 'vibrato': 15, 'delay': 20},
    'Clean Electric Guitar': {'reverb': 20, 'vibrato': 20, 'delay': 30},
    'Overdriven Guitar': {'reverb': 15, 'vibrato': 25, 'delay': 35},
    'Distortion Guitar': {'reverb': 10, 'vibrato': 30, 'delay': 40},
    
    # String instruments - vibrato, reverb
    'Violin': {'reverb': 50, 'vibrato': 40, 'delay': 10},
    'Viola': {'reverb': 45, 'vibrato': 35, 'delay': 8},
    'Cello': {'reverb': 55, 'vibrato': 45, 'delay': 5},
    'String Ensemble 1': {'reverb': 60, 'vibrato': 30, 'delay': 15},
    
    # Woodwinds - reverb, vibrato
    'Flute': {'reverb': 40, 'vibrato': 20, 'delay': 15},
    'Pan Flute': {'reverb': 35, 'vibrato': 15, 'delay': 25},
    
    # Brass - reverb, vibrato
    'Brass Section': {'reverb': 30, 'vibrato': 25, 'delay': 10},
    'Trumpet': {'reverb': 25, 'vibrato': 30, 'delay': 8},
    'French Horn': {'reverb': 35, 'vibrato': 20, 'delay': 12},
    'Tuba': {'reverb': 40, 'vibrato': 15, 'delay': 5},
    
    # Percussion/Mallet - reverb
    'Vibraphone': {'reverb': 50, 'vibrato': 35, 'delay': 20},
    
    # Organ - reverb, delay
    'Rock Organ': {'reverb': 20, 'vibrato': 10, 'delay': 30},
    'Hammond Organ': {'reverb': 25, 'vibrato': 15, 'delay': 25},
    
    # Default effects
    'default': {'reverb': 30, 'vibrato': 20, 'delay': 15}
}

# ========== CHORDS DICTIONARY ==========
CHORDS = {
    'C': [60, 64, 67], 'C#': [61, 65, 68], 'Db': [61, 65, 68],
    'D': [62, 66, 69], 'D#': [63, 67, 70], 'Eb': [63, 67, 70],
    'E': [64, 68, 71], 'F': [65, 69, 72], 'F#': [66, 70, 73],
    'Gb': [66, 70, 73], 'G': [67, 71, 74], 'G#': [68, 72, 75],
    'Ab': [68, 72, 75], 'A': [69, 73, 76], 'A#': [70, 74, 77],
    'Bb': [70, 74, 77], 'B': [71, 75, 78],
    'Cm': [60, 63, 67], 'C#m': [61, 64, 68], 'Dm': [62, 65, 69],
    'D#m': [63, 66, 70], 'Em': [64, 67, 71], 'Fm': [65, 68, 72],
    'F#m': [66, 69, 73], 'Gm': [67, 70, 74], 'G#m': [68, 71, 75],
    'Am': [69, 72, 76], 'A#m': [70, 73, 77], 'Bm': [71, 74, 78],
    'C7': [60, 64, 67, 70], 'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74],
    'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77], 'A7': [69, 73, 76, 79],
    'B7': [71, 75, 78, 81], 'Cm7': [60, 63, 67, 70], 'Dm7': [62, 65, 69, 72],
    'Em7': [64, 67, 71, 74], 'Fm7': [65, 68, 72, 75], 'Gm7': [67, 70, 74, 77],
    'Am7': [69, 72, 76, 79], 'Bm7': [71, 74, 78, 81],
    'Cmaj7': [60, 64, 67, 71], 'Dmaj7': [62, 66, 69, 73], 'Emaj7': [64, 68, 71, 75],
    'Fmaj7': [65, 69, 72, 76], 'Gmaj7': [67, 71, 74, 78], 'Amaj7': [69, 73, 76, 80],
    'Bmaj7': [71, 75, 78, 82],
    'C9': [60, 64, 67, 70, 74], 'D9': [62, 66, 69, 72, 76], 'E9': [64, 68, 71, 74, 78],
    'F9': [65, 69, 72, 75, 79], 'G9': [67, 71, 74, 77, 81], 'A9': [69, 73, 76, 79, 83],
    'B9': [71, 75, 78, 81, 85],
    'Csus2': [60, 62, 67], 'Dsus2': [62, 64, 69], 'Esus2': [64, 66, 71],
    'Fsus2': [65, 67, 72], 'Gsus2': [67, 69, 74], 'Asus2': [69, 71, 76],
    'Bsus2': [71, 73, 78],
    'Csus4': [60, 65, 67], 'Dsus4': [62, 67, 69], 'Esus4': [64, 69, 71],
    'Fsus4': [65, 70, 72], 'Gsus4': [67, 72, 74], 'Asus4': [69, 74, 76],
    'Bsus4': [71, 76, 78],
    'Cdim': [60, 63, 66], 'Ddim': [62, 65, 68], 'Edim': [64, 67, 70],
    'Fdim': [65, 68, 71], 'Gdim': [67, 70, 73], 'Adim': [69, 72, 75],
    'Bdim': [71, 74, 77],
    'Caug': [60, 64, 68], 'Daug': [62, 66, 70], 'Eaug': [64, 68, 72],
    'Faug': [65, 69, 73], 'Gaug': [67, 71, 75], 'Aaug': [69, 73, 77],
    'Baug': [71, 75, 79],
}

# ========== SCALES DICTIONARY ==========
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 3, 5, 7, 10],
    'latin': [0, 2, 4, 5, 7, 9, 10],
    'dangdut': [0, 1, 4, 5, 7, 8, 11],
    'jazz': [0, 2, 4, 5, 7, 9, 10, 11],
    'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor': [0, 2, 3, 5, 7, 9, 11],
    'march': [0, 2, 4, 5, 7, 9, 11],
}

# ========== GENRE PARAMETERS ==========
GENRE_PARAMS = {
    'pop': {
        'tempo': 126, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': [],  # Will be populated from MELODY_INSTRUMENTS_BY_GENRE
            'harmony': ['String Ensemble 1', 'New Age Pad', 'Electric Piano 2'],
            'bass': ['Electric Bass finger', 'Acoustic Bass'],
            'rhythm': ['Clean Electric Guitar', 'Electric Piano 1'],
        },
        'drums_enabled': True, 
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['C', 'Em', 'F', 'G'], ['Am', 'F', 'C', 'G'],
            ['C', 'F', 'G', 'Am'], ['G', 'D', 'Em', 'C'], ['F', 'C', 'G', 'Am'],
            ['C', 'G', 'F', 'C'], ['Dm', 'G', 'C', 'Am'], ['C', 'Am', 'F', 'G'],
            ['Em', 'C', 'G', 'D']
        ],
        'duration_beats': 192,
        'mood': 'happy',
        'structure': ['intro', 'verse', 'pre-chorus', 'chorus', 'verse', 'pre-chorus', 'chorus', 'bridge', 'chorus', 'outro']
    },
    'rock': {
        'tempo': 135, 'key': 'E', 'scale': 'major',
        'instruments': {
            'melody': [],  # Will be populated from MELODY_INSTRUMENTS_BY_GENRE
            'harmony': ['Overdriven Guitar', 'Brass Section', 'Rock Organ'],
            'bass': ['Electric Bass pick', 'Fretless Bass'],
            'rhythm': ['Distortion Guitar', 'Overdriven Guitar'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['E', 'A', 'B', 'C#m'], ['E', 'G', 'A', 'B'], ['A', 'E', 'D', 'A'],
            ['E', 'D', 'A', 'E'], ['G', 'C', 'D', 'G'], ['C', 'F', 'G', 'C'],
            ['D', 'G', 'A', 'D'], ['A', 'D', 'E', 'A'], ['E', 'A', 'D', 'E'],
            ['G', 'D', 'Em', 'C']
        ],
        'duration_beats': 192,
        'mood': 'energetic',
        'structure': ['intro', 'verse', 'chorus', 'verse', 'chorus', 'bridge', 'guitar_solo', 'chorus', 'outro']
    },
    'march': {
        'tempo': 120, 'key': 'G', 'scale': 'march',
        'instruments': {
            'melody': [],  # Will be populated from MELODY_INSTRUMENTS_BY_GENRE
            'harmony': ['Brass Section', 'String Ensemble 1', 'French Horn'],
            'bass': ['Tuba', 'Contrabass'],
            'rhythm': ['Rock Organ', 'Pipe Organ'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['G', 'C', 'D', 'G'], ['G', 'D', 'Em', 'C'], ['C', 'G', 'Am', 'D'],
            ['D', 'G', 'C', 'D'], ['G', 'Em', 'Bm', 'D'], ['C', 'F', 'G', 'C'],
            ['D', 'G', 'A', 'D'], ['A', 'D', 'E', 'A'], ['E', 'A', 'B', 'E'],
            ['G', 'C', 'D', 'G']
        ],
        'duration_beats': 192,
        'mood': 'marching',
        'structure': ['intro', 'verse', 'chorus', 'verse', 'chorus', 'bridge', 'brass_solo', 'chorus', 'outro']
    },
    'default': {
        'tempo': 120, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': [],  # Will be populated from MELODY_INSTRUMENTS_BY_GENRE
            'harmony': ['String Ensemble 1'],
            'bass': ['Acoustic Bass'],
            'rhythm': ['Acoustic Grand Piano'],
        },
        'drums_enabled': True,
        'chord_progressions': [
            ['C', 'G', 'Am', 'F']
        ],
        'duration_beats': 128,
        'mood': 'neutral',
        'structure': ['intro', 'verse', 'chorus', 'verse', 'chorus', 'outro']
    }
}

# ========== FUNGSI UTAMA YANG DISEMPURNAKAN ==========

def detect_genre_from_lyrics(lyrics):
    """Deteksi genre dari lirik menggunakan keyword matching"""
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'party', 'fun', 'happy', 'tonight', 'forever', 'together', 'cinta', 'hati', 'mimpi'],
        'rock': ['rock', 'guitar', 'energy', 'power', 'fire', 'wild', 'roll', 'scream', 'freedom', 'bebas'],
        'march': ['march', 'marching', 'parade', 'military', 'brass', 'drum', 'soldier', 'victory', 'energetic']
    }
    
    blob = TextBlob(lyrics.lower())
    words = set(blob.words)
    
    scores = {genre: sum(1 for keyword in kw_list if keyword in words) 
              for genre, kw_list in keywords.items()}
    
    detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
    logger.info(f"Genre terdeteksi: '{detected_genre}'")
    return detected_genre

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    """Generate parameter musik berdasarkan genre dan analisis lirik"""
    genre_lower = genre.lower()
    
    if genre_lower not in GENRE_PARAMS:
        logger.warning(f"Genre '{genre}' tidak ditemukan, menggunakan default")
        params = GENRE_PARAMS['default'].copy()
        params['genre'] = genre
    else:
        params = GENRE_PARAMS[genre_lower].copy()
        params['genre'] = genre
    
    # Populate melody instruments from genre-specific list
    if 'melody' in params['instruments'] and not params['instruments']['melody']:
        melody_choices = MELODY_INSTRUMENTS_BY_GENRE.get(genre_lower, MELODY_INSTRUMENTS_BY_GENRE['default'])
        available_melody_instruments = [instr for instr in melody_choices if instr in INSTRUMENTS]
        if available_melody_instruments:
            params['instruments']['melody'] = random.choice(available_melody_instruments)
            logger.info(f"Melody instrument selected: {params['instruments']['melody']}")
        else:
            params['instruments']['melody'] = 'Acoustic Grand Piano'
            logger.warning("No valid melody instruments, using default")
    
    # Pilih chord progression secara acak
    if 'chord_progressions' in params and params['chord_progressions']:
        selected_progression = random.choice(params['chord_progressions'])
        params['chord_progression'] = selected_progression
        logger.info(f"Chord progression: {selected_progression}")
    else:
        params['chord_progression'] = ['C', 'G', 'Am', 'F']
    
    if user_tempo_input != 'auto':
        try:
            params['tempo'] = int(user_tempo_input)
            if not (60 <= params['tempo'] <= 200):
                params['tempo'] = GENRE_PARAMS.get(genre_lower, GENRE_PARAMS['default'])['tempo']
        except ValueError:
            params['tempo'] = GENRE_PARAMS.get(genre_lower, GENRE_PARAMS['default'])['tempo']
    
    # Analisis sentiment lirik
    blob = TextBlob(lyrics)
    sentiment = blob.sentiment.polarity
    
    if sentiment < -0.3:
        params['mood'] = 'sad'
        params['scale'] = 'minor'
    elif sentiment > 0.3:
        params['mood'] = 'happy'
        params['scale'] = 'major'
    
    # Pilih instrumen untuk kategori lainnya
    for category in ['harmony', 'bass', 'rhythm']:
        if category in params['instruments']:
            instrument_choices = params['instruments'][category]
            if isinstance(instrument_choices, list) and instrument_choices:
                available_instruments = [instr for instr in instrument_choices if instr in INSTRUMENTS]
                if available_instruments:
                    params['instruments'][category] = random.choice(available_instruments)
                else:
                    default_fallback = {
                        'harmony': 'String Ensemble 1', 
                        'bass': 'Acoustic Bass',
                        'rhythm': 'Acoustic Grand Piano'
                    }
                    params['instruments'][category] = default_fallback[category]
            else:
                params['instruments'][category] = instrument_choices

    # Set effects for melody instrument
    melody_instrument = params['instruments'].get('melody', 'Acoustic Grand Piano')
    params['melody_effects'] = MELODY_EFFECTS.get(melody_instrument, MELODY_EFFECTS['default'])
    
    # Konversi chord names ke MIDI notes
    base_chords = params['chord_progression']
    selected_chords = []
    for chord_name in base_chords:
        if chord_name in CHORDS:
            selected_chords.append(CHORDS[chord_name])
        else:
            selected_chords.append(CHORDS['C'])
    params['chords'] = selected_chords
    
    logger.info(f"Parameters: Tempo={params['tempo']}BPM, Mood={params['mood']}")
    logger.info(f"Instruments: Melody={params['instruments']['melody']}, Bass={params['instruments']['bass']}")
    
    return params

def get_scale_notes(key, scale_name):
    """Mengembalikan daftar not MIDI dari skala tertentu"""
    key_map = {'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63, 'E': 64, 
               'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68, 'Ab': 68, 'A': 69, 
               'A#': 70, 'Bb': 70, 'B': 71}
    root_midi = key_map.get(key, 60)
    
    scale_intervals = SCALES.get(scale_name, SCALES['major'])
    return [root_midi + interval for interval in scale_intervals]

def generate_melody_for_section(params, section_type, start_beat, duration_beats):
    """Generate melodi untuk section tertentu"""
    scale_notes = get_scale_notes(params['key'], params['scale'])
    melody = []
    
    # Pattern berdasarkan section type
    if section_type in ['intro', 'outro']:
        patterns = [[2, 2, 4], [4, 4, 8], [1, 1, 2, 2, 2]]
        velocities = [70, 80]
        note_range = [0, 2]
        
    elif section_type in ['verse']:
        patterns = [[1, 1, 0.5, 0.5, 2], [0.5, 0.5, 1, 1.5, 1], [1, 1, 2]]
        velocities = [60, 75]
        note_range = [0, 1, 2]
        
    elif section_type in ['pre-chorus']:
        patterns = [[0.5, 0.5, 1, 0.5, 0.5, 1], [1, 0.5, 0.5, 1, 1]]
        velocities = [75, 85]
        note_range = [1, 2, 3]
        
    elif section_type in ['chorus']:
        patterns = [[0.5, 0.5, 0.5, 0.5, 1, 1], [1, 1, 1, 1], [0.5, 0.5, 1, 0.5, 0.5, 1]]
        velocities = [85, 95]
        note_range = [2, 3, 4]
        
    elif section_type in ['bridge']:
        patterns = [[1, 2, 1, 2], [2, 1, 1, 2], [1, 1, 1, 1, 2]]
        velocities = [65, 80]
        note_range = [0, 1, 2]
        
    elif 'solo' in section_type:
        patterns = [[0.25, 0.25, 0.25, 0.25, 0.5, 0.5], [0.5, 0.25, 0.25, 1], [0.25, 0.25, 0.5, 0.25, 0.25, 0.5]]
        velocities = [90, 110]
        note_range = [1, 2, 3, 4]
        
    else:
        patterns = [[1, 1, 2], [0.5, 0.5, 1, 1]]
        velocities = [70, 85]
        note_range = [0, 1, 2]
    
    current_pattern = random.choice(patterns)
    current_velocity = random.choice(velocities)
    
    total_beats_generated = 0
    time_pos = start_beat
    
    while total_beats_generated < duration_beats:
        for beat_duration_segment in current_pattern:
            if total_beats_generated + beat_duration_segment > duration_beats:
                beat_duration_segment = duration_beats - total_beats_generated
                if beat_duration_segment <= 0.001: 
                    break

            if not scale_notes:
                return []
            
            note_idx = random.randint(0, len(scale_notes) - 1)
            octave_shift = random.choice(note_range) * 12
            pitch = scale_notes[note_idx] + octave_shift
            pitch = max(0, min(127, pitch))

            melody.append((pitch, time_pos, beat_duration_segment, current_velocity))
            time_pos += beat_duration_segment
            total_beats_generated += beat_duration_segment
            if total_beats_generated >= duration_beats:
                break
        
        if random.random() < 0.3:
            current_pattern = random.choice(patterns)
            current_velocity = random.choice(velocities)
            
    return melody

def generate_harmony_for_section(params, section_type, start_beat, duration_beats):
    """Generate harmoni untuk section tertentu"""
    chords = params['chords']
    harmony = []
    
    if not chords:
        return []

    # Tentukan chord progression berdasarkan section
    if section_type in ['intro', 'outro']:
        section_chords = chords[:2] * 2
    elif section_type in ['verse']:
        section_chords = chords
    elif section_type in ['pre-chorus']:
        section_chords = chords[-2:] + chords[:2]
    elif section_type in ['chorus']:
        section_chords = chords * 2
    elif section_type in ['bridge']:
        section_chords = chords[::-1]
    else:
        section_chords = chords

    chords_count = len(section_chords)
    chord_duration = duration_beats / chords_count

    velocity = 85 if section_type in ['chorus', 'solo'] else 75

    current_beat = start_beat
    for chord_notes in section_chords:
        for note in chord_notes:
            harmony.append((note, current_beat, chord_duration, velocity))
        current_beat += chord_duration
    
    return harmony

def generate_bass_for_section(params, section_type, start_beat, duration_beats):
    """Generate bass line untuk section tertentu"""
    chords = params['chords']
    bass_line = []

    if not chords:
        return []

    section_chords = chords
    chords_count = len(section_chords)
    chord_duration = duration_beats / chords_count

    velocity = 90 if section_type in ['chorus', 'solo'] else 80

    current_beat = start_beat
    for chord_notes in section_chords:
        root_note = chord_notes[0] - 24
        root_note = max(24, min(root_note, 48))
        
        bass_line.append((root_note, current_beat, chord_duration * 0.75, velocity))
        if chord_duration > 1:
            bass_line.append((root_note + 7, current_beat + chord_duration * 0.75, chord_duration * 0.25, velocity - 10))
        
        current_beat += chord_duration
            
    return bass_line

def generate_drums_for_section(params, section_type, start_beat, duration_beats):
    """Generate drum patterns untuk section tertentu"""
    drums = []
    genre = params['genre'].lower()
    
    for beat_pos in range(int(duration_beats)):
        absolute_beat = start_beat + beat_pos
        
        # Basic rock pattern
        if beat_pos % 4 == 0:
            drums.append((36, absolute_beat, 0.5, 110))
        if beat_pos % 4 == 2:
            drums.append((36, absolute_beat, 0.5, 100))
        if beat_pos % 2 == 1:
            drums.append((38, absolute_beat, 0.5, 95))
        
        # Hi-hat/cymbal
        drums.append((42, absolute_beat, 0.25, 75))

    return drums

def create_midi_file(params, output_path):
    """Buat file MIDI dengan struktur part lengkap"""
    tempo = params['tempo']
    structure = params.get('structure', ['intro', 'verse', 'chorus', 'verse', 'chorus', 'outro'])
    
    midi = MIDIFile(5, 120)  # 5 tracks: melody, harmony, bass, rhythm, drums
    
    for i in range(5):
        midi.addTempo(i, 0, tempo)
    
    # Setup instruments
    melody_instrument = params['instruments'].get('melody', 'Acoustic Grand Piano')
    harmony_instrument = params['instruments'].get('harmony', 'String Ensemble 1')
    bass_instrument = params['instruments'].get('bass', 'Acoustic Bass')
    rhythm_instrument = params['instruments'].get('rhythm', 'Acoustic Grand Piano')
    
    # Program changes
    midi.addProgramChange(0, 0, 0, INSTRUMENTS.get(melody_instrument, 0))
    midi.addProgramChange(1, 0, 0, INSTRUMENTS.get(harmony_instrument, 48))
    midi.addProgramChange(2, 0, 0, INSTRUMENTS.get(bass_instrument, 33))
    midi.addProgramChange(3, 0, 0, INSTRUMENTS.get(rhythm_instrument, 0))
    
    # Set panpot
    midi.addControllerEvent(0, 0, 0, 10, 64)  # Melody center
    midi.addControllerEvent(1, 0, 0, 10, 30)  # Harmony left
    midi.addControllerEvent(2, 0, 0, 10, 64)  # Bass center
    midi.addControllerEvent(3, 0, 0, 10, 90)  # Rhythm right
    midi.addControllerEvent(4, 0, 0, 10, 64)  # Drums center
    
    # Generate sections
    current_beat = 0.0
    section_duration = params['duration_beats'] / len(structure)
    
    for i, section in enumerate(structure):
        logger.info(f"Generating section: {section}")
        
        # Melody
        melody_notes = generate_melody_for_section(params, section, current_beat, section_duration)
        for pitch, time_pos, duration, velocity in melody_notes:
            midi.addNote(0, 0, pitch, time_pos, duration, int(velocity * 1.2))
        
        # Harmony
        harmony_notes = generate_harmony_for_section(params, section, current_beat, section_duration)
        for pitch, time_pos, duration, velocity in harmony_notes:
            midi.addNote(1, 0, pitch, time_pos, duration, int(velocity * 0.8))
        
        # Bass
        bass_notes = generate_bass_for_section(params, section, current_beat, section_duration)
        for pitch, time_pos, duration, velocity in bass_notes:
            midi.addNote(2, 0, pitch, time_pos, duration, int(velocity * 1.1))
        
        # Drums
        if params['drums_enabled']:
            drum_notes = generate_drums_for_section(params, section, current_beat, section_duration)
            for pitch, time_pos, duration, velocity in drum_notes:
                midi.addNote(4, 9, pitch, time_pos, duration, velocity)
        
        current_beat += section_duration

    try:
        with open(output_path, 'wb') as f:
            midi.writeFile(f)
        logger.info(f"MIDI generated: {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"Gagal menulis file MIDI: {e}")
        return False

def midi_to_audio_subprocess(midi_path, output_wav_path, soundfont_path):
    """Konversi MIDI ke WAV menggunakan FluidSynth"""
    try:
        cmd = [
            FLUIDSYNTH_EXE,
            '-F', str(output_wav_path), 
            '-r', '44100',
            '-ni',
            '-g', '1.0',
            str(soundfont_path),
            str(midi_path)
        ]
        
        logger.info(f"Converting MIDI to WAV: {midi_path.name}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, 
                              encoding=CONSOLE_ENCODING, errors='replace')
        
        if result.returncode == 0 and output_wav_path.exists():
            file_size = output_wav_path.stat().st_size / 1024
            logger.info(f"WAV generated: {output_wav_path.name} ({file_size:.1f} KB)")
            return True
        else:
            logger.error(f"FluidSynth error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout")
        return False
    except FileNotFoundError:
        logger.critical(f"FluidSynth tidak ditemukan: '{FLUIDSYNTH_EXE}'")
        return False
    except Exception as e:
        logger.error(f"Error FluidSynth: {e}")
        return False

def midi_to_audio(midi_path, output_wav_path):
    return midi_to_audio_subprocess(midi_path, output_wav_path, SOUNDFONT_PATH)

def wav_to_mp3(wav_path, mp3_path):
    """Konversi WAV ke MP3 dengan kompresi dan sub-bass"""
    try:
        logger.info(f"Converting WAV to MP3: {wav_path.name}")
        
        # Load WAV file
        audio = AudioSegment.from_wav(str(wav_path))
        
        # Pastikan audio memiliki durasi yang cukup
        if len(audio) < 1000:  # kurang dari 1 detik
            logger.warning("Audio terlalu pendek, menambahkan silence")
            silence = AudioSegment.silent(duration=3000)  # 3 detik silence
            audio = audio + silence
        
        # Apply compression
        try:
            audio = compress_dynamic_range(audio, threshold=-20.0, ratio=4.0)
        except Exception as e:
            logger.warning(f"Compression failed: {e}")
        
        # Boost bass frequencies
        try:
            bass_boosted = audio.low_pass_filter(120)
            audio = audio.overlay(bass_boosted - 10)
        except Exception as e:
            logger.warning(f"Bass boost failed: {e}")
        
        # Normalize audio
        try:
            audio = audio.normalize()
        except Exception as e:
            logger.warning(f"Normalization failed: {e}")
        
        # Export ke MP3
        audio.export(
            str(mp3_path), 
            format='mp3', 
            bitrate='192k'
        )
        
        # Verifikasi file berhasil dibuat
        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            file_size = mp3_path.stat().st_size / 1024
            logger.info(f"MP3 successfully generated: {mp3_path.name} ({file_size:.1f} KB)")
            return True
        else:
            logger.error("MP3 file creation failed")
            return False
        
    except Exception as e:
        logger.error(f"Error converting WAV to MP3: {e}")
        if shutil.which(FFMPEG_EXE) is None:
            logger.critical(f"FFmpeg tidak ditemukan: '{FFMPEG_EXE}'")
        return False

def cleanup_old_files(directory, max_age_hours=1):
    """Bersihkan file audio lama"""
    logger.info(f"Membersihkan file lama di {directory}")
    deleted_count = 0
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    for file_path in Path(directory).glob("*.{mp3,wav,mid}"):
        try:
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_time < cutoff_time:
                file_path.unlink()
                deleted_count += 1
        except Exception as e:
            logger.warning(f"Error menghapus {file_path.name}: {e}")
    
    logger.info(f"Pembersihan selesai. {deleted_count} file dihapus.")
    return deleted_count

def generate_unique_id(lyrics):
    """Generate unique ID berdasarkan hash lirik dan timestamp"""
    lyrics_for_hash = lyrics[:500]
    hash_object = hashlib.md5(lyrics_for_hash.encode('utf-8')).hexdigest()
    timestamp = str(int(time.time()))
    return f"{hash_object[:8]}_{timestamp}"

# ========== ROUTES ==========

@app.route('/')
def index():
    """Serve HTML interface"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Generate Instrumental - Music Creator</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; color: #333; }
            h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
            p { text-align: center; color: #555; margin-bottom: 25px; }
            form { background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
            label { display: block; margin-bottom: 8px; font-weight: bold; color: #34495e; }
            textarea { width: calc(100% - 22px); height: 180px; margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; resize: vertical; }
            select, input[type="number"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; background-color: #f9f9f9; }
            input[type="number"] { width: 150px; display: inline-block; margin-right: 10px; }
            small { color: #7f8c8d; font-size: 0.9em; }
            button { background: #3498db; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 18px; font-weight: bold; display: block; width: 100%; transition: background-color 0.3s ease; }
            button:hover { background: #2980b9; }
            .result { margin-top: 30px; padding: 25px; background: #e8f6f3; border-radius: 8px; border: 1px solid #d1eeea; text-align: center; }
            .result h3 { color: #2c3e50; margin-bottom: 15px; }
            .result p { margin: 8px 0; color: #444; }
            audio { width: 100%; margin: 20px 0; border-radius: 5px; }
            #status { font-style: italic; color: #666; }
            #downloadLink a { color: #2ecc71; text-decoration: none; font-weight: bold; }
            #downloadLink a:hover { text-decoration: underline; }
            .error-message { color: #e74c3c; font-weight: bold; }
            .success-message { color: #27ae60; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🎵 Generate Instrumental Music</h1>
        <p>Masukkan lirik lagu Anda dan pilih genre untuk generate musik instrumental otomatis!</p>
        
        <form id="musicForm">
            <label for="lyrics">Lirik Lagu (1-2000 karakter):</label><br>
            <textarea id="lyrics" name="lyrics" placeholder="Masukkan lirik lagu Anda di sini..." 
                      minlength="3" maxlength="2000" required></textarea><br>
            
            <label for="genre">Genre Musik:</label><br>
            <select id="genre" name="genre">
                <option value="auto">Auto-Detect</option>
                <option value="pop">Pop</option>
                <option value="rock">Rock</option>
                <option value="march">March</option>
            </select><br>
            
            <label for="tempo">Tempo (BPM):</label><br>
            <input type="number" id="tempo" name="tempo" min="60" max="200" placeholder="Auto">
            <small>(Kosongkan untuk auto-detect)</small><br><br>
            
            <button type="submit">🎼 Generate Musik! (Min. 3 menit)</button>
        </form>
        
        <div id="result" class="result" style="display: none;">
            <h3>Hasil Generasi:</h3>
            <div id="status"></div>
            <audio id="audioPlayer" controls style="display: none;"></audio>
            <div id="downloadLink"></div>
        </div>

        <script>
            document.getElementById('musicForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData();
                formData.append('lyrics', document.getElementById('lyrics').value);
                formData.append('genre', document.getElementById('genre').value);
                
                let tempoValue = document.getElementById('tempo').value;
                if (tempoValue === '' || isNaN(parseInt(tempoValue))) {
                    formData.append('tempo', 'auto');
                } else {
                    formData.append('tempo', parseInt(tempoValue));
                }
                
                const resultDiv = document.getElementById('result');
                const statusDiv = document.getElementById('status');
                const audioPlayer = document.getElementById('audioPlayer');
                const downloadLink = document.getElementById('downloadLink');
                
                resultDiv.style.display = 'block';
                statusDiv.innerHTML = '<p class="success-message">⏳ Sedang generate musik... Ini mungkin memakan waktu 1-2 menit.</p>';
                audioPlayer.style.display = 'none';
                downloadLink.innerHTML = '';
                
                try {
                    const response = await fetch('/generate-instrumental', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        statusDiv.innerHTML = `<p class="success-message">✅ Musik berhasil digenerate!</p>
                                             <p><strong>Genre:</strong> ${data.genre}</p>
                                             <p><strong>Tempo:</strong> ${data.tempo} BPM</p>
                                             <p><strong>Durasi:</strong> ${data.duration} detik</p>`;
                        
                        audioPlayer.src = `/static/audio_output/${data.filename}`;
                        audioPlayer.style.display = 'block';
                        audioPlayer.load();
                        
                        downloadLink.innerHTML = `<p><a href="/static/audio_output/${data.filename}" download="${data.filename}">💾 Download MP3</a></p>`;
                    } else {
                        const errorData = await response.json();
                        statusDiv.innerHTML = `<p class="error-message">❌ Error: ${errorData.error || 'Gagal generate musik'}</p>`;
                    }
                } catch (error) {
                    statusDiv.innerHTML = `<p class="error-message">❌ Network Error: ${error.message}</p>`;
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/generate-instrumental', methods=['POST'])
def generate_instrumental_endpoint():
    """Endpoint utama untuk generate instrumental"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
            
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto').lower()
        tempo_input = data.get('tempo', 'auto')
        
        # Validasi input
        if not lyrics:
            return jsonify({'error': 'Lirik tidak boleh kosong.'}), 400
        
        if len(lyrics) < 3:
            return jsonify({'error': 'Lirik minimal 3 karakter.'}), 400
            
        if len(lyrics) > 2000:
            return jsonify({'error': 'Lirik maksimal 2000 karakter.'}), 400
        
        logger.info(f"Memproses lirik: '{lyrics[:100]}...' (panjang: {len(lyrics)} karakter)")
        
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Pastikan durasi minimal 3 menit (180 detik)
        min_beats = 180 * params['tempo'] / 60
        if params['duration_beats'] < min_beats:
            params['duration_beats'] = min_beats
            logger.info(f"Menyesuaikan durasi menjadi {params['duration_beats']} beats untuk durasi minimal 3 menit")
        
        unique_id = generate_unique_id(lyrics)
        midi_filename = f"{unique_id}.mid"
        wav_filename = f"{unique_id}.wav"
        mp3_filename = f"{unique_id}.mp3"
        
        midi_path = AUDIO_OUTPUT_DIR / midi_filename
        wav_path = AUDIO_OUTPUT_DIR / wav_filename
        mp3_path = AUDIO_OUTPUT_DIR / mp3_filename
        
        logger.info(f"Memulai generasi musik untuk ID: {unique_id}")
        
        # Step 1: Generate MIDI
        if not create_midi_file(params, midi_path):
            return jsonify({'error': 'Gagal membuat file MIDI.'}), 500
        
        # Step 2: Convert MIDI to WAV
        if not midi_to_audio(midi_path, wav_path):
            if midi_path.exists():
                midi_path.unlink()
            return jsonify({'error': 'Gagal konversi MIDI ke WAV.'}), 500
        
        # Step 3: Convert WAV to MP3
        if not wav_to_mp3(wav_path, mp3_path):
            if wav_path.exists():
                wav_path.unlink()
            if midi_path.exists():
                midi_path.unlink()
            return jsonify({'error': 'Gagal konversi audio ke MP3.'}), 500
        
        # Hitung durasi sebenarnya
        duration_seconds = params['duration_beats'] * 60 / params['tempo']
        try:
            if mp3_path.exists():
                audio = AudioSegment.from_mp3(mp3_path)
                duration_seconds = len(audio) / 1000
        except Exception as e:
            logger.warning(f"Gagal mendapatkan durasi akurat: {e}")
            
        # Cleanup temporary files
        if midi_path.exists():
            midi_path.unlink()
        if wav_path.exists():
            wav_path.unlink()
        
        logger.info(f"Generasi selesai untuk ID {unique_id}. File: {mp3_filename}")
        
        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'audio_url': f'/static/audio_output/{mp3_filename}',
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration_seconds, 1),
            'id': unique_id
        })
        
    except Exception as e:
        logger.error(f"Error saat generasi instrumental: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve file audio"""
    try:
        file_path = AUDIO_OUTPUT_DIR / filename
        if not file_path.exists():
            return "File not found", 404
        
        mimetype = 'audio/mpeg' if filename.endswith('.mp3') else 'audio/wav'
        return send_from_directory(AUDIO_OUTPUT_DIR, filename, mimetype=mimetype)
        
    except Exception as e:
        logger.error(f"Error serving audio {filename}: {e}")
        return "Internal server error", 500

def main_app_runner():
    """Fungsi utama untuk start server"""
    try:
        # Cek dependencies
        actual_fluidsynth_path = shutil.which(FLUIDSYNTH_EXE)
        actual_ffmpeg_path = shutil.which(FFMPEG_EXE)

        logger.info(f"FluidSynth: '{actual_fluidsynth_path or 'TIDAK DITEMUKAN'}'")
        logger.info(f"FFmpeg: '{actual_ffmpeg_path or 'TIDAK DITEMUKAN'}'")
        logger.info(f"SoundFont: '{SOUNDFONT_PATH}'")

        if not SOUNDFONT_PATH.exists():
            logger.critical(f"SoundFont tidak ditemukan: {SOUNDFONT_PATH}")
            sys.exit(1)

        if not actual_fluidsynth_path:
            logger.critical(f"FluidSynth tidak ditemukan: '{FLUIDSYNTH_EXE}'")
            sys.exit(1)
        
        if not actual_ffmpeg_path:
            logger.warning(f"FFmpeg tidak ditemukan: '{FFMPEG_EXE}' - konversi MP3 mungkin gagal")

        cleanup_old_files(AUDIO_OUTPUT_DIR)
        
        logger.info("Server berjalan di http://127.0.0.1:5000")
        logger.info("CTRL+C untuk menghentikan server.")
        
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("Server dihentikan oleh user")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Error fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main_app_runner()
