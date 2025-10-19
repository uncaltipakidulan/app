#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask Generate Instrumental dengan Latin & Dangdut Support
Text-to-Instrumental Music Generator dengan Genre Detection
"""

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
import pyphen # Digunakan untuk analisis teks lebih lanjut jika diperlukan

# Import pyfluidsynth dengan error handling
try:
    import fluidsynth as pyfluidsynth_lib # Alias untuk menghindari konflik nama dengan fungsi fluidsynth
    FLUIDSYNTH_BINDING_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_BINDING_AVAILABLE = False

from pydub import AudioSegment

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'), # Mengganti app5.log ke app.log
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Inisialisasi Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Development mode

# Path konfigurasi
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'
SOUNDFONT_PATH = BASE_DIR / 'GeneralUser-GS-v1.471.sf2'

# Buat direktori jika belum ada
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# Deteksi dependensi
def check_python_dependencies():
    """Cek dependensi Python yang diperlukan"""
    deps = {
        'Flask-CORS': 'flask_cors' in sys.modules or __import__('flask_cors'),
        'MIDIUtil': 'midiutil' in sys.modules or __import__('midiutil'),
        'TextBlob': 'textblob' in sys.modules or __import__('textblob'),
        'Pyphen': 'pyphen' in sys.modules or __import__('pyphen'),
        'Pydub': 'pydub' in sys.modules or __import__('pydub')
    }
    return [name for name, available in deps.items() if available]

# Dictionary instrumen GM SoundFont (MIDI Program Numbers)
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
    'Hammond Organ': 17, # Hammond Organ sering dipetakan ke Percussive Organ
    'Rotary Organ': 18, # Rotary Organ sering dipetakan ke Rock Organ
    
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
    
    # Percussive
    'Tinkle Bell': 112, 'Agogo': 113, 'Steel Drums': 114, 'Woodblock': 115,
    
    # Sound FX
    'Guitar Fret Noise': 120, 'Breath Noise': 121, 'Seashore': 122, 'Bird Tweet': 123,
    'Telephone Ring': 124, 'Helicopter': 125, 'Applause': 126, 'Gunshot': 127,
    
    # Indonesian Instruments (aproksimasi)
    'Gamelan': 114,  # Steel Drums sebagai pengganti
    'Kendang': 115,  # Woodblock sebagai pengganti
    'Suling': 75,    # Pan Flute sebagai pengganti suling
    'Rebab': 110,    # Fiddle sebagai pengganti rebab
    'Talempong': 14, # Tubular Bells sebagai pengganti
    'Gambus': 25,    # Steel String Guitar sebagai pengganti
    'Mandolin': 27,  # Menggunakan Clean Electric Guitar sebagai pengganti
    'Harmonica': 77, # Menggunakan Shakuhachi sebagai pengganti
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
    'Cm9': [60, 63, 67, 70, 74],  # Added Cm9 (C Eb G Bb D)
    'Fm9': [65, 68, 72, 75, 79],  # Added Fm9 (F Ab C Eb G)
    'Ebmaj7': [63, 67, 70, 74],   # Added Ebmaj7 (Eb G Bb D)
    'Gmaj7': [67, 71, 74, 78], 
    'Cmaj7': [60, 64, 67, 71], 
    
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
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'locrian': [0, 1, 3, 5, 6, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10], # Minor pentatonic + blue note
    'pentatonic': [0, 3, 5, 7, 10], # Minor pentatonic
    'latin': [0, 2, 4, 5, 7, 9, 10],  # Mixolydian sering digunakan untuk Latin
    'dangdut': [0, 1, 4, 5, 7, 8, 11],  # Phrygian variant, atau minor harmonic dengan G# (A-Bb-D-Eb-F-G-Ab-Bb)
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
        'drums_enabled': True,
        'chord_progression': ['E', 'A', 'B', 'C#m'],
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
            'harmony': ['Acoustic Grand Piano', 'String Ensemble 1', 'Brass Section'],
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
        'mood': 'traditional'
    }
}

def detect_genre_from_lyrics(lyrics):
    """Deteksi genre dari lirik menggunakan keyword matching"""
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'party', 'fun', 'happy', 'tonight', 'forever', 'together'],
        'rock': ['rock', 'guitar', 'energy', 'power', 'fire', 'wild', 'roll', 'scream', 'freedom'],
        'metal': ['metal', 'heavy', 'dark', 'scream', 'thunder', 'steel', 'rage', 'shadow', 'death'],
        'ballad': ['sad', 'love', 'heartbreak', 'memory', 'gentle', 'soft', 'tears', 'alone', 'forever'],
        'blues': ['soul', 'heartache', 'guitar', 'night', 'trouble', 'baby', 'lonely'], 
        'jazz': ['jazz', 'smooth', 'night', 'sax', 'cool', 'swing', 'harmony', 'blue', 'lounge'],
        'hiphop': ['rap', 'street', 'beat', 'flow', 'rhythm', 'hustle', 'city', 'rhyme', 'crew'],
        'latin': ['latin', 'salsa', 'rhythm', 'dance', 'passion', 'fiesta', 'caliente', 'amor', 'despacito'],
        'dangdut': ['dangdut', 'tradisional', 'cinta', 'hati', 'kenangan', 'indonesia', 'rindu', 'sayang', 'melayu', 'koplo']
    }
    
    blob = TextBlob(lyrics.lower())
    words = set(blob.words)
    
    scores = {genre: sum(1 for keyword in kw_list if keyword in words) 
              for genre, kw_list in keywords.items()}
    
    # Jika tidak ada yang cocok, default ke pop
    detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
    logger.info(f"Genre terdeteksi dari kata kunci: '{detected_genre}'")
    return detected_genre

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    """Generate parameter musik berdasarkan genre dan analisis lirik"""
    params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy() # Use .copy() to avoid modifying global dict
    
    # Override tempo jika user input spesifik
    if user_tempo_input != 'auto':
        try:
            params['tempo'] = int(user_tempo_input)
            if not (60 <= params['tempo'] <= 200): # Batasan tempo yang wajar
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
        params['scale'] = 'minor' # Ubah ke minor untuk mood sedih
    elif sentiment > 0.3:
        params['mood'] = 'happy'
        params['scale'] = 'major' # Ubah ke major untuk mood bahagia
    
    # Pilih instrumen secara random dari available options
    # Iterasi melalui 'instruments' dictionary
    for category, instrument_choices in params['instruments'].items():
        available = [instr for instr in instrument_choices if instr in INSTRUMENTS]
        if available:
            params['instruments'][category] = random.choice(available)
        else:
            # Fallback ke instrumen default jika tidak ada yang cocok
            if category == 'melody':
                params['instruments'][category] = 'Acoustic Grand Piano'
            elif category == 'harmony':
                params['instruments'][category] = 'String Ensemble 1'
            elif category == 'bass':
                params['instruments'][category] = 'Acoustic Bass'
            else:
                params['instruments'][category] = None
            logger.warning(f"Tidak ada instrumen valid untuk kategori '{category}' pada genre '{genre}'. Menggunakan fallback: {params['instruments'][category]}")

    # drums_enabled sudah boolean, tidak perlu diproses seperti instrumen lain
    # params['drums_enabled'] tetap True/False

    # Generate chord progression
    base_chords = params['chord_progression']
    selected_chords = []
    for chord_name in base_chords:
        if chord_name in CHORDS:
            selected_chords.append(CHORDS[chord_name])
        else:
            logger.warning(f"Chord '{chord_name}' tidak ditemukan di dictionary CHORDS. Menggunakan C major sebagai fallback.")
            selected_chords.append(CHORDS['C']) # Fallback
    params['chords'] = selected_chords
    
    # Set genre di params agar bisa digunakan di create_midi_file
    params['genre'] = genre

    logger.info(f"Parameter musik untuk genre '{genre}' (Mood: {params['mood']}): Tempo={params['tempo']}BPM, Est. Durasi={params['duration_beats']} beats")
    logger.debug(f"  Melody: {params['instruments']['melody']} ({INSTRUMENTS.get(params['instruments']['melody'])}), Harmony: {params['instruments']['harmony']} ({INSTRUMENTS.get(params['instruments']['harmony'])}), "
                f"Bass: {params['instruments']['bass']} ({INSTRUMENTS.get(params['instruments']['bass'])}), Drums: {params['drums_enabled']}, Chords: {base_chords}")
    
    return params

def get_scale_notes(key, scale_name):
    """Mengembalikan daftar not MIDI dari skala tertentu berdasarkan root key"""
    root_midi = CHORDS.get(key, [60])[0] # C4 sebagai default root, ambil not pertama dari chord
    scale_intervals = SCALES.get(scale_name, SCALES['major'])
    return [root_midi + interval for interval in scale_intervals]

def generate_melody(params):
    """Generate melodi sederhana berdasarkan skala"""
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
    else: # happy or neutral
        patterns = [[1, 1, 0.5, 0.5, 1.5], [0.5, 1, 1.5, 1], [1, 1, 2]]
        velocities = [70, 85]
        
    current_pattern = random.choice(patterns)
    current_velocity = random.choice(velocities)
    
    total_beats_generated = 0
    time_pos = 0.0 # Posisi waktu absolut
    while total_beats_generated < duration_beats:
        for beat_duration_segment in current_pattern:
            if total_beats_generated + beat_duration_segment > duration_beats:
                beat_duration_segment = duration_beats - total_beats_generated
                if beat_duration_segment <= 0.001: break # Toleransi kecil untuk floating point

            # Pilih not dari skala
            note_idx = random.randint(0, len(scale_notes) - 1)
            # Sesuaikan oktaf untuk variasi
            octave_shift = random.choice([-12, 0, 12]) # -12 (down an octave), 0 (same octave), 12 (up an octave)
            pitch = scale_notes[note_idx] + octave_shift
            
            # Pastikan pitch dalam jangkauan MIDI (0-127)
            pitch = max(0, min(127, pitch))

            melody.append((pitch, time_pos, beat_duration_segment, current_velocity)) # pitch, time_pos, duration, velocity
            time_pos += beat_duration_segment
            total_beats_generated += beat_duration_segment
            if total_beats_generated >= duration_beats:
                break
        
        # Ganti pattern dan velocity untuk variasi setiap beberapa bar (misal 4 bar)
        if (total_beats_generated / 4) % 4 == 0 and total_beats_generated > 0:
            current_pattern = random.choice(patterns)
            current_velocity = random.choice(velocities)
            
    return melody

def generate_harmony(params):
    """Generate harmoni/chord progression"""
    chords = params['chords']
    duration_beats = params['duration_beats']

    harmony = []
    
    # Tentukan berapa lama setiap chord dimainkan
    # Bagi total durasi beats dengan jumlah chord. Jika tidak habis, chord terakhir yang menampung sisa.
    beats_per_chord_base = duration_beats // len(chords)
    
    # Velocity berdasarkan mood
    if params['mood'] == 'sad' or params['mood'] == 'emotional':
        velocity = 60
    elif params['mood'] == 'energetic' or params['mood'] == 'intense':
        velocity = 90
    else:
        velocity = 75

    current_beat = 0.0
    for i, chord_notes in enumerate(chords):
        # Durasi aktual untuk chord ini
        chord_duration = beats_per_chord_base
        if i == len(chords) - 1: # Chord terakhir menampung sisa beats
            chord_duration = duration_beats - current_beat
            
        if chord_duration <= 0.001: # Toleransi kecil untuk floating point
            break

        # Mainkan semua not dalam chord secara bersamaan
        for note in chord_notes:
            harmony.append((note, current_beat, chord_duration, velocity)) # pitch, start_beat, duration, velocity
        
        current_beat += chord_duration
    
    return harmony

def generate_bass_line(params):
    """Generate bass line sederhana"""
    chords = params['chords']
    duration_beats = params['duration_beats']

    bass_line = []
    
    # Tentukan berapa lama setiap chord dimainkan
    beats_per_chord_base = duration_beats // len(chords)

    # Velocity berdasarkan mood
    if params['mood'] == 'sad' or params['mood'] == 'emotional':
        velocity = 70
    elif params['mood'] == 'energetic' or params['mood'] == 'intense':
        velocity = 100
    else:
        velocity = 85
    
    current_beat = 0.0
    for i, chord_notes in enumerate(chords):
        root_note = chord_notes[0] - 24 # Satu atau dua oktaf di bawah C4 (60)
        root_note = max(24, min(root_note, 48)) # Batasi bass ke oktaf yang lebih rendah
        
        # Durasi aktual untuk chord ini
        chord_duration = beats_per_chord_base
        if i == len(chords) - 1: # Chord terakhir menampung sisa beats
            chord_duration = duration_beats - current_beat
            
        if chord_duration <= 0.001: # Toleransi kecil untuk floating point
            break

        # Contoh pattern bass: root on beat 1, then maybe a fifth or just hold
        for beat_in_chord_segment in range(int(chord_duration)):
            # Mainkan root pada awal setiap chord
            bass_line.append((root_note, current_beat + beat_in_chord_segment, 1, velocity)) 
            # Bisa ditambahkan variasi di sini, misal fifth di beat selanjutnya
            if beat_in_chord_segment + 0.5 < chord_duration:
                fifth = root_note + 7
                if fifth <= 48:
                    bass_line.append((fifth, current_beat + beat_in_chord_segment + 0.5, 0.5, velocity - 10))
                else:
                    bass_line.append((root_note, current_beat + beat_in_chord_segment + 0.5, 0.5, velocity - 10))

        current_beat += chord_duration
            
    return bass_line

def create_midi_file(params, output_path):
    """Buat file MIDI dari parameter musik"""
    tempo = params['tempo']
    duration_beats = params['duration_beats']
    
    # MIDIFile(num_tracks, ticks_per_beat)
    # Ticks_per_beat 120 adalah standar yang baik
    midi = MIDIFile(4, 120)  # 4 tracks: melody, harmony, bass, drums
    
    # Set tempo untuk semua track
    for i in range(4):
        midi.addTempo(i, 0, tempo)
    
    # Track 0: Melody (paling keras)
    if params['instruments']['melody']:
        program_num = INSTRUMENTS.get(params['instruments']['melody'], 0) # Default to Acoustic Grand Piano
        midi.addProgramChange(0, 0, 0, program_num) # Track 0, Channel 0, Time 0, Program Number
        
        melody_notes = generate_melody(params)
        
        for pitch, time_pos, duration, velocity in melody_notes:
            midi.addNote(0, 0, pitch, time_pos, duration, int(velocity * 1.2)) # REVISI: Melody 20% lebih keras (disesuaikan)
    
    # Track 1: Harmony/Chords
    if params['instruments']['harmony']:
        program_num = INSTRUMENTS.get(params['instruments']['harmony'], 48) # Default to String Ensemble 1
        midi.addProgramChange(1, 0, 0, program_num) # Track 1, Channel 0, Time 0, Program Number
        
        harmony_data = generate_harmony(params)
        
        # Harmony data is (pitch, start_beat, duration, velocity)
        for pitch, start_beat, duration, velocity in harmony_data:
            midi.addNote(1, 0, pitch, start_beat, duration, int(velocity * 0.8)) # REVISI: Harmony sedikit lebih rendah
    
    # Track 2: Bass
    if params['instruments']['bass']:
        program_num = INSTRUMENTS.get(params['instruments']['bass'], 33) # Default to Electric Bass finger
        midi.addProgramChange(2, 0, 0, program_num) # Track 2, Channel 0, Time 0, Program Number
        
        bass_notes = generate_bass_line(params)
        
        # Bass data is (pitch, start_beat, duration, velocity)
        for pitch, start_beat, duration, velocity in bass_notes:
            midi.addNote(2, 0, pitch, start_beat, duration, int(velocity * 1.1)) # REVISI: Bass sedikit lebih keras
    
    # Track 3: Drums (Channel 10)
    if params['drums_enabled']: # Gunakan drums_enabled
        midi.addProgramChange(3, 9, 0, 0)  # Track 3, Channel 9 (MIDI drums), Time 0, Program Number (default drum set)
        
        # Simple drum pattern
        for beat_pos in range(int(duration_beats)):
            # Kick on beats 1 and 3 of every 4-beat measure
            if beat_pos % 4 == 0 or beat_pos % 4 == 2:
                midi.addNote(3, 9, 36, beat_pos, 0.5, 110)  # Bass drum (MIDI note 36) - REVISI: Sedikit lebih keras
            # Snare on beats 2 and 4
            if beat_pos % 4 == 1 or beat_pos % 4 == 3:
                midi.addNote(3, 9, 38, beat_pos, 0.5, 95)  # Snare drum (MIDI note 38)
            # Hi-hat every beat
            midi.addNote(3, 9, 42, beat_pos, 0.25, 75) # Closed hi-hat (MIDI note 42)
            
            # Tambahkan variasi untuk Latin/Dangdut drums
            if params['genre'] in ['latin', 'dangdut'] and beat_pos % 2 == 0:
                random_perc_note = random.choice([49, 54, 56, 58, 60]) # Cowbell, Tambourine, Conga, Bongo, Timbale
                midi.addNote(3, 9, random_perc_note, beat_pos + 0.5, 0.25, 60)

    # Write MIDI file
    with open(output_path, 'wb') as f:
        midi.writeFile(f)
    
    logger.info(f"MIDI generated: {output_path.name}")
    return True

def midi_to_audio_pyfluidsynth(midi_path, output_wav_path, soundfont_path):
    """Konversi MIDI ke WAV menggunakan pyfluidsynth"""
    if not FLUIDSYNTH_BINDING_AVAILABLE:
        return False # Cannot use pyfluidsynth if not imported

    try:
        fs = pyfluidsynth_lib.Synth()
        fs.start()
        
        sfid = fs.sfload(str(soundfont_path))
        if sfid == pyfluidsynth_lib.ERROR_CODE:
            logger.error("Gagal memuat SoundFont dengan pyfluidsynth.")
            fs.delete()
            return False
        
        logger.debug(f"SoundFont '{soundfont_path.name}' dimuat (ID: {sfid})")
        
        # pyfluidsynth's direct file rendering is often not as straightforward as the CLI
        # The common approach is to play events into a buffer and then save that.
        # However, for simplicity and robustness in this app, we'll favor subprocess.
        # This part of the code serves more as a placeholder if direct pyfluidsynth file
        # rendering becomes feasible and robust in future versions.
        logger.warning("pyfluidsynth binding tidak mendukung direct render MIDI file ke WAV seperti command line secara langsung. Menggunakan subprocess.")
        fs.delete()
        return False

    except Exception as e:
        logger.error(f"Error pyfluidsynth konversi: {e}")
        return False

def midi_to_audio_subprocess(midi_path, output_wav_path, soundfont_path):
    """Konversi MIDI ke WAV menggunakan FluidSynth binary via subprocess"""
    try:
        cmd = [
            'fluidsynth',
            '-F', str(output_wav_path), 
            '-r', '44100',  # Sample rate
            '-ni',          # Non-interactive mode
            '-g', '1.0',    # Gain
            '-l',           # Loop mode off
            str(soundfont_path),
            str(midi_path)
        ]
        
        logger.debug(f"Menjalankan FluidSynth subprocess: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and output_wav_path.exists():
            file_size = output_wav_path.stat().st_size / 1024  # KB
            logger.info(f"WAV generated: {output_wav_path.name} ({file_size:.1f} KB)")
            return True
        else:
            logger.error(f"FluidSynth subprocess error (code: {result.returncode}): {result.stderr}")
            if not soundfont_path.exists():
                logger.error(f"SoundFont tidak ditemukan di: {soundfont_path}")
            if not midi_path.exists():
                logger.error(f"MIDI file tidak ditemukan di: {midi_path}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FluidSynth subprocess timeout - file MIDI mungkin terlalu kompleks atau soundfont terlalu besar.")
        return False
    except FileNotFoundError:
        logger.error("Executable 'fluidsynth' tidak ditemukan. Pastikan sudah terinstal dan ada di PATH.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in FluidSynth subprocess: {e}")
        return False

def midi_to_audio(midi_path, output_wav_path):
    """Fungsi pembungkus untuk konversi MIDI ke WAV"""
    # Prefer subprocess karena lebih stabil untuk rendering dari file MIDI ke WAV
    # pyfluidsynth bindings cenderung lebih cocok untuk live playing atau manipulasi event.
    return midi_to_audio_subprocess(midi_path, output_wav_path, SOUNDFONT_PATH)

def wav_to_mp3(wav_path, mp3_path):
    """Konversi WAV ke MP3 menggunakan pydub/ffmpeg dengan kompresi dan sub-bass"""
    try:
        logger.debug(f"Membaca WAV: {wav_path.name}")
        audio = AudioSegment.from_wav(wav_path)
        
        # --- FFmpeg Audio Filters ---
        # Kompresi ringan (mengurangi dynamic range, membuat lebih 'padat')
        # Bass boost ringan (meningkatkan frekuensi rendah untuk 'ketebalan')
        # Loudness normalization untuk volume akhir yang konsisten (opsional tapi sangat direkomendasikan)
        audio_filters = [
            "compand=attacks=0:decays=0:points=-80/-90|-40/-40|-20/-20|0/0", # Compand filter (dynamic range compression)
            "bass=g=8:f=80:w=0.7", # Bass boost: gain 8dB, freq 80Hz, width 0.7
            "loudnorm=I=-16:TP=-1.5:LRA=11", # Loudness normalization untuk volume akhir yang konsisten
        ]
        
        # Konversi list filter ke string yang dipisahkan koma
        ffmpeg_audio_filters = ",".join(audio_filters)
        
        logger.debug(f"Mengekspor ke MP3: {mp3_path.name} dengan filter: {ffmpeg_audio_filters}")
        
        # Pydub.export() memungkinkan passing parameter ffmpeg_options
        audio.export(
            mp3_path, 
            format='mp3', 
            bitrate='192k',
            parameters=["-af", ffmpeg_audio_filters] # Menerapkan filter audio
        )
        
        file_size = mp3_path.stat().st_size / 1024  # KB
        logger.info(f"MP3 generated: {mp3_path.name} ({file_size:.1f} KB)")
        return True
        
    except Exception as e:
        logger.error(f"Error konversi WAV ke MP3 (FFmpeg/pydub) dengan filter: {e}")
        # Info lebih lanjut jika ffmpeg tidak ditemukan
        if shutil.which('ffmpeg') is None:
            logger.error("Executable 'ffmpeg' tidak ditemukan. Install dengan: sudo apt install ffmpeg")
        return False

def cleanup_old_files(directory, max_age_hours=1):
    """Bersihkan file audio lama (mp3, wav, mid)"""
    logger.info(f"Memulai pembersihan file lama di {directory}. File lebih tua dari {max_age_hours} jam akan dihapus.")
    deleted_count = 0
    
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    for file_path in Path(directory).glob("*.{mp3,wav,mid}"):
        try:
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_time < cutoff_time:
                file_path.unlink()
                logger.info(f"  - Menghapus file lama: {file_path.name}")
                deleted_count += 1
        except Exception as e:
            logger.warning(f"Error menghapus {file_path.name}: {e}")
    
    logger.info(f"Pembersihan selesai. {deleted_count} file lama dihapus.")
    return deleted_count

def generate_unique_id(lyrics):
    """Generate unique ID berdasarkan hash lirik dan timestamp"""
    hash_object = hashlib.md5(lyrics.encode('utf-8')).hexdigest()
    timestamp = str(int(time.time()))
    return f"{hash_object[:8]}_{timestamp}"

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
        <h1>ðµ Generate Instrumental Music</h1>
        <p>Masukkan lirik lagu Anda dan pilih genre untuk generate musik instrumental otomatis!</p>
        
        <form id="musicForm">
            <label for="lyrics">Lirik Lagu:</label><br>
            <textarea id="lyrics" name="lyrics" placeholder="Masukkan lirik lagu Anda di sini...&#10;&#10;Contoh:&#10;[Verse 1]&#10;Di malam yang sunyi kukenang dirimu...&#10;[Chorus]&#10;Cinta ini takkan pernah usai..." required></textarea><br>
            
            <label for="genre">Genre Musik:</label><br>
            <select id="genre" name="genre">
                <option value="auto">Auto-Detect</option>
                <option value="pop">Pop</option>
                <option value="rock">Rock</option>
                <option value="metal">Metal</option>
                <option value="ballad">Ballad</option>
                <option value="blues">Blues</option>
                <option value="jazz">Jazz</option>
                <option value="hiphop">Hip-Hop</option>
                <option value="latin">Latin</option>
                <option value="dangdut">Dangdut</option>
            </select><br>
            
            <label for="tempo">Tempo (BPM):</label><br>
            <input type="number" id="tempo" name="tempo" min="60" max="200" placeholder="Auto">
            <small>(Kosongkan untuk auto-detect atau gunakan nilai default genre)</small><br><br>
            
            <button type="submit">ð¼ Generate Musik!</button>
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
                statusDiv.innerHTML = '<p class="success-message">â³ Sedang generate musik... Ini mungkin memakan waktu 1-2 menit.</p>';
                audioPlayer.style.display = 'none';
                downloadLink.innerHTML = '';
                
                try {
                    const response = await fetch('/generate-instrumental', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        statusDiv.innerHTML = `<p class="success-message">â Musik berhasil digenerate!</p>
                                             <p><strong>Genre:</strong> ${data.genre}</p>
                                             <p><strong>Tempo:</strong> ${data.tempo} BPM</p>
                                             <p><strong>Durasi:</strong> ${data.duration} detik</p>`;
                        
                        audioPlayer.src = `/static/audio_output/${data.filename}`;
                        audioPlayer.style.display = 'block';
                        audioPlayer.load();
                        
                        downloadLink.innerHTML = `<p><a href="/static/audio_output/${data.filename}" download="${data.filename}">ð¾ Download MP3</a></p>`;
                    } else {
                        const errorData = await response.json();
                        statusDiv.innerHTML = `<p class="error-message">â Error: ${errorData.error || 'Gagal generate musik'}</p>`;
                    }
                } catch (error) {
                    statusDiv.innerHTML = `<p class="error-message">â Network Error: ${error.message}. Pastikan server berjalan dan koneksi internet stabil.</p>`;
                    console.error("Fetch error:", error);
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/generate-instrumental', methods=['OPTIONS', 'POST'])
def generate_instrumental_endpoint(): # Mengubah nama fungsi untuk menghindari konflik
    """Endpoint utama untuk generate instrumental"""
    if request.method == 'OPTIONS':
        return '', 200
    
    logger.info("Menerima permintaan POST untuk /generate-instrumental.")
    
    try:
        # Ambil data dari request
        data = request.form if request.form else request.json
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto').lower()
        tempo_input = data.get('tempo', 'auto')
        
        if not lyrics:
            return jsonify({'error': 'Lirik tidak boleh kosong.'}), 400
        
        logger.info(f"Memproses lirik: '{lyrics[:100]}...' (panjang: {len(lyrics)} karakter)")
        logger.info(f"Input pengguna: Genre='{genre_input}', Tempo='{tempo_input}'")
        
        # Deteksi genre jika auto
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        
        # Generate parameter musik
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Generate unique ID
        unique_id = generate_unique_id(lyrics)
        midi_filename = f"{unique_id}.mid"
        wav_filename = f"{unique_id}.wav"
        mp3_filename = f"{unique_id}.mp3"
        
        midi_path = AUDIO_OUTPUT_DIR / midi_filename
        wav_path = AUDIO_OUTPUT_DIR / wav_filename
        mp3_path = AUDIO_OUTPUT_DIR / mp3_filename
        
        logger.info(f"Memulai generasi musik untuk ID: {unique_id}")
        
        # Buat MIDI file
        if not create_midi_file(params, midi_path):
            return jsonify({'error': 'Gagal membuat file MIDI.'}), 500
        
        # Konversi ke WAV
        if not midi_to_audio(midi_path, wav_path):
            # Bersihkan MIDI jika gagal
            if midi_path.exists():
                midi_path.unlink()
            return jsonify({'error': 'Gagal konversi MIDI ke audio. Pastikan FluidSynth terinstal dan SoundFont benar.'}), 500
        
        # Konversi ke MP3
        if not wav_to_mp3(wav_path, mp3_path):
            # Bersihkan file sementara jika gagal
            if wav_path.exists():
                wav_path.unlink()
            if midi_path.exists():
                midi_path.unlink()
            return jsonify({'error': 'Gagal konversi audio ke MP3. Pastikan FFmpeg terinstal.'}), 500
        
        # Hitung durasi
        duration_seconds = params['duration_beats'] * 60 / params['tempo'] # Estimasi durasi
        try:
            if mp3_path.exists():
                audio = AudioSegment.from_mp3(mp3_path)
                duration_seconds = len(audio) / 1000
        except Exception as e:
            logger.warning(f"Gagal mendapatkan durasi akurat dari MP3: {e}. Menggunakan estimasi.")
            
        # Bersihkan file sementara (MIDI dan WAV)
        if midi_path.exists():
            midi_path.unlink()
        if wav_path.exists():
            wav_path.unlink()
        logger.info("File sementara (MIDI dan WAV) berhasil dibersihkan.")
        
        logger.info(f"Generasi selesai untuk ID {unique_id}. File: {mp3_filename} ({mp3_path.stat().st_size/1024:.1f} KB)")
        
        return jsonify({
            'success': True,
            'filename': mp3_filename,
            'audio_url': f'/static/audio_output/{mp3_filename}', # Path relatif untuk player
            'download_url': request.url_root + f'static/audio_output/{mp3_filename}', # URL absolut untuk download
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration_seconds, 1),
            'id': unique_id,
        })
        
    except Exception as e:
        logger.error(f"Error saat generasi instrumental: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve file audio dari direktori output"""
    try:
        file_path = AUDIO_OUTPUT_DIR / filename
        if not file_path.exists():
            logger.warning(f"File audio tidak ditemukan: {file_path}")
            return "File not found", 404
        
        mimetype = 'audio/mpeg' if filename.endswith('.mp3') else 'audio/wav'
        logger.info(f"Serving audio file: {filename} (mimetype: {mimetype})")
        
        # REVISI: Tambahkan header Content-Disposition untuk memaksa download
        response = send_from_directory(
            AUDIO_OUTPUT_DIR,
            filename,
            mimetype=mimetype,
            as_attachment=True,  # Ini yang paling penting: memaksa download
            download_name=filename # Memberikan nama file untuk download
        )
        return response
        
    except Exception as e:
        logger.error(f"Error serving audio {filename}: {e}")
        return "Internal server error", 500

