import os
import sys
import time
import random
import logging
import hashlib
import shutil
import math
import re
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
from pydub.generators import Sine, Sawtooth, Square, Pulse

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

# Keywords filter untuk konten asusila
INAPPROPRIATE_KEYWORDS = [
    'porn', 'sex', 'xxx', 'adult', 'nude', 'fuck', 'shit', 'asshole', 'bitch', 'bastard',
    'dick', 'pussy', 'whore', 'slut', 'cunt', 'nigga', 'nigger', 'rape', 'pedophile',
    'hentai', 'incest', 'bestiality', 'scat', 'violence', 'gore', 'murder', 'kill',
    'terrorist', 'bomb', 'drugs', 'cocaine', 'heroin', 'meth', 'weed', 'marijuana',
    'suicide', 'selfharm', 'abuse', 'harassment', 'racist', 'nazi', 'hitler'
]

# ==================== KONSTANTA YANG DIPERLUKAN ====================

# Drum mapping constants
DRUM_NOTES = {
    'bass_drum': 36,
    'snare': 38,
    'closed_hihat': 42,
    'open_hihat': 46,
    'crash_cymbal': 49,
    'ride_cymbal': 51,
    'china_cymbal': 52,
    'high_tom': 50,
    'mid_tom': 47,
    'low_tom': 45,
    'floor_tom': 41,
    'cowbell': 56,
    'tambourine': 54,
    'claves': 75,
    'agogo': 67,
    'cabasa': 69,
    'whistle': 71,
    'guiro': 73,
    'cuica': 78,
    'taiko': 64,
    'melodic_tom': 65,
    'synth_drum': 77,
    'reverse_cymbal': 55,
    'electronic_snare': 40,
    'electronic_tom': 43,
    'electronic_bass': 35
}

# Section timing untuk struktur lagu
SECTION_TIMING = {
    'intro': (0, 8),
    'verse': (8, 24),
    'pre_chorus': (24, 32),
    'chorus': (32, 48),
    'verse2': (48, 64),
    'pre_chorus2': (64, 72),
    'chorus2': (72, 88),
    'bridge': (88, 104),
    'solo': (104, 120),
    'chorus3': (120, 136),
    'outro': (136, 144)
}

# Staccato settings
STACCATO_DURATION_FACTOR = 0.3

# Outro patterns
OUTRO_PATTERNS = {
    'fade': 'fade_out',
    'intro': 'back_to_intro', 
    'descending': 'descending',
    'abrupt': 'abrupt'
}

# General MIDI Instruments
INSTRUMENTS = {
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3, 'Electric Piano 1': 4, 'Electric Piano 2': 5,
    'Harpsichord': 6, 'Clavinet': 7, 'Celesta': 8, 'Glockenspiel': 9,
    'Music Box': 10, 'Vibraphone': 11, 'Marimba': 12, 'Xylophone': 13,
    'Tubular Bells': 14, 'Dulcimer': 15, 'Drawbar Organ': 16, 'Percussive Organ': 17,
    'Rock Organ': 18, 'Church Organ': 19, 'Reed Organ': 20, 'Pipe Organ': 21,
    'Nylon String Guitar': 24, 'Steel String Guitar': 25, 'Jazz Electric Guitar': 26,
    'Clean Electric Guitar': 27, 'Muted Electric Guitar': 28, 'Overdriven Guitar': 29,
    'Distortion Guitar': 30, 'Guitar Harmonics': 31, 'Acoustic Bass': 32,
    'Electric Bass finger': 33, 'Electric Bass pick': 34, 'Fretless Bass': 35,
    'Slap Bass 1': 36, 'Slap Bass 2': 37, 'Synth Bass 1': 38, 'Synth Bass 2': 39,
    'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43,
    'Tremolo Strings': 44, 'Pizzicato Strings': 45, 'Orchestral Strings': 46,
    'String Ensemble 1': 48, 'String Ensemble 2': 49, 'Synth Strings 1': 50,
    'Synth Strings 2': 51, 'Choir Aahs': 52, 'Voice Oohs': 53, 'Synth Voice': 54,
    'Orchestra Hit': 55, 'Trumpet': 56, 'Trombone': 57, 'Tuba': 58,
    'Muted Trumpet': 59, 'French Horn': 60, 'Brass Section': 61, 'Synth Brass 1': 62,
    'Synth Brass 2': 63, 'Soprano Sax': 64, 'Alto Sax': 65, 'Tenor Sax': 66,
    'Baritone Sax': 67, 'Oboe': 68, 'English Horn': 69, 'Bassoon': 70,
    'Clarinet': 71, 'Piccolo': 72, 'Flute': 73, 'Recorder': 74,
    'Pan Flute': 75, 'Blown Bottle': 76, 'Shakuhachi': 77, 'Whistle': 78,
    'Ocarina': 79, 'Square Wave': 80, 'Sawtooth Wave': 81, 'Calliope Lead': 82,
    'Chiff Lead': 83, 'Charang': 84, 'Voice Lead': 85, 'Fifth Saw Wave': 86,
    'Bass & Lead': 87, 'New Age Pad': 88, 'Warm Pad': 89, 'Poly Synth Pad': 90,
    'Choir Pad': 91, 'Bowed Glass Pad': 92, 'Metallic Pad': 93, 'Halo Pad': 94,
    'Sweep Pad': 95, 'Sitar': 104, 'Banjo': 105, 'Shamisen': 106, 'Koto': 107,
    'Kalimba': 108, 'Bagpipe': 109, 'Fiddle': 110, 'Shanai': 111,
    'Guitar Fret Noise': 120, 'Breath Noise': 121, 'Seashore': 122, 'Bird Tweet': 123,
    'Telephone Ring': 124, 'Helicopter': 125, 'Applause': 126, 'Gunshot': 127,
    'Gamelan': 114, 'Kendang': 115, 'Suling': 75, 'Rebab': 110,
    'Talempong': 14, 'Gambus': 25, 'Mandolin': 27, 'Harmonica': 22,
    'Oud': 25, 'Erhu': 110, 'Pipa': 107, 'Guzheng': 107, 'Dagu': 115,
    'Tabla': 115, 'Janggu': 115, 'Kendang': 115, 'Darbuka': 115, 'Bendir': 115,
    'Tombak': 115, 'Bandoneon': 22, 'Accordion': 22
}

# Chords (MIDI note numbers, C4 = 60)
CHORDS = {
    'C': [60, 64, 67], 'C#': [61, 65, 68], 'Db': [61, 65, 68],
    'D': [62, 66, 69], 'D#': [63, 67, 70], 'Eb': [63, 67, 70],
    'E': [64, 68, 71], 'F': [65, 69, 72], 'F#': [66, 70, 73],
    'Gb': [66, 70, 73], 'G': [67, 71, 74], 'G#': [68, 72, 75],
    'Ab': [68, 72, 75], 'A': [69, 73, 76], 'A#': [70, 74, 77],
    'Bb': [70, 74, 77], 'B': [71, 75, 78], 'Cm': [60, 63, 67],
    'C#m': [61, 64, 68], 'Dm': [62, 65, 69], 'D#m': [63, 66, 70],
    'Em': [64, 67, 71], 'Fm': [65, 68, 72], 'F#m': [66, 69, 73],
    'Gm': [67, 70, 74], 'G#m': [68, 71, 75], 'Am': [69, 72, 76],
    'A#m': [70, 73, 77], 'Bm': [71, 74, 78], 'C7': [60, 64, 67, 70],
    'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74], 'F7': [65, 69, 72, 75],
    'G7': [67, 71, 74, 77], 'A7': [69, 73, 76, 79], 'B7': [71, 75, 78, 82],
    'Cm7': [60, 63, 67, 70], 'Dm7': [62, 65, 69, 72], 'Em7': [64, 67, 71, 74],
    'Fm7': [65, 68, 72, 75], 'Gm7': [67, 70, 74, 77], 'Am7': [69, 72, 76, 79],
    'Bbmaj7': [70, 74, 77, 81], 'Cmaj7': [60, 64, 67, 71], 'Dmaj7': [62, 66, 69, 73],
    'Emaj7': [64, 68, 71, 75], 'Fmaj7': [65, 69, 72, 76], 'Gmaj7': [67, 71, 74, 78],
    'Amaj7': [69, 73, 76, 80], 'Ebmaj7': [63, 67, 70, 74], 'Hm': [71, 74, 78],
    # Power chords untuk metal
    'C5': [60, 67], 'D5': [62, 69], 'E5': [64, 71], 'F5': [65, 72],
    'G5': [67, 74], 'A5': [69, 76], 'B5': [71, 78], 'Eb5': [63, 70]
}

# Scales (intervals from root note)
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'locrian': [0, 1, 3, 5, 6, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'latin': [0, 2, 4, 5, 7, 9, 10],
    'dangdut': [0, 1, 4, 5, 7, 8, 11],
    'arabic': [0, 1, 4, 5, 7, 8, 11],
    'japanese': [0, 1, 5, 7, 8],
    'indian': [0, 1, 4, 5, 7, 8, 11],
    'chinese': [0, 2, 4, 7, 9],
    'pelog': [0, 1, 3, 7, 8],
    'slendro': [0, 2, 5, 7, 9],
    'persian': [0, 1, 4, 5, 6, 8, 11],
    'makam': [0, 1, 4, 5, 7, 8, 10]
}