def get_local_ip():
    """Dapatkan IP lokal untuk akses jaringan"""
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
    """Fungsi utama untuk start server"""
    logger.info("ð Memulai Flask Generate Instrumental dengan Latin & Dangdut Support!")
    
    try:
        # Cek SoundFont
        if not SOUNDFONT_PATH.exists():
            logger.critical(f"SoundFont tidak ditemukan: {SOUNDFONT_PATH}")
            logger.critical("Download GeneralUser GS dari: https://musical-artifacts.com/artifacts/661 dan letakkan di direktori yang sama dengan app.py.")
            sys.exit(1)
        
        # Cek dependensi Python
        available_deps = check_python_dependencies()
        logger.info(f"Dependensi Python terdeteksi: {', '.join(available_deps)}")
        
        if len(available_deps) < 5: # Minimal flask-cors, midiutil, textblob, pyphen, pydub
            logger.critical("Dependensi Python tidak lengkap. Install dengan: pip install flask-cors MIDIUtil textblob pyphen pydub")
            sys.exit(1)
            
        # Cek executable FluidSynth dan FFmpeg
        fluidsynth_path = shutil.which('fluidsynth')
        ffmpeg_path = shutil.which('ffmpeg')
        
        logger.info(f"Menggunakan executable FluidSynth: '{fluidsynth_path or 'TIDAK DITEMUKAN'}'")
        logger.info(f"Menggunakan executable FFmpeg (via pydub): '{ffmpeg_path or 'TIDAK DITEMUKAN'}'")
        logger.info(f"Menggunakan SoundFont: '{SOUNDFONT_PATH}'")
        
        if not fluidsynth_path:
            logger.critical("Executable 'fluidsynth' tidak ditemukan. Install dengan: sudo apt install fluidsynth")
            sys.exit(1)
        if not ffmpeg_path:
            logger.critical("Executable 'ffmpeg' tidak ditemukan. Install dengan: sudo apt install ffmpeg")
            sys.exit(1)

        # Pembersihan file lama
        cleanup_old_files(AUDIO_OUTPUT_DIR)
        
        # Info server
        local_ip = get_local_ip()
        logger.info("Server akan berjalan di http://127.0.0.1:5000 (lokal) dan di jaringan Anda.")
        logger.info(f"Akses lokal (browser): http://127.0.0.1:5000")
        logger.info(f"Akses jaringan (IP lokal): http://{local_ip}:5000")
        logger.info("Untuk membuat server dapat diakses publik, gunakan tunneling seperti Pinggy: pinggy -p 5000")
        logger.info("ð CORS diaktifkan untuk semua origin (mode development).")
        logger.info("â¨ï¸ Untuk menghentikan server, tekan Ctrl+C.")
        
        # Jalankan Flask
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True, # Set False untuk production
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("Server dihentikan oleh user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Error fatal saat memulai server: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main_app_runner()