# Chord progressions berdasarkan genre
CHORD_PROGRESSIONS_BY_GENRE = {
    'pop': [['C', 'G', 'Am', 'F'], ['G', 'D', 'Em', 'C'], ['D', 'A', 'Bm', 'G']],
    'rock': [['C', 'F', 'G'], ['G', 'C', 'D'], ['A', 'D', 'E']],
    'metal': [['C5', 'G5', 'A5', 'F5'], ['D5', 'A5', 'B5', 'G5']],
    'jazz': [['Dm7', 'G7', 'Cmaj7'], ['Em7', 'A7', 'Dmaj7']],
    'latin': [['Am', 'D7', 'Gmaj7', 'Cmaj7'], ['G', 'Bm', 'Em', 'A7']],
    'japan': [['Dm', 'G', 'C', 'Am'], ['Em', 'Am', 'Dm', 'G']],
    'china': [['G', 'C', 'D', 'G'], ['Am', 'Dm', 'G', 'C']],
    'india': [['C', 'G', 'Am', 'F'], ['Dm', 'G', 'C', 'Am']],
    'korea': [['C', 'G', 'Am', 'F'], ['D', 'A', 'Bm', 'G']],
    'indonesia': [['G', 'C', 'D', 'G'], ['Am', 'Dm', 'G', 'C']],
    'afrobeat': [['F', 'C', 'G', 'F'], ['Gm', 'F', 'Eb', 'F']],
    'soukous': [['C', 'F', 'G', 'C'], ['Dm', 'G', 'C', 'Am']],
    'highlife': [['G', 'C', 'D', 'G'], ['Am', 'Dm', 'G', 'C']],
    'reggae': [['G', 'C', 'D', 'G'], ['Am', 'Dm', 'G', 'C']],
    'salsa': [['C', 'F', 'G', 'C'], ['Dm', 'G', 'C', 'Am']],
    'samba': [['D', 'G', 'A', 'D'], ['Em', 'A', 'D', 'Bm']],
    'celtic': [['Dm', 'G', 'C', 'F'], ['Em', 'Am', 'Dm', 'G']],
    'flamenco': [['Am', 'G', 'F', 'E'], ['Dm', 'C', 'Bb', 'Am']],
    'balkan': [['Em', 'D', 'C', 'B'], ['Am', 'G', 'F', 'E']],
    'arabic': [['C', 'F', 'G', 'C'], ['Dm', 'G', 'C', 'Am']],
    'turkish': [['Hm', 'G', 'F', 'E'], ['Am', 'G', 'F', 'E']],
    'persian': [['C', 'F', 'G', 'C'], ['Dm', 'G', 'C', 'Am']]
}

# GENRE PARAMS STANDARD (sebelum ditambah genre dunia)
GENRE_PARAMS = {
    'pop': {
        'tempo': 126, 'key': 'A', 'scale': 'major',
        'instruments': {
            'rhythm': 'Acoustic Grand Piano',
            'harmony': 'Warm Pad',
            'melody': 'Overdriven Guitar',
            'bass': 'Electric Bass finger',
        },
        'drums_enabled': True,
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['pop'],
        'sub_genres': {
            'synthpop': {'tempo': 128},
            'indiepop': {'tempo': 122},
            'electropop': {'tempo': 130},
        },
        'time_signatures': ['4/4'],
        'duration_beats': 240,
        'mood': 'happy',
        'bass_pattern': 'half_notes'
    },
    'rock': {
        'tempo': 135, 'key': 'A', 'scale': 'major',
        'instruments': {
            'rhythm': 'Overdriven Guitar',
            'harmony': 'String Ensemble 1',
            'melody': 'Overdriven Guitar',
            'bass': 'Electric Bass pick',
        },
        'drums_enabled': True,
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['rock'],
        'sub_genres': {
            'classic': {'tempo': 130},
            'alternative': {'tempo': 125},
            'punk': {'tempo': 180},
        },
        'time_signatures': ['4/4'],
        'duration_beats': 240,
        'mood': 'energetic',
        'bass_pattern': 'half_notes'
    },
    'metal': {
        'tempo': 160, 'key': 'A', 'scale': 'minor',
        'instruments': {
            'rhythm': 'Overdriven Guitar',
            'harmony': 'String Ensemble 1',
            'melody': 'Overdriven Guitar',
            'bass': 'Electric Bass pick',
        },
        'drums_enabled': True,
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['metal'],
        'sub_genres': {
            'thrash': {'tempo': 180},
            'death': {'tempo': 170},
            'black': {'tempo': 165},
        },
        'time_signatures': ['4/4'],
        'duration_beats': 240,
        'mood': 'intense',
        'bass_pattern': 'half_notes'
    },
    'jazz': {
        'tempo': 140, 'key': 'C', 'scale': 'dorian',
        'instruments': {
            'rhythm': 'Electric Piano 1',
            'harmony': 'Drawbar Organ',
            'melody': 'Tenor Sax',
            'bass': 'Electric Bass finger',
        },
        'drums_enabled': True,
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['jazz'],
        'sub_genres': {
            'bebop': {'tempo': 200},
            'swing': {'tempo': 180},
            'cool': {'tempo': 130},
        },
        'time_signatures': ['4/4'],
        'duration_beats': 240,
        'mood': 'sophisticated',
        'bass_pattern': 'walking'
    },
    'latin': {
        'tempo': 120, 'key': 'G', 'scale': 'latin',
        'instruments': {
            'rhythm': 'Acoustic Grand Piano',
            'harmony': 'Warm Pad',
            'melody': 'Overdriven Guitar',
            'bass': 'Acoustic Bass',
        },
        'drums_enabled': True,
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['latin'],
        'sub_genres': {
            'salsa': {'tempo': 180},
            'bossa': {'tempo': 130},
            'tango': {'tempo': 120},
        },
        'time_signatures': ['4/4'],
        'duration_beats': 240,
        'mood': 'rhythmic',
        'bass_pattern': 'latin'
    }
}

# Hi-hat volume dan ritme berdasarkan section dan genre
HI_HAT_VOLUMES_BY_GENRE = {
    'rock': {
        'intro': {'closed': 90, 'open': 95, 'pattern': 'steady_8th'},
        'verse': {'closed': 85, 'open': 90, 'pattern': 'steady_8th'},
        'pre_chorus': {'closed': 95, 'open': 100, 'pattern': 'steady_16th'},
        'chorus': {'closed': 100, 'open': 110, 'pattern': 'accented_8th'},
        'bridge': {'closed': 80, 'open': 85, 'pattern': 'steady_8th'},
        'solo': {'closed': 95, 'open': 100, 'pattern': 'steady_16th'},
        'outro': {'closed': 70, 'open': 75, 'pattern': 'fade_8th'}
    }
}

# Fill patterns untuk setiap genre
FILL_PATTERNS = {
    'pop': [
        [(DRUM_NOTES['snare'], 0.0), (DRUM_NOTES['high_tom'], 0.25), (DRUM_NOTES['mid_tom'], 0.5), (DRUM_NOTES['crash_cymbal'], 0.75)],
    ],
    'rock': [
        [(DRUM_NOTES['snare'], 0.0), (DRUM_NOTES['high_tom'], 0.125), (DRUM_NOTES['mid_tom'], 0.25), (DRUM_NOTES['floor_tom'], 0.375), (DRUM_NOTES['crash_cymbal'], 0.5)],
    ]
}

# ==================== KONSTANTA BARU UNTUK GENRE DUNIA ====================

# Default instrument mapping berdasarkan genre dunia
DEFAULT_INSTRUMENTS_WORLD = {
    'japan': {
        'rhythm': 'Koto',
        'harmony': 'Shakuhachi',
        'melody': 'Koto',
        'bass': 'Taiko'
    },
    'china': {
        'rhythm': 'Guzheng',
        'harmony': 'Erhu',
        'melody': 'Pipa',
        'bass': 'Dagu'
    },
    'india': {
        'rhythm': 'Sitar',
        'harmony': 'Tambura',
        'melody': 'Sitar',
        'bass': 'Tabla'
    },
    'korea': {
        'rhythm': 'Gayageum',
        'harmony': 'Daegeum',
        'melody': 'Haegeum',
        'bass': 'Janggu'
    },
    'indonesia': {
        'rhythm': 'Gamelan',
        'harmony': 'Suling',
        'melody': 'Rebab',
        'bass': 'Kendang'
    },
    'afrobeat': {
        'rhythm': 'Electric Piano 1',
        'harmony': 'Brass Section',
        'melody': 'Tenor Sax',
        'bass': 'Slap Bass 1'
    },
    'soukous': {
        'rhythm': 'Nylon String Guitar',
        'harmony': 'Brass Section',
        'melody': 'Trumpet',
        'bass': 'Fretless Bass'
    },
    'highlife': {
        'rhythm': 'Acoustic Grand Piano',
        'harmony': 'String Ensemble 1',
        'melody': 'Trumpet',
        'bass': 'Electric Bass finger'
    },
    'reggae': {
        'rhythm': 'Electric Piano 1',
        'harmony': 'Drawbar Organ',
        'melody': 'Steel String Guitar',
        'bass': 'Electric Bass finger'
    },
    'salsa': {
        'rhythm': 'Acoustic Grand Piano',
        'harmony': 'Brass Section',
        'melody': 'Trumpet',
        'bass': 'Acoustic Bass'
    },
    'samba': {
        'rhythm': 'Acoustic Grand Piano',
        'harmony': 'String Ensemble 1',
        'melody': 'Flute',
        'bass': 'Acoustic Bass'
    },
    'celtic': {
        'rhythm': 'Acoustic Grand Piano',
        'harmony': 'String Ensemble 1',
        'melody': 'Fiddle',
        'bass': 'Acoustic Bass'
    },
    'flamenco': {
        'rhythm': 'Nylon String Guitar',
        'harmony': 'Nylon String Guitar',
        'melody': 'Nylon String Guitar',
        'bass': 'Acoustic Bass'
    },
    'balkan': {
        'rhythm': 'Accordion',
        'harmony': 'String Ensemble 1',
        'melody': 'Clarinet',
        'bass': 'Acoustic Bass'
    },
    'arabic': {
        'rhythm': 'Oud',
        'harmony': 'Ney',
        'melody': 'Violin',
        'bass': 'Darbuka'
    },
    'turkish': {
        'rhythm': 'Oud',
        'harmony': 'Kanun',
        'melody': 'Ney',
        'bass': 'Bendir'
    },
    'persian': {
        'rhythm': 'Santur',
        'harmony': 'Tar',
        'melody': 'Ney',
        'bass': 'Tombak'
    }
}

# Drum kit mapping untuk setiap genre
DRUM_KITS_BY_GENRE = {
    'pop': ['bass_drum', 'snare', 'closed_hihat', 'open_hihat', 'crash_cymbal', 'ride_cymbal'],
    'rock': ['bass_drum', 'snare', 'closed_hihat', 'open_hihat', 'crash_cymbal', 'ride_cymbal', 'china_cymbal'],
    'metal': ['bass_drum', 'snare', 'closed_hihat', 'open_hihat', 'crash_cymbal', 'china_cymbal'],
    'jazz': ['bass_drum', 'snare', 'closed_hihat', 'ride_cymbal', 'crash_cymbal'],
    'latin': ['bass_drum', 'snare', 'closed_hihat', 'cowbell', 'tambourine', 'claves', 'agogo'],
    'salsa': ['bass_drum', 'snare', 'closed_hihat', 'cowbell', 'tambourine', 'claves', 'cabasa'],
    'samba': ['bass_drum', 'snare', 'closed_hihat', 'cowbell', 'tambourine', 'agogo', 'cuica'],
    'japan': ['taiko', 'melodic_tom', 'synth_drum'],
    'china': ['taiko', 'melodic_tom', 'synth_drum'],
    'india': ['taiko', 'melodic_tom'],
    'korea': ['taiko', 'melodic_tom', 'synth_drum'],
    'indonesia': ['taiko', 'melodic_tom'],
    'afrobeat': ['bass_drum', 'snare', 'closed_hihat', 'cowbell', 'tambourine'],
    'soukous': ['bass_drum', 'snare', 'closed_hihat', 'cowbell', 'claves'],
    'highlife': ['bass_drum', 'snare', 'closed_hihat', 'ride_cymbal'],
    'reggae': ['bass_drum', 'snare', 'closed_hihat', 'cowbell'],
    'celtic': ['bass_drum', 'snare', 'closed_hihat', 'tambourine'],
    'flamenco': ['bass_drum', 'snare', 'closed_hihat'],
    'balkan': ['bass_drum', 'snare', 'closed_hihat', 'tambourine'],
    'arabic': ['bass_drum', 'snare', 'closed_hihat'],
    'turkish': ['bass_drum', 'snare', 'closed_hihat'],
    'persian': ['bass_drum', 'snare', 'closed_hihat']
}

# GENRE PARAMS DUNIA - DIPERBAIKI: 5 SUB-GENRE PER GENRE
GENRE_PARAMS_WORLD = {
    'japan': {
        'tempo': 120, 'key': 'D', 'scale': 'japanese',
        'time_signatures': ['4/4', '6/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['japan'],
        'sub_genres': {
            'enka': {'tempo': 80, 'scale': 'minor'},
            'jpop': {'tempo': 130, 'scale': 'major'},
            'jrock': {'tempo': 140, 'scale': 'minor'},
            'anime': {'tempo': 125, 'scale': 'major'},
            'traditional': {'tempo': 100, 'scale': 'japanese'}
        }
    },
    'china': {
        'tempo': 110, 'key': 'G', 'scale': 'chinese',
        'time_signatures': ['4/4', '2/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['china'],
        'sub_genres': {
            'cpop': {'tempo': 120, 'scale': 'major'},
            'folk': {'tempo': 90, 'scale': 'pentatonic'},
            'opera': {'tempo': 85, 'scale': 'chinese'},
            'rock': {'tempo': 130, 'scale': 'minor'},
            'traditional': {'tempo': 95, 'scale': 'chinese'}
        }
    },
    'india': {
        'tempo': 100, 'key': 'C', 'scale': 'indian',
        'time_signatures': ['4/4', '6/8', '7/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['india'],
        'sub_genres': {
            'bollywood': {'tempo': 120, 'scale': 'major'},
            'classical': {'tempo': 85, 'scale': 'indian'},
            'bhajan': {'tempo': 80, 'scale': 'major'},
            'filmi': {'tempo': 125, 'scale': 'major'},
            'folk': {'tempo': 110, 'scale': 'pentatonic'}
        }
    },
    'korea': {
        'tempo': 115, 'key': 'A', 'scale': 'major',
        'time_signatures': ['4/4', '3/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['korea'],
        'sub_genres': {
            'kpop': {'tempo': 125, 'scale': 'major'},
            'trot': {'tempo': 130, 'scale': 'major'},
            'ballad': {'tempo': 75, 'scale': 'minor'},
            'hiphop': {'tempo': 95, 'scale': 'minor'},
            'rock': {'tempo': 140, 'scale': 'minor'}
        }
    },
    'indonesia': {
        'tempo': 110, 'key': 'G', 'scale': 'pelog',
        'time_signatures': ['4/4', '2/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['indonesia'],
        'sub_genres': {
            'dangdut': {'tempo': 130, 'scale': 'dangdut'},
            'pop': {'tempo': 120, 'scale': 'major'},
            'keroncong': {'tempo': 90, 'scale': 'major'},
            'campursari': {'tempo': 125, 'scale': 'pelog'},
            'folk': {'tempo': 100, 'scale': 'slendro'}
        }
    },
    'afrobeat': {
        'tempo': 115, 'key': 'F', 'scale': 'mixolydian',
        'time_signatures': ['4/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['afrobeat'],
        'sub_genres': {
            'traditional': {'tempo': 110, 'scale': 'pentatonic'},
            'modern': {'tempo': 120, 'scale': 'mixolydian'},
            'fusion': {'tempo': 115, 'scale': 'minor'},
            'dance': {'tempo': 125, 'scale': 'major'},
            'jazz': {'tempo': 105, 'scale': 'dorian'}
        }
    },
    'soukous': {
        'tempo': 130, 'key': 'C', 'scale': 'major',
        'time_signatures': ['4/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['soukous'],
        'sub_genres': {
            'congolese': {'tempo': 135, 'scale': 'major'},
            'rumba': {'tempo': 110, 'scale': 'minor'},
            'modern': {'tempo': 125, 'scale': 'major'},
            'dance': {'tempo': 140, 'scale': 'major'},
            'guitar': {'tempo': 120, 'scale': 'major'}
        }
    },
    'highlife': {
        'tempo': 120, 'key': 'G', 'scale': 'major',
        'time_signatures': ['4/4', '6/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['highlife'],
        'sub_genres': {
            'ghanaian': {'tempo': 125, 'scale': 'major'},
            'nigerian': {'tempo': 130, 'scale': 'major'},
            'guitar': {'tempo': 115, 'scale': 'major'},
            'brass': {'tempo': 120, 'scale': 'major'},
            'dance': {'tempo': 135, 'scale': 'major'}
        }
    },
    'reggae': {
        'tempo': 85, 'key': 'G', 'scale': 'major',
        'time_signatures': ['4/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['reggae'],
        'sub_genres': {
            'roots': {'tempo': 80, 'scale': 'major'},
            'dancehall': {'tempo': 95, 'scale': 'minor'},
            'rockers': {'tempo': 85, 'scale': 'major'},
            'steppers': {'tempo': 90, 'scale': 'major'},
            'one_drop': {'tempo': 75, 'scale': 'major'}
        }
    },
    'salsa': {
        'tempo': 180, 'key': 'C', 'scale': 'major',
        'time_signatures': ['4/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['salsa'],
        'sub_genres': {
            'cuban': {'tempo': 185, 'scale': 'major'},
            'puerto_rican': {'tempo': 190, 'scale': 'major'},
            'colombian': {'tempo': 175, 'scale': 'minor'},
            'romantica': {'tempo': 170, 'scale': 'minor'},
            'dura': {'tempo': 195, 'scale': 'major'}
        }
    },
    'samba': {
        'tempo': 110, 'key': 'D', 'scale': 'major',
        'time_signatures': ['2/4', '4/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['samba'],
        'sub_genres': {
            'batucada': {'tempo': 120, 'scale': 'major'},
            'pagode': {'tempo': 105, 'scale': 'major'},
            'bossa_nova': {'tempo': 95, 'scale': 'major'},
            'carnival': {'tempo': 130, 'scale': 'major'},
            'traditional': {'tempo': 115, 'scale': 'major'}
        }
    },
    'celtic': {
        'tempo': 120, 'key': 'D', 'scale': 'dorian',
        'time_signatures': ['4/4', '6/8', '3/4'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['celtic'],
        'sub_genres': {
            'irish': {'tempo': 125, 'scale': 'dorian'},
            'scottish': {'tempo': 115, 'scale': 'mixolydian'},
            'welsh': {'tempo': 110, 'scale': 'major'},
            'folk': {'tempo': 120, 'scale': 'dorian'},
            'dance': {'tempo': 140, 'scale': 'major'}
        }
    },
    'flamenco': {
        'tempo': 130, 'key': 'A', 'scale': 'phrygian',
        'time_signatures': ['4/4', '3/4', '6/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['flamenco'],
        'sub_genres': {
            'bulerias': {'tempo': 180, 'scale': 'phrygian'},
            'solea': {'tempo': 70, 'scale': 'phrygian'},
            'alegrias': {'tempo': 140, 'scale': 'major'},
            'rumba': {'tempo': 130, 'scale': 'major'},
            'tangos': {'tempo': 110, 'scale': 'phrygian'}
        }
    },
    'balkan': {
        'tempo': 140, 'key': 'E', 'scale': 'minor',
        'time_signatures': ['7/8', '9/8', '5/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['balkan'],
        'sub_genres': {
            'romanian': {'tempo': 145, 'scale': 'minor'},
            'bulgarian': {'tempo': 150, 'scale': 'minor'},
            'serbian': {'tempo': 135, 'scale': 'major'},
            'greek': {'tempo': 130, 'scale': 'minor'},
            'gypsy': {'tempo': 160, 'scale': 'minor'}
        }
    },
    'arabic': {
        'tempo': 110, 'key': 'C', 'scale': 'arabic',
        'time_signatures': ['4/4', '6/8', '10/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['arabic'],
        'sub_genres': {
            'egyptian': {'tempo': 115, 'scale': 'arabic'},
            'lebanese': {'tempo': 120, 'scale': 'major'},
            'syrian': {'tempo': 110, 'scale': 'minor'},
            'classical': {'tempo': 90, 'scale': 'arabic'},
            'pop': {'tempo': 130, 'scale': 'major'}
        }
    },
    'turkish': {
        'tempo': 120, 'key': 'H', 'scale': 'phrygian',
        'time_signatures': ['4/4', '9/8', '7/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['turkish'],
        'sub_genres': {
            'anatolian': {'tempo': 125, 'scale': 'phrygian'},
            'folk': {'tempo': 115, 'scale': 'minor'},
            'classical': {'tempo': 100, 'scale': 'makam'},
            'pop': {'tempo': 130, 'scale': 'major'},
            'rock': {'tempo': 140, 'scale': 'minor'}
        }
    },
    'persian': {
        'tempo': 95, 'key': 'C', 'scale': 'persian',
        'time_signatures': ['6/8', '4/4', '7/8'],
        'chord_progressions': CHORD_PROGRESSIONS_BY_GENRE['persian'],
        'sub_genres': {
            'classical': {'tempo': 85, 'scale': 'persian'},
            'folk': {'tempo': 100, 'scale': 'major'},
            'pop': {'tempo': 120, 'scale': 'minor'},
            'traditional': {'tempo': 90, 'scale': 'persian'},
            'dastgah': {'tempo': 80, 'scale': 'persian'}
        }
    }
}

# Gabungkan genre dunia dengan genre existing
GENRE_PARAMS.update(GENRE_PARAMS_WORLD)

# ==================== FUNGSI UTAMA YANG DIPERLUKAN ====================

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

def check_inappropriate_content(text):
    """Check for inappropriate content in lyrics"""
    if not text:
        return False
    
    text_lower = text.lower()
    for keyword in INAPPROPRIATE_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def get_current_section(beat_position):
    """Determine current section based on beat position"""
    for section, (start, end) in SECTION_TIMING.items():
        if start <= beat_position < end:
            return section
    return 'outro'

def beats_to_ticks(beats, ticks_per_beat=480):
    """Convert beats to MIDI ticks"""
    return int(round(beats * ticks_per_beat))

def get_drum_kit_for_genre(genre):
    """Get appropriate drum kit for genre"""
    if genre in DRUM_KITS_BY_GENRE:
        return DRUM_KITS_BY_GENRE[genre]
    return ['bass_drum', 'snare', 'closed_hihat', 'open_hihat', 'crash_cymbal']

def generate_kick_hits(start_beat, time_offsets, base_velocity, note_duration=0.12):
    """Helper function to generate multiple kick drum hits"""
    events = []
    for offset in time_offsets:
        hit_time = start_beat + offset
        events.append((beats_to_ticks(hit_time), 
                      Message('note_on', channel=9, note=DRUM_NOTES['bass_drum'], velocity=base_velocity, time=0)))
        events.append((beats_to_ticks(hit_time + note_duration),
                      Message('note_off', channel=9, note=DRUM_NOTES['bass_drum'], velocity=0, time=0)))
    return events

def generate_hihat_pattern_half_note(genre, section, start_beat, duration_beats=1.0):
    """Generate hi-hat pattern dengan setengah not untuk intro dan verse"""
    events = []
    
    # Untuk intro dan verse, gunakan setengah not
    if section in ['intro', 'verse']:
        # Pattern setengah not (2 ketukan per hi-hat)
        for half_note in range(int(duration_beats * 2)):
            hat_time = start_beat + (half_note * 0.5)
            vel = 80 if half_note % 2 == 0 else 75
            events.append((beats_to_ticks(hat_time), 
                          Message('note_on', channel=9, note=DRUM_NOTES['closed_hihat'], velocity=vel, time=0)))
            events.append((beats_to_ticks(hat_time + 0.45), 
                          Message('note_off', channel=9, note=DRUM_NOTES['closed_hihat'], velocity=0, time=0)))
    else:
        # Untuk section lain, gunakan pattern normal
        for eighth in range(8):
            hat_time = start_beat + (eighth * 0.125)
            vel = 85 if eighth % 2 == 0 else 75
            events.append((beats_to_ticks(hat_time), 
                          Message('note_on', channel=9, note=DRUM_NOTES['closed_hihat'], velocity=vel, time=0)))
            events.append((beats_to_ticks(hat_time + 0.06), 
                          Message('note_off', channel=9, note=DRUM_NOTES['closed_hihat'], velocity=0, time=0)))
    
    return events

def generate_section_fill(genre, current_section, next_section, fill_position):
    """Generate fill patterns between sections"""
    fills = []
    
    # Gunakan drum kit yang sesuai untuk genre
    drum_kit = get_drum_kit_for_genre(genre)
    
    # Buat fill sederhana berdasarkan drum kit yang tersedia
    if 'snare' in drum_kit and 'high_tom' in drum_kit:
        fills.append((DRUM_NOTES['snare'], fill_position, 0.25, 100))
        fills.append((DRUM_NOTES['high_tom'], fill_position + 0.125, 0.25, 90))
        fills.append((DRUM_NOTES['mid_tom'], fill_position + 0.25, 0.25, 85))
    
    return fills

def find_best_instrument(choice):
    """Fuzzy matching for instruments (case-insensitive + partial match)"""
    if isinstance(choice, list):
        choice = choice[0] if choice else 'Acoustic Grand Piano'
    
    choice_lower = choice.lower().strip()
    for instr, num in INSTRUMENTS.items():
        if choice_lower == instr.lower():
            return instr
    for instr, num in INSTRUMENTS.items():
        if (choice_lower in instr.lower() or
            any(word in instr.lower() for word in choice_lower.split())):
            return instr

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

def select_progression(params, lyrics=""):
    """Select chord progression based on mood and sentiment analysis"""
    progressions = params.get('chord_progressions', [['C', 'G', 'Am', 'F']])
    
    if lyrics:
        try:
            blob = TextBlob(lyrics)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.1: # Happy mood
                major_progressions = []
                for prog in progressions:
                    major_count = sum(1 for chord in prog if not chord.lower().startswith('m') and 'dim' not in chord and 'sus' not in chord)
                    if major_count > len(prog) / 2:
                        major_progressions.append(prog)
                if major_progressions:
                    return random.choice(major_progressions)
            
            elif polarity < -0.1: # Sad mood
                minor_progressions = []
                for prog in progressions:
                    minor_count = sum(1 for chord in prog if chord.lower().startswith('m') or 'dim' in chord)
                    if minor_count > len(prog) / 2:
                        minor_progressions.append(prog)
                if minor_progressions:
                    return random.choice(minor_progressions)
        except Exception as e:
            logger.warning("Sentiment analysis failed: {}".format(e))
    
    # Default: random selection
    selected = random.choice(progressions)
    logger.info("Selected progression: {}".format(selected))
    return selected

def detect_genre_from_lyrics(lyrics):
    """Detect genre from lyrics using keyword matching"""
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'party', 'fun', 'happy', 'tonight', 'forever', 'together'],
        'rock': ['rock', 'guitar', 'energy', 'power', 'fire', 'wild', 'roll', 'scream', 'freedom'],
        'metal': ['metal', 'heavy', 'dark', 'scream', 'thunder', 'steel', 'rage', 'shadow', 'death'],
        'jazz': ['jazz', 'smooth', 'night', 'sax', 'swing', 'harmony', 'blue', 'lounge'],
        'latin': ['latin', 'salsa', 'bossa', 'tango', 'rhythm', 'dance', 'passion', 'fiesta', 'amor'],
        'japan': ['japan', 'anime', 'sakura', 'tokyo', 'kawaii', 'samurai', 'ninja', 'sushi'],
        'india': ['india', 'bollywood', 'karma', 'yoga', 'spice', 'taj', 'mahal', 'namaste'],
        'korea': ['korea', 'kpop', 'oppa', 'seoul', 'kimchi', 'gangnam', 'hallyu'],
        'reggae': ['reggae', 'jamaica', 'rasta', 'marley', 'island', 'caribbean', 'dub'],
        'arabic': ['arabic', 'desert', 'oasis', 'allah', 'mecca', 'arab', 'middle', 'east'],
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
        logger.warning("Genre detection failed: {}".format(e))
        return 'pop'

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto', sub_genre=None, time_signature='4/4'):
    """Generate instrumental parameters based on genre and lyrics analysis - DIPERBAIKI untuk genre dunia"""
    # Cek apakah genre termasuk dalam genre dunia
    if genre in GENRE_PARAMS_WORLD:
        params = GENRE_PARAMS_WORLD.get(genre.lower(), GENRE_PARAMS_WORLD['japan']).copy()
    else:
        params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy()

    # Apply sub-genre parameters jika tersedia
    if sub_genre and sub_genre in params.get('sub_genres', {}):
        sub_params = params['sub_genres'][sub_genre]
        # Update parameters sub-genre
        for key, value in sub_params.items():
            params[key] = value
        logger.info("Applied sub-genre '{}' parameters".format(sub_genre))

    # Handle tempo input
    if user_tempo_input != 'auto' and user_tempo_input != '':
        try:
            params['tempo'] = int(user_tempo_input)
            if not (60 <= params['tempo'] <= 200):
                logger.warning("Tempo out of range (60-200 BPM): {}, using default.".format(user_tempo_input))
                params['tempo'] = params.get('tempo', 120)
        except ValueError:
            logger.warning("Invalid tempo input: '{}', using default.".format(user_tempo_input))

    # Apply time signature
    params['time_signature'] = time_signature

    # Set default instruments untuk genre dunia
    if genre in DEFAULT_INSTRUMENTS_WORLD:
        params['instruments'] = DEFAULT_INSTRUMENTS_WORLD[genre].copy()
    else:
        # Fallback untuk genre standard
        if 'instruments' not in params:
            params['instruments'] = {
                'rhythm': 'Acoustic Grand Piano',
                'harmony': 'String Ensemble 1', 
                'melody': 'Overdriven Guitar',
                'bass': 'Electric Bass finger'
            }

    # Select chord progression
    selected_progression = select_progression(params, lyrics)
    selected_chords = []
    for chord_name in selected_progression:
        if chord_name in CHORDS:
            selected_chords.append(CHORDS[chord_name])
        else:
            logger.warning("Chord '{}' not found. Using C major.".format(chord_name))
            selected_chords.append(CHORDS['C'])
    params['chords'] = selected_chords
    params['selected_progression'] = selected_progression

    params['genre'] = genre
    params['sub_genre'] = sub_genre

    logger.info("Parameter untuk {}: Tempo={}BPM, Time Signature={}, Progression={}".format(
        genre, params['tempo'], time_signature, selected_progression
    ))

    return params

def generate_bass_line_fixed(params):
    """Generate bass line dengan transposisi -12 untuk frekuensi lebih rendah"""
    chords = params['chords']
    duration_beats = params.get('duration_beats', 240)
    genre = params['genre']
    
    beats_per_chord = duration_beats / len(chords)
    
    bass_line = []
    current_beat = 0.0
    
    for i, chord_notes in enumerate(chords):
        # TRANSPOSE -36 untuk frekuensi bass lebih rendah (3 oktaf)
        root_note = chord_notes[0] - 36
        root_note = max(24, min(root_note, 48))

        chord_duration = beats_per_chord
        if i == len(chords) - 1:
            chord_duration = duration_beats - current_beat

        if chord_duration <= 0.001:
            break

        # Bass line sederhana dengan not setengah
        note_duration = 1.8
        
        for j in range(int(chord_duration / 2.0)):
            beat_pos = current_beat + (j * 2.0)
            if beat_pos < current_beat + chord_duration:
                bass_line.append((int(root_note), beat_pos, note_duration, 90))

        current_beat += chord_duration
    
    logger.info("Generated {} bass notes with -36 transposition".format(len(bass_line)))
    return bass_line

def generate_bass_line(params):
    """Generate bass line dengan transposisi -12 yang sudah diperbaiki"""
    return generate_bass_line_fixed(params)

def generate_enhanced_drum_pattern(params, duration_beats):
    """Generate enhanced drum patterns dengan hi-hat setengah not dan drum kit khusus"""
    drum_events = []
    genre = params['genre']
    sub_genre = params.get('sub_genre', '')
    
    logger.info("Generating enhanced drum pattern for {}/{} with half-note hi-hat".format(genre, sub_genre))
    
    # Dapatkan drum kit yang sesuai untuk genre
    drum_kit = get_drum_kit_for_genre(genre)
    
    # ADD INTRO CRASH CYMBAL jika tersedia dalam kit
    if 'crash_cymbal' in drum_kit:
        drum_events.append((0, Message('note_on', channel=9, note=DRUM_NOTES['crash_cymbal'], velocity=110, time=0)))
        drum_events.append((beats_to_ticks(2.0), Message('note_off', channel=9, note=DRUM_NOTES['crash_cymbal'], velocity=0, time=0)))
    
    fill_added = False
    
    for beat_pos in range(0, int(duration_beats)):
        beat_time_start_beats = float(beat_pos)
        current_section = get_current_section(beat_pos)
        
        # Generate hi-hat pattern dengan setengah not untuk intro/verse
        hihat_events = generate_hihat_pattern_half_note(genre, current_section, beat_time_start_beats)
        drum_events.extend(hihat_events)
        
        # Basic pattern berdasarkan drum kit yang tersedia
        if 'bass_drum' in drum_kit:
            if beat_pos % 4 == 0:  # Beat 1
                drum_events.extend(generate_kick_hits(beat_time_start_beats, [0], 120))
            elif beat_pos % 4 == 2:  # Beat 3
                drum_events.extend(generate_kick_hits(beat_time_start_beats, [0], 115))
        
        if 'snare' in drum_kit:
            # Snare on beats 2 and 4
            if beat_pos % 4 == 1 or beat_pos % 4 == 3:
                snare_time = beat_time_start_beats
                drum_events.append((beats_to_ticks(snare_time), 
                                  Message('note_on', channel=9, note=DRUM_NOTES['snare'], velocity=115, time=0)))
                drum_events.append((beats_to_ticks(snare_time + 0.25), 
                                  Message('note_off', channel=9, note=DRUM_NOTES['snare'], velocity=0, time=0)))
        
        # Add fill sebelum section transition dengan drum kit yang sesuai
        if not fill_added and beat_pos in [7, 23, 31, 47, 63, 71, 87, 103, 119, 135]:
            next_section = get_current_section(beat_pos + 1)
            fill_events = generate_section_fill(genre, current_section, next_section, beat_time_start_beats + 0.5)
            for note, fill_time, duration, velocity in fill_events:
                drum_events.append((beats_to_ticks(fill_time), 
                                  Message('note_on', channel=9, note=note, velocity=velocity, time=0)))
                drum_events.append((beats_to_ticks(fill_time + duration), 
                                  Message('note_off', channel=9, note=note, velocity=0, time=0)))
            fill_added = True
        elif beat_pos % 4 == 0:
            fill_added = False
    
    # SORT events by time
    drum_events.sort(key=lambda x: x[0])
    
    # Convert to proper MIDI timing
    final_drum_events = []
    current_time = 0
    
    for tick_time, message in drum_events:
        delta_time = max(0, tick_time - current_time)
        message.time = delta_time
        final_drum_events.append(message)
        current_time = tick_time
    
    logger.info("Generated {} drum events with genre-specific kit: {}".format(len(final_drum_events), drum_kit))
    return final_drum_events

def generate_enhanced_drums(params, duration_beats):
    """Generate enhanced drum patterns dengan semua perbaikan"""
    return generate_enhanced_drum_pattern(params, duration_beats)

# ==================== FUNGSI GENERATE MUSIC SEDERHANA ====================

def generate_simple_melody(params):
    """Generate simple melody untuk testing"""
    scale_notes = [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale
    duration_beats = params.get('duration_beats', 240)
    
    melody_events = []
    for i in range(0, int(duration_beats), 2):
        note = random.choice(scale_notes)
        melody_events.append((note, i, 1.5, 90))
    
    return melody_events, []

def generate_simple_rhythm(params):
    """Generate simple rhythm untuk testing"""
    chords = params['chords']
    duration_beats = params.get('duration_beats', 240)
    
    rhythm_data = []
    beats_per_chord = duration_beats / len(chords)
    
    for i, chord_notes in enumerate(chords):
        start_beat = i * beats_per_chord
        for note in chord_notes[:3]:  # Mainkan 3 note pertama chord
            rhythm_data.append((note, start_beat, beats_per_chord * 0.9, 80))
    
    return rhythm_data

def generate_simple_harmony(params):
    """Generate simple harmony untuk testing"""
    chords = params['chords']
    duration_beats = params.get('duration_beats', 240)
    
    harmony_data = []
    beats_per_chord = duration_beats / len(chords)
    
    for i, chord_notes in enumerate(chords):
        start_beat = i * beats_per_chord
        for note in chord_notes:
            harmony_data.append((note + 12, start_beat, beats_per_chord * 0.9, 70))
    
    return harmony_data

def create_midi_file(params, output_path, outro_type='fade'):
    """Create multi-track MIDI file sederhana untuk testing"""
    tempo = params['tempo']
    duration_beats = params.get('duration_beats', 240)
    ticks_per_beat = 480
    genre = params['genre']

    mid = MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    # Create tracks
    rhythm_track = MidiTrack()
    harmony_track = MidiTrack()
    melody_track = MidiTrack()
    bass_track = MidiTrack()
    drums_track = MidiTrack()

    mid.tracks.extend([rhythm_track, harmony_track, melody_track, bass_track, drums_track])

    mido_tempo_us = bpm2tempo(tempo)
    rhythm_track.append(MetaMessage('set_tempo', tempo=mido_tempo_us, time=0))
    
    # Apply time signature
    time_sig = params.get('time_signature', '4/4').split('/')
    numerator = int(time_sig[0])
    denominator = int(time_sig[1])
    rhythm_track.append(MetaMessage('time_signature', numerator=numerator, denominator=denominator, time=0))

    def add_note_events_to_track(track, note_data, channel, program=None, volume=100):
        """Helper function to add note events to track"""
        if program is not None:
            track.append(Message('program_change', channel=channel, program=program, time=0))
        
        track.append(Message('control_change', channel=channel, control=7, value=volume, time=0))
        
        # Convert note data to absolute ticks and sort
        all_messages = []
        for pitch, start_beat, duration_beat, velocity in note_data:
            start_ticks = beats_to_ticks(start_beat)
            duration_ticks = beats_to_ticks(duration_beat)
            
            all_messages.append((start_ticks, Message('note_on', channel=channel, note=pitch, velocity=velocity, time=0)))
            all_messages.append((start_ticks + duration_ticks, Message('note_off', channel=channel, note=pitch, velocity=0, time=0)))
        
        # Sort by time and add with proper delta times
        all_messages.sort(key=lambda x: x[0])
        current_time = 0
        
        for abs_time, message in all_messages:
            delta_time = max(0, abs_time - current_time)
            message.time = delta_time
            track.append(message)
            current_time = abs_time

    # RHYTHM TRACK - DIPERBAIKI: handle instrument yang mungkin list
    rhythm_instrument = params['instruments'].get('rhythm')
    if rhythm_instrument:
        # Pastikan rhythm_instrument adalah string, bukan list
        if isinstance(rhythm_instrument, list):
            rhythm_instrument = rhythm_instrument[0] if rhythm_instrument else 'Acoustic Grand Piano'
        program_num = INSTRUMENTS.get(rhythm_instrument, 0)
        rhythm_events = generate_simple_rhythm(params)
        add_note_events_to_track(rhythm_track, rhythm_events, 0, program_num, 110)

    # HARMONY TRACK - DIPERBAIKI: handle instrument yang mungkin list
    harmony_instrument = params['instruments'].get('harmony')
    if harmony_instrument:
        if isinstance(harmony_instrument, list):
            harmony_instrument = harmony_instrument[0] if harmony_instrument else 'String Ensemble 1'
        program_num = INSTRUMENTS.get(harmony_instrument, 48)
        harmony_data = generate_simple_harmony(params)
        add_note_events_to_track(harmony_track, harmony_data, 1, program_num, 100)

    # MELODY TRACK - DIPERBAIKI: handle instrument yang mungkin list
    melody_instrument = params['instruments'].get('melody')
    if melody_instrument:
        if isinstance(melody_instrument, list):
            melody_instrument = melody_instrument[0] if melody_instrument else 'Overdriven Guitar'
        program_num = INSTRUMENTS.get(melody_instrument, 0)
        melody_events, _ = generate_simple_melody(params)
        add_note_events_to_track(melody_track, melody_events, 2, program_num, 120)

    # BASS TRACK - DIPERBAIKI: handle instrument yang mungkin list
    bass_instrument = params['instruments'].get('bass')
    if bass_instrument:
        if isinstance(bass_instrument, list):
            bass_instrument = bass_instrument[0] if bass_instrument else 'Electric Bass finger'
        program_num = INSTRUMENTS.get(bass_instrument, 33)
        bass_notes = generate_bass_line(params)
        add_note_events_to_track(bass_track, bass_notes, 3, program_num, 110)

    # DRUMS TRACK
    if params.get('drums_enabled', True):
        drums_track.append(Message('control_change', channel=9, control=7, value=120, time=0))
        drum_events = generate_enhanced_drums(params, duration_beats)
        
        current_time = 0
        for message in drum_events:
            drums_track.append(message)
            current_time += message.time

    # Add end_of_track to all tracks
    for track in mid.tracks:
        if len(track) > 0:
            total_ticks = sum(msg.time for msg in track)
            end_ticks = beats_to_ticks(duration_beats)
            remaining_ticks = max(0, end_ticks - total_ticks)
            track.append(MetaMessage('end_of_track', time=remaining_ticks))
        else:
            track.append(MetaMessage('end_of_track', time=0))

    try:
        mid.save(output_path)
        logger.info("MIDI generated successfully: {}".format(output_path.name))
        return True
    except Exception as e:
        logger.error("Error writing MIDI file: {}".format(e), exc_info=True)
        return False

# ==================== FUNGSI AUDIO PROCESSING ====================

def midi_to_audio_subprocess(midi_path, output_wav_path, soundfont_path):
    """FluidSynth subprocess dengan settings yang diperbaiki"""
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
            '-o', 'synth.gain=1.2',
            '-o', 'audio.periods=2',
            '-a', 'file',
            '-r', '48000',
            '-c', '2',
            '-z', '1024',
            '-ni',
            str(soundfont_path),
            str(midi_path)
        ]

        logger.info("Rendering MIDI with FluidSynth...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
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
                return False

        logger.error("FluidSynth error (code {}): {}".format(result.returncode, result.stderr))
        return False

    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout (120s)")
        return False
    except FileNotFoundError:
        logger.error("'fluidsynth' not found. Install: sudo apt install fluidsynth")
        return False
    except Exception as e:
        logger.error("Unexpected FluidSynth error: {}".format(e))
        return False

def midi_to_audio(midi_path, output_wav_path):
    """Main MIDI to audio conversion"""
    if not SOUNDFONT_PATH:
        logger.error("SoundFont not available")
        return False

    return midi_to_audio_subprocess(midi_path, output_wav_path, SOUNDFONT_PATH)

def convert_to_mp3_fast(wav_path, mp3_path):
    """Fast audio processing menggunakan FFmpeg langsung"""
    logger.info("MP3 CONVERSION: {} -> {}".format(wav_path, mp3_path))
    
    try:
        mp3_cmd = [
            'ffmpeg', '-i', str(wav_path),
            '-codec:a', 'libmp3lame',
            '-b:a', '192k',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            str(mp3_path)
        ]
        
        result = subprocess.run(mp3_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"MP3 conversion failed: {result.stderr}")

        if os.path.exists(mp3_path):
            file_size = os.path.getsize(mp3_path) / 1024
            logger.info("MP3 generated: {} ({:.1f} KB)".format(mp3_path.name, file_size))
            return True
        else:
            raise Exception("Final MP3 file not created")

    except Exception as e:
        logger.error("MP3 conversion failed: {}".format(str(e)))
        return False

def wav_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3"""
    return convert_to_mp3_fast(wav_path, mp3_path)

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

# ==================== FLASK ROUTES ====================

@app.route('/')
def index():
    """Main web interface - DIPERBAIKI dengan genre dunia"""
    html_template = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎵 Generate Instrumental AI - World Music 🎵</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }
        .container { max-width: 1000px; margin: auto; }
        h1 { 
            text-align: center;
            color: white;
            margin-bottom: 20px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            font-size: 2.2em;
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
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #2c3e50;
            font-size: 1em;
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
        select, input[type="number"] {
            width: 100%;
            padding: 12px;
            margin-bottom: 15px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
            background: #f8f9fa;
        }
        .form-row { 
            display: flex; 
            gap: 15px; 
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .form-row > div { 
            flex: 1;
            min-width: 200px;
        }
        .form-row small { 
            display: block; 
            margin-top: 5px; 
            color: #95a5a6; 
            font-size: 0.8em; 
        }

        button {
            background: linear-gradient(45deg, #3498db, #2980b9);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 18px;
            cursor: pointer;
            width: 100%;
            transition: all 0.3s ease;
            font-weight: bold;
            margin-top: 10px;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            background: linear-gradient(45deg, #2980b9, #3498db);
        }
        button:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
            transform: none;
        }
        .result {
            display: none;
            margin-top: 30px;
            text-align: center;
        }
        .audio-player {
            width: 100%;
            margin: 20px 0;
            border-radius: 10px;
        }
        .download-btn {
            display: inline-block;
            background: #27ae60;
            color: white;
            padding: 12px 25px;
            border-radius: 8px;
            text-decoration: none;
            margin: 10px;
            transition: all 0.3s ease;
        }
        .download-btn:hover {
            background: #219a52;
            transform: translateY(-2px);
        }
        .loading {
            display: none;
            text-align: center;
            margin: 20px 0;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 2s linear infinite;
            margin: 0 auto 15px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .error {
            background: #e74c3c;
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: none;
        }
        .success {
            background: #27ae60;
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: none;
        }
        .info-box {
            background: #d6eaf8;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin: 15px 0;
            border-radius: 0 8px 8px 0;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Generate Instrumental AI - World Music 🎵</h1>
        <p class="subtitle">Ubah lirik menjadi musik instrumental dari seluruh dunia dengan teknologi AI</p>
        
        <div class="card">
            <h2>📝 Masukkan Lirik Lagu</h2>
            <textarea id="lyrics" placeholder="Masukkan lirik lagu di sini... Contoh: 
Aku mencintaimu
Dengan sepenuh hati
Bersamamu selamanya
Dalam suka dan duka"></textarea>
            
            <div class="form-row">
                <div>
                    <label for="genre">🌍 Genre Musik Dunia</label>
                    <select id="genre">
                        <option value="auto">Auto-detect dari lirik</option>
                        
                        <optgroup label="ASIA">
                            <option value="japan">Japan</option>
                            <option value="china">China</option>
                            <option value="india">India</option>
                            <option value="korea">Korea</option>
                            <option value="indonesia">Indonesia</option>
                        </optgroup>
                        
                        <optgroup label="AFRIKA">
                            <option value="afrobeat">Afrobeat</option>
                            <option value="soukous">Soukous</option>
                            <option value="highlife">Highlife</option>
                        </optgroup>
                        
                        <optgroup label="AMERIKA">
                            <option value="reggae">Reggae</option>
                            <option value="salsa">Salsa</option>
                            <option value="samba">Samba</option>
                        </optgroup>
                        
                        <optgroup label="EROPA">
                            <option value="celtic">Celtic</option>
                            <option value="flamenco">Flamenco</option>
                            <option value="balkan">Balkan</option>
                        </optgroup>
                        
                        <optgroup label="TIMUR TENGAH">
                            <option value="arabic">Arabic</option>
                            <option value="turkish">Turkish</option>
                            <option value="persian">Persian</option>
                        </optgroup>
                        
                        <optgroup label="INTERNASIONAL">
                            <option value="pop">Pop</option>
                            <option value="rock">Rock</option>
                            <option value="metal">Metal</option>
                            <option value="jazz">Jazz</option>
                            <option value="latin">Latin</option>
                        </optgroup>
                    </select>
                </div>
                <div>
                    <label for="tempo">🎵 Tempo (BPM)</label>
                    <input type="number" id="tempo" min="60" max="200" placeholder="Auto (60-200)">
                    <small>Kosongkan untuk auto-detect</small>
                </div>
            </div>

            <div class="form-row">
                <div>
                    <label for="subgenre">🎸 Sub-Genre</label>
                    <select id="subgenre">
                        <option value="auto">Auto-pilih</option>
                    </select>
                </div>
                <div>
                    <label for="timesignature">⏱️ Time Signature</label>
                    <select id="timesignature">
                        <option value="4/4">4/4 (Common Time)</option>
                        <option value="3/4">3/4 (Waltz)</option>
                        <option value="6/8">6/8 (Compound)</option>
                        <option value="2/4">2/4 (March)</option>
                        <option value="7/8">7/8 (Balkan)</option>
                        <option value="9/8">9/8 (Turkish)</option>
                    </select>
                </div>
            </div>

            <div class="form-row">
                <div>
                    <label for="outro">🎹 Outro Type</label>
                    <select id="outro">
                        <option value="fade">Fade Out</option>
                        <option value="intro">Back to Intro</option>
                        <option value="descending">Descending</option>
                        <option value="abrupt">Abrupt End</option>
                    </select>
                </div>
            </div>

            <div class="info-box">
                <strong>🎯 Fitur Enhanced World Music:</strong> 
                <ul style="margin: 10px 0; padding-left: 20px;">
                    <li><strong>20+ Genre Dunia:</strong> Asia, Afrika, Amerika, Eropa, Timur Tengah</li>
                    <li><strong>5 Sub-genre:</strong> Setiap genre memiliki 5 variasi sub-genre</li>
                    <li><strong>Instrumen Tradisional:</strong> Koto (Jepang), Sitar (India), Oud (Arab), dll</li>
                    <li><strong>Drum Kit Khusus:</strong> Setiap genre memiliki drum kit yang sesuai</li>
                    <li><strong>Hi-hat Setengah Not:</strong> Untuk intro dan verse</li>
                    <li><strong>Bass Frekuensi Rendah:</strong> Transpose -36 untuk suara bass yang dalam</li>
                    <li><strong>Time Signature Beragam:</strong> 2/4, 3/4, 4/4, 6/8, 7/8, 9/8</li>
                </ul>
            </div>

            <button id="generateBtn" onclick="generateMusic()">
                🌍 Generate World Music (Enhanced)
            </button>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Sedang membuat musik dunia... Ini mungkin memakan waktu 1-2 menit</p>
            <p><small>Membuat MIDI → Render Audio → Convert MP3 → Apply Effects</small></p>
        </div>

        <div class="error" id="error"></div>
        <div class="success" id="success"></div>

        <div class="result" id="result">
            <div class="card">
                <h2>🎵 Musik Dunia Anda Siap!</h2>
                <audio controls class="audio-player" id="audioPlayer"></audio>
                <div>
                    <a href="#" class="download-btn" id="downloadMp3">📥 Download MP3</a>
                    <a href="#" class="download-btn" id="downloadMidi">🎹 Download MIDI</a>
                </div>
                <div id="trackInfo" style="margin-top: 15px; text-align: left;"></div>
            </div>
        </div>
    </div>

    <script>
        // Sub-genre mapping untuk genre dunia - DIPERBAIKI: 5 sub-genre per genre
        const worldSubgenres = {
            // ASIA
            'japan': ['enka', 'jpop', 'jrock', 'anime', 'traditional'],
            'china': ['cpop', 'folk', 'opera', 'rock', 'traditional'],
            'india': ['bollywood', 'classical', 'bhajan', 'filmi', 'folk'],
            'korea': ['kpop', 'trot', 'ballad', 'hiphop', 'rock'],
            'indonesia': ['dangdut', 'pop', 'keroncong', 'campursari', 'folk'],
            
            // AFRIKA
            'afrobeat': ['traditional', 'modern', 'fusion', 'dance', 'jazz'],
            'soukous': ['congolese', 'rumba', 'modern', 'dance', 'guitar'],
            'highlife': ['ghanaian', 'nigerian', 'guitar', 'brass', 'dance'],
            
            // AMERIKA
            'reggae': ['roots', 'dancehall', 'rockers', 'steppers', 'one_drop'],
            'salsa': ['cuban', 'puerto_rican', 'colombian', 'romantica', 'dura'],
            'samba': ['batucada', 'pagode', 'bossa_nova', 'carnival', 'traditional'],
            
            // EROPA
            'celtic': ['irish', 'scottish', 'welsh', 'folk', 'dance'],
            'flamenco': ['bulerias', 'solea', 'alegrias', 'rumba', 'tangos'],
            'balkan': ['romanian', 'bulgarian', 'serbian', 'greek', 'gypsy'],
            
            // TIMUR TENGAH
            'arabic': ['egyptian', 'lebanese', 'syrian', 'classical', 'pop'],
            'turkish': ['anatolian', 'folk', 'classical', 'pop', 'rock'],
            'persian': ['classical', 'folk', 'pop', 'traditional', 'dastgah'],
            
            // INTERNASIONAL
            'pop': ['synthpop', 'indiepop', 'electropop'],
            'rock': ['classic', 'alternative', 'punk'],
            'metal': ['thrash', 'death', 'black'],
            'jazz': ['bebop', 'swing', 'cool'],
            'latin': ['salsa', 'bossa', 'tango']
        };

        function updateSubgenreOptions() {
            const genre = document.getElementById('genre').value;
            const subgenreSelect = document.getElementById('subgenre');
            
            subgenreSelect.innerHTML = '<option value="auto">Auto-pilih</option>';
            
            if (worldSubgenres[genre]) {
                worldSubgenres[genre].forEach(sub => {
                    const option = document.createElement('option');
                    option.value = sub;
                    // Format nama sub-genre menjadi lebih readable
                    const formattedName = sub.split('_').map(word => 
                        word.charAt(0).toUpperCase() + word.slice(1)
                    ).join(' ');
                    option.textContent = formattedName;
                    subgenreSelect.appendChild(option);
                });
            }
        }

        // Initial setup
        document.getElementById('genre').addEventListener('change', updateSubgenreOptions);
        updateSubgenreOptions();

        async function generateMusic() {
            const lyrics = document.getElementById('lyrics').value.trim();
            const genre = document.getElementById('genre').value;
            const tempo = document.getElementById('tempo').value;
            const subgenre = document.getElementById('subgenre').value;
            const timesignature = document.getElementById('timesignature').value;
            const outro = document.getElementById('outro').value;

            // Validasi
            if (!lyrics) {
                showError('Silakan masukkan lirik lagu terlebih dahulu.');
                return;
            }

            if (lyrics.length < 10) {
                showError('Lirik terlalu pendek. Minimal 10 karakter.');
                return;
            }

            // Tampilkan loading
            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('success').style.display = 'none';
            document.getElementById('result').style.display = 'none';
            document.getElementById('generateBtn').disabled = true;

            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        lyrics: lyrics,
                        genre: genre,
                        tempo: tempo,
                        sub_genre: subgenre,
                        time_signature: timesignature,
                        outro_type: outro
                    })
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    showSuccess('Musik dunia berhasil dibuat!');
                    displayResult(data);
                } else {
                    showError(data.error || 'Terjadi kesalahan saat membuat musik.');
                }
            } catch (error) {
                showError('Koneksi error: ' + error.message);
            } finally {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('generateBtn').disabled = false;
            }
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            document.getElementById('success').style.display = 'none';
        }

        function showSuccess(message) {
            const successDiv = document.getElementById('success');
            successDiv.textContent = message;
            successDiv.style.display = 'block';
            document.getElementById('error').style.display = 'none';
        }

        function displayResult(data) {
            const resultDiv = document.getElementById('result');
            const audioPlayer = document.getElementById('audioPlayer');
            const downloadMp3 = document.getElementById('downloadMp3');
            const downloadMidi = document.getElementById('downloadMidi');
            const trackInfo = document.getElementById('trackInfo');

            // Set audio source
            audioPlayer.src = data.audio_url;
            
            // Set download links
            downloadMp3.href = data.audio_url;
            downloadMp3.download = data.filename + '.mp3';
            
            downloadMidi.href = data.midi_url;
            downloadMidi.download = data.filename + '.mid';

            // Display track info
            trackInfo.innerHTML = `
                <h3>📊 Info Track World Music:</h3>
                <p><strong>Genre:</strong> ${data.genre} ${data.sub_genre ? '(' + data.sub_genre + ')' : ''}</p>
                <p><strong>Tempo:</strong> ${data.tempo} BPM</p>
                <p><strong>Time Signature:</strong> ${data.time_signature}</p>
                <p><strong>Outro Type:</strong> ${data.outro_type}</p>
                <p><strong>Durasi:</strong> ${data.duration || '3:00'} menit</p>
                <p><strong>Instruments:</strong> ${data.instruments?.join(', ') || 'Traditional instruments'}</p>
                <p><strong>Fitur:</strong> Drum kit khusus, Hi-hat setengah not, Bass frekuensi rendah, Time signature beragam</p>
            `;

            resultDiv.style.display = 'block';
            resultDiv.scrollIntoView({ behavior: 'smooth' });
        }

        // Auto-cleanup on page load
        window.addEventListener('load', function() {
            fetch('/cleanup', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    console.log('Cleanup completed:', data);
                })
                .catch(console.error);
        });
    </script>
</body>
</html>
    """
    return render_template_string(html_template)

@app.route('/generate', methods=['POST'])
def generate_music():
    """Generate music from lyrics dengan semua perbaikan"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'}), 400

        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto').lower()
        tempo_input = data.get('tempo', 'auto')
        sub_genre_input = data.get('sub_genre', 'auto')
        time_signature = data.get('time_signature', '4/4')
        outro_type = data.get('outro_type', 'fade')

        # Validasi input
        if not lyrics:
            return jsonify({'success': False, 'error': 'Lirik tidak boleh kosong'}), 400

        if len(lyrics) < 10:
            return jsonify({'success': False, 'error': 'Lirik terlalu pendek (minimal 10 karakter)'}), 400

        # Cek konten tidak pantas
        if check_inappropriate_content(lyrics):
            return jsonify({'success': False, 'error': 'Lirik mengandung konten yang tidak pantas'}), 400

        # Auto-detect genre jika diperlukan
        if genre_input == 'auto':
            detected_genre = detect_genre_from_lyrics(lyrics)
            genre = detected_genre
            logger.info("Auto-detected genre: '{}'".format(genre))
        else:
            genre = genre_input

        # Validasi genre
        if genre not in GENRE_PARAMS:
            return jsonify({'success': False, 'error': 'Genre tidak valid: {}'.format(genre)}), 400

        # Auto-pilih sub-genre jika diperlukan
        if sub_genre_input == 'auto':
            sub_genre = None
        else:
            sub_genre = sub_genre_input

        # Validasi outro type
        if outro_type not in OUTRO_PATTERNS:
            outro_type = 'fade'

        # Generate parameter musik
        music_params = get_music_params_from_lyrics(
            genre, lyrics, tempo_input, sub_genre, time_signature
        )

        # Set duration untuk 3 menit (144 beats pada 120 BPM)
        target_duration_seconds = 180  # 3 menit
        music_params['duration_beats'] = int((target_duration_seconds * music_params['tempo']) / 60)

        # Generate unique ID untuk file
        unique_id = generate_unique_id(lyrics)
        filename_base = "instrumental_{}".format(unique_id)
        
        midi_path = AUDIO_OUTPUT_DIR / "{}.mid".format(filename_base)
        wav_path = AUDIO_OUTPUT_DIR / "{}.wav".format(filename_base)
        mp3_path = AUDIO_OUTPUT_DIR / "{}.mp3".format(filename_base)

        logger.info("Starting ENHANCED WORLD MUSIC generation for '{}' (ID: {})".format(genre, unique_id))

        # Step 1: Buat file MIDI dengan semua perbaikan
        logger.info("Step 1: Creating enhanced MIDI file...")
        midi_success = create_midi_file(music_params, midi_path, outro_type)
        if not midi_success:
            return jsonify({'success': False, 'error': 'Gagal membuat file MIDI'}), 500

        # Step 2: Convert MIDI ke WAV
        logger.info("Step 2: Converting MIDI to WAV...")
        audio_success = midi_to_audio(midi_path, wav_path)
        if not audio_success:
            return jsonify({'success': False, 'error': 'Gagal merender audio dari MIDI'}), 500

        # Step 3: Convert WAV ke MP3
        logger.info("Step 3: Converting WAV to MP3...")
        mp3_success = wav_to_mp3(wav_path, mp3_path)
        if not mp3_success:
            return jsonify({'success': False, 'error': 'Gagal convert ke MP3'}), 500

        # Step 4: Bersihkan file WAV sementara
        try:
            if wav_path.exists():
                wav_path.unlink()
                logger.info("Cleaned up temporary WAV file")
        except Exception as e:
            logger.warning("Could not delete WAV file: {}".format(e))

        # Siapkan response
        processing_time = time.time() - start_time
        logger.info("Enhanced world music generation completed in {:.1f}s".format(processing_time))

        response_data = {
            'success': True,
            'filename': filename_base,
            'audio_url': '/audio/{}.mp3'.format(filename_base),
            'midi_url': '/audio/{}.mid'.format(filename_base),
            'genre': music_params['genre'],
            'sub_genre': music_params.get('sub_genre'),
            'tempo': music_params['tempo'],
            'time_signature': music_params.get('time_signature', '4/4'),
            'outro_type': outro_type,
            'duration': '3:00',
            'instruments': list(music_params['instruments'].values()),
            'processing_time': processing_time,
            'message': 'Musik dunia berhasil dibuat dengan fitur enhanced!'
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error("Error in generate_music: {}".format(e), exc_info=True)
        return jsonify({'success': False, 'error': 'Terjadi kesalahan sistem: {}'.format(str(e))}), 500

@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve generated audio files"""
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)

@app.route('/cleanup', methods=['POST'])
def cleanup_files():
    """Clean up old generated files"""
    try:
        deleted_count = cleanup_old_files(AUDIO_OUTPUT_DIR, max_age_hours=1)
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': 'Cleanup completed'
        })
    except Exception as e:
        logger.error("Cleanup error: {}".format(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/status')
def status():
    """API status check"""
    deps_available = check_python_dependencies()
    
    status_info = {
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'dependencies': deps_available,
        'soundfont_available': SOUNDFONT_PATH is not None,
        'soundfont_path': str(SOUNDFONT_PATH) if SOUNDFONT_PATH else None,
        'audio_output_dir': str(AUDIO_OUTPUT_DIR),
        'supported_genres': list(GENRE_PARAMS.keys()),
        'features': [
            '20+ Genre dunia dengan 5 sub-genre masing-masing',
            'Instrumen tradisional untuk setiap region',
            'Drum kit khusus per genre',
            'Hi-hat setengah not untuk intro dan verse',
            'Bass frekuensi rendah (transpose -36)',
            'Time signature beragam (2/4, 3/4, 4/4, 6/8, 7/8, 9/8)'
        ]
    }
    
    return jsonify(status_info)

def main():
    """Main function"""
    logger.info("=== ENHANCED WORLD MUSIC Generator Starting ===")
    logger.info("Python version: {}".format(sys.version))
    logger.info("Working directory: {}".format(BASE_DIR))
    
    # Check dependencies
    available_deps = check_python_dependencies()
    
    # SoundFont status
    if SOUNDFONT_PATH:
        logger.info("SoundFont detected: {}".format(SOUNDFONT_PATH.name))
    else:
        logger.warning("No SoundFont found! Audio generation will fail.")
        logger.info("Please download a SoundFont and place it in the application directory.")
    
    # Clean up old files on startup
    cleanup_old_files(AUDIO_OUTPUT_DIR)
    
    # Start Flask app
    logger.info("Starting Flask server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
