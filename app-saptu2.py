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
# Impor 'compress_dynamic_range' bersama dengan 'normalize'
from pydub.effects import normalize as pydub_normalize, compress_dynamic_range

# --- [Konfigurasi Awal dan Variabel Global] ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'

SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',
    BASE_DIR / 'GeneralUser GS v1.471.sf2',
    BASE_DIR / 'FluidR3_GM.sf2',
]
for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        break
if not SOUNDFONT_PATH:
    logger.warning("No SoundFont found. Audio generation will not work.")

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

# --- [Daftar Instrumen, Kunci, Skala, dll.] ---
INSTRUMENTS = {
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2, 'Honky-tonk Piano': 3,
    'Electric Piano 1': 4, 'Electric Piano 2': 5, 'Harpsichord': 6, 'Clavinet': 7,
    'Celesta': 8, 'Glockenspiel': 9, 'Music Box': 10, 'Vibraphone': 11, 'Marimba': 12, 'Xylophone': 13,
    'Tubular Bells': 14, 'Dulcimer': 15, 'Drawbar Organ': 16, 'Percussive Organ': 17, 'Rock Organ': 18,
    'Church Organ': 19, 'Reed Organ': 20, 'Nylon String Guitar': 24, 'Steel String Guitar': 25,
    'Jazz Electric Guitar': 26, 'Clean Electric Guitar': 27, 'Muted Electric Guitar': 28, 'Overdriven Guitar': 29,
    'Distortion Guitar': 30, 'Guitar Harmonics': 31, 'Acoustic Bass': 32, 'Electric Bass finger': 33,
    'Electric Bass pick': 34, 'Fretless Bass': 35, 'Slap Bass 1': 36, 'Slap Bass 2': 37, 'Synth Bass 1': 38,
    'Synth Bass 2': 39, 'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43, 'Tremolo Strings': 44,
    'Pizzicato Strings': 45, 'Orchestral Strings': 46, 'String Ensemble 1': 48, 'String Ensemble 2': 49,
    'Synth Strings 1': 50, 'Synth Strings 2': 51, 'Choir Aahs': 52, 'Voice Oohs': 53, 'Synth Voice': 54,
    'Orchestra Hit': 55, 'Trumpet': 56, 'Trombone': 57, 'Tuba': 58, 'Muted Trumpet': 59, 'French Horn': 60,
    'Brass Section': 61, 'Synth Brass 1': 62, 'Synth Brass 2': 63, 'Soprano Sax': 64, 'Alto Sax': 65,
    'Tenor Sax': 66, 'Baritone Sax': 67, 'Oboe': 68, 'English Horn': 69, 'Bassoon': 70, 'Clarinet': 71,
    'Piccolo': 72, 'Flute': 73, 'Recorder': 74, 'Pan Flute': 75, 'Blown Bottle': 76, 'Shakuhachi': 77,
    'Whistle': 78, 'Ocarina': 79, 'Square Wave': 80, 'Sawtooth Wave': 81, 'New Age Pad': 88, 'Warm Pad': 89,
    'Poly Synth Pad': 90, 'Choir Pad': 91, 'Bowed Glass Pad': 92, 'Sitar': 104, 'Banjo': 105, 'Shamisen': 106,
    'Koto': 107, 'Kalimba': 108, 'Bagpipe': 109, 'Fiddle': 110, 'Shanai': 111, 'Gamelan': 114, 'Gunshot': 127
}

CHORDS = {
    'C': [60, 64, 67], 'C#': [61, 65, 68], 'Db': [61, 65, 68], 'D': [62, 66, 69], 'D#': [63, 67, 70],
    'Eb': [63, 67, 70], 'E': [64, 68, 71], 'F': [65, 69, 72], 'F#': [66, 70, 73], 'Gb': [66, 70, 73],
    'G': [67, 71, 74], 'G#': [68, 72, 75], 'Ab': [68, 72, 75], 'A': [69, 73, 76], 'A#': [70, 74, 77],
    'Bb': [70, 74, 77], 'B': [71, 75, 78], 'Cm': [60, 63, 67], 'C#m': [61, 64, 68], 'Dm': [62, 65, 69],
    'D#m': [63, 66, 70], 'Em': [64, 67, 71], 'Fm': [65, 68, 72], 'F#m': [66, 69, 73], 'Gm': [67, 70, 74],
    'G#m': [68, 71, 75], 'Am': [69, 72, 76], 'A#m': [70, 73, 77], 'Bm': [71, 74, 78], 'C7': [60, 64, 67, 70],
    'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74], 'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77],
    'A7': [69, 73, 76, 79], 'B7': [71, 75, 78, 82], 'Cmaj7': [60, 64, 67, 71], 'Dm7': [62, 65, 69, 72],
    'Em7': [64, 67, 71, 74], 'C5': [60, 67], 'D5': [62, 69], 'E5': [64, 71], 'F5': [65, 72], 'G5': [67, 74],
    'A5': [69, 76], 'B5': [71, 78], 'Eb5': [63, 70], 'F#5': [66, 73]
}

SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11], 'minor': [0, 2, 3, 5, 7, 8, 10], 'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9], 'latin': [0, 2, 4, 5, 7, 9, 10], 'dangdut': [0, 1, 4, 5, 7, 8, 11]
}

DRUM_NOTES = {
    'kick': 36, 'snare': 38, 'hat_closed': 42, 'ride': 51, 'crash': 49,
    'tom_high': 50, 'tom_mid': 47, 'tom_low': 45, 'tom_floor': 43
}

GENRE_PARAMS = {
    'pop': {
        'tempo': 120, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Clean Electric Guitar',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'Electric Piano 1', # Diubah agar lebih clean
            'bass': 'Electric Bass finger'
        },
        'drums_enabled': True, 'chord_progressions': [['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G']], 'bass_style': 'melodic'
    },
    'rock': {
        'tempo': 130, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {'melody': 'Overdriven Guitar', 'rhythm_primary': 'Distortion Guitar', 'rhythm_secondary': 'Rock Organ', 'bass': 'Electric Bass pick'},
        'drums_enabled': True, 'chord_progressions': [['E5', 'A5', 'B5', 'A5'], ['Em', 'G', 'D', 'A']], 'bass_style': 'driving'
    },
    'metal': {
        'tempo': 140, 'key': 'E', 'scale': 'minor',
        'instruments': {'melody': 'Distortion Guitar', 'rhythm_primary': 'Overdriven Guitar', 'rhythm_secondary': 'Synth Strings 2', 'bass': 'Electric Bass pick'},
        'drums_enabled': True, 'chord_progressions': [['E5', 'G5', 'A5', 'C5'], ['Em', 'C', 'G', 'D']], 'bass_style': 'heavy'
    },
    'ballad': {
        'tempo': 70, 'key': 'C', 'scale': 'major',
        'instruments': {'melody': 'Acoustic Grand Piano', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'Warm Pad', 'bass': 'Acoustic Bass'},
        'drums_enabled': True, 'chord_progressions': [['C', 'G', 'Am', 'F'], ['F', 'C', 'G', 'Am']], 'bass_style': 'sustained'
    },
    'blues': {
        'tempo': 110, 'key': 'A', 'scale': 'blues',
        'instruments': {'melody': 'Tenor Sax', 'rhythm_primary': 'Electric Piano 2', 'rhythm_secondary': 'Drawbar Organ', 'bass': 'Acoustic Bass'},
        'drums_enabled': True, 'chord_progressions': [['A7', 'D7', 'E7', 'A7']], 'bass_style': 'walking'
    },
    'jazz': {
        'tempo': 140, 'key': 'C', 'scale': 'major',
        'instruments': {'melody': 'Trumpet', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'Brass Section', 'bass': 'Acoustic Bass'},
        'drums_enabled': True, 'chord_progressions': [['Dm7', 'G7', 'Cmaj7', 'A7']], 'bass_style': 'walking'
    },
    'hiphop': {
        'tempo': 95, 'key': 'Am', 'scale': 'minor',
        'instruments': {'melody': 'Synth Voice', 'rhythm_primary': 'Electric Piano 2', 'rhythm_secondary': 'Synth Strings 1', 'bass': 'Synth Bass 1'},
        'drums_enabled': True, 'chord_progressions': [['Am', 'F', 'C', 'G']], 'bass_style': 'syncopated'
    },
    'latin': {
        'tempo': 100, 'key': 'G', 'scale': 'latin',
        'instruments': {'melody': 'Nylon String Guitar', 'rhythm_primary': 'Acoustic Grand Piano', 'rhythm_secondary': 'Brass Section', 'bass': 'Acoustic Bass'},
        'drums_enabled': True, 'chord_progressions': [['G', 'C', 'D', 'G']], 'bass_style': 'tumbao'
    },
    'dangdut': {
        'tempo': 130, 'key': 'Am', 'scale': 'dangdut',
        'instruments': {'melody': 'Flute', 'rhythm_primary': 'Gamelan', 'rhythm_secondary': 'Clean Electric Guitar', 'bass': 'Electric Bass finger'},
        'drums_enabled': True, 'chord_progressions': [['Am', 'G', 'F', 'Am']], 'bass_style': 'offbeat_syncopated'
    }
}

# --- [Fungsi Helper] ---

def chord_names_to_midi_notes(chord_names):
    return [CHORDS.get(c, CHORDS['C']) for c in chord_names]

def select_progression(params, lyrics=""):
    return random.choice(params['chord_progressions'])

def detect_genre_from_lyrics(lyrics):
    if not lyrics: return 'pop'
    keywords = {
        'pop': ['love', 'heart', 'dream', 'dance', 'tonight'], 'rock': ['rock', 'fire', 'wild', 'scream', 'freedom'],
        'metal': ['dark', 'scream', 'rage', 'shadow', 'death'], 'ballad': ['sad', 'memory', 'tears', 'alone', 'heartbreak'],
        'blues': ['soul', 'trouble', 'baby', 'lonely', 'rain'], 'jazz': ['swing', 'harmony', 'night', 'sax', 'blue'],
        'hiphop': ['street', 'beat', 'flow', 'hustle', 'city'], 'latin': ['dance', 'passion', 'fiesta', 'caliente', 'amor'],
        'dangdut': ['cinta', 'hati', 'rindu', 'sayang', 'melayu']
    }
    try:
        words = set(TextBlob(lyrics.lower()).words)
        scores = {genre: sum(1 for kw in kw_list if kw in words) for genre, kw_list in keywords.items()}
        detected_genre = max(scores, key=scores.get)
        return detected_genre if scores[detected_genre] > 0 else 'pop'
    except Exception: return 'pop'

def find_best_instrument(choice):
    if not choice: return 'Acoustic Grand Piano'
    choice_lower = str(choice).lower().strip()
    for instr_name in INSTRUMENTS:
        if choice_lower in instr_name.lower(): return instr_name
    return 'Acoustic Grand Piano'

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    params = GENRE_PARAMS.get(genre.lower(), GENRE_PARAMS['pop']).copy()
    params['genre'] = genre
    if user_tempo_input != 'auto':
        try: params['tempo'] = max(60, min(200, int(user_tempo_input)))
        except (ValueError, TypeError): pass
    for category in ['melody', 'rhythm_primary', 'rhythm_secondary', 'bass']:
        params['instruments'][category] = find_best_instrument(params['instruments'][category])
    selected_progression_names = select_progression(params, lyrics)
    params['chords'] = chord_names_to_midi_notes(selected_progression_names)
    params['selected_progression'] = selected_progression_names
    logger.info(f"Params: {genre}, Tempo={params['tempo']}BPM, Progression={selected_progression_names}")
    return params

def get_scale_notes(key, scale_name):
    root_midi = CHORDS.get(key, CHORDS['C'])[0]
    return [root_midi + i for i in SCALES.get(scale_name, SCALES['major'])]

# --- [Fungsi Generasi Musik] ---

def generate_melody_section(params, section_type, section_beats, chord_prog):
    scale_notes = get_scale_notes(params['key'], params['scale'])
    events, velocity_base, note_density = [], 85, 0.8
    if section_type in ['intro', 'interlude']: velocity_base, note_density = 70, 0.5
    elif section_type == 'verse': velocity_base, note_density = 80, 0.7
    elif section_type == 'chorus': velocity_base, note_density = 100, 0.9
    elif section_type == 'bridge': velocity_base, note_density = 90, 0.6
    elif section_type == 'outro': velocity_base, note_density = 65, 0.4
    beats_per_chord = section_beats / max(1, len(chord_prog))
    for i in range(int(section_beats * 2)):
        if random.random() > note_density: continue
        current_beat = i * 0.5
        chord = chord_prog[min(int(current_beat / beats_per_chord), len(chord_prog) - 1)]
        possible_notes = [n for n in scale_notes if n % 12 in [c % 12 for c in chord]] or scale_notes
        pitch = random.choice(possible_notes)
        if section_type == 'chorus' and random.random() < 0.3: pitch += 12
        pitch = max(48, min(84, pitch))
        velocity = velocity_base + random.randint(-5, 5)
        duration = random.choice([0.4, 0.9, 1.4])
        events.append((pitch, current_beat, duration, velocity))
    return events

def generate_rhythm_primary_section(params, section_type, section_beats, chord_prog):
    events = []
    if section_type in ['intro', 'outro']: pattern = [(0, 4)]
    elif section_type in ['verse', 'bridge']: pattern = [(0, 1), (1, 1), (2, 1), (3, 1)]
    else: pattern = [(0, 0.5), (0.5, 0.5), (1, 1), (2, 0.5), (2.5, 0.5), (3, 1)]
    beats_per_chord = section_beats / max(1, len(chord_prog))
    time_pos = 0.0
    for chord_notes in chord_prog:
        for beat_offset, duration in pattern:
            current_beat = time_pos + beat_offset
            if current_beat < time_pos + beats_per_chord and current_beat < section_beats:
                for note in chord_notes:
                    velocity = 80 if 'chorus' in section_type else 70
                    events.append((note, current_beat, duration, random.randint(velocity - 5, velocity + 5)))
        time_pos += beats_per_chord
    return events

def generate_rhythm_secondary_section(params, section_type, section_beats, chord_prog):
    events, time_pos = [], 0.0
    beats_per_chord = section_beats / max(1, len(chord_prog))
    for chord_notes in chord_prog:
        for note in chord_notes:
            events.append((note - 12, time_pos, beats_per_chord * 0.95, 65))
        time_pos += beats_per_chord
    return events

def generate_bass_line_section(params, section_type, section_beats, chord_prog):
    events, time_pos = [], 0.0
    beats_per_chord = section_beats / max(1, len(chord_prog))
    for chord_notes in chord_prog:
        root_note = chord_notes[0] - 24
        if section_type in ['intro', 'outro']:
            events.append((root_note, time_pos, beats_per_chord, 90))
        elif section_type == 'verse':
            events.append((root_note, time_pos, 1.0, 100))
            if beats_per_chord > 2: events.append((root_note, time_pos + 2, 1.0, 95))
        else:
            for beat in range(int(beats_per_chord)):
                events.append((root_note, time_pos + beat, 0.8, 110))
        time_pos += beats_per_chord
    return events

def generate_sub_bass_section(params, section_type, section_beats, chord_prog):
    """Generates a simple, held root note sub-bass line."""
    events, time_pos = [], 0.0
    beats_per_chord = section_beats / max(1, len(chord_prog))
    
    if section_type == 'intro':
        return []

    for chord_notes in chord_prog:
        root_note = chord_notes[0]
        sub_note = root_note - 36
        sub_note = max(24, min(36, sub_note)) 
        duration = beats_per_chord * 0.95 
        events.append((sub_note, time_pos, duration, 100))
        time_pos += beats_per_chord
        
    return events

def generate_drum_fill(duration_beats):
    events, num_steps = [], int(duration_beats * 4)
    fill_notes = [DRUM_NOTES['snare'], DRUM_NOTES['tom_high'], DRUM_NOTES['tom_mid'], DRUM_NOTES['tom_low']]
    for i in range(num_steps):
        note = random.choice(fill_notes)
        velocity = 90 + int((i / num_steps) * 30)
        events.append((note, i * (duration_beats / num_steps), 0.2, velocity))
    events.append((DRUM_NOTES['crash'], duration_beats, 1.5, 120))
    return events

def generate_drum_pattern_section(params, section_type, section_beats):
    events = []
    if section_type == 'intro' or (params['genre'] == 'ballad' and section_type != 'chorus'):
        for beat in range(int(section_beats)):
            if beat % 4 == 0: events.append((DRUM_NOTES['kick'], float(beat), 0.5, 80))
            events.append((DRUM_NOTES['hat_closed'], float(beat), 0.2, 60))
    elif section_type in ['verse', 'bridge']:
        for beat in range(int(section_beats)):
            events.append((DRUM_NOTES['kick'], float(beat), 0.5, 100))
            if beat % 2 == 1: events.append((DRUM_NOTES['snare'], float(beat), 0.5, 90))
            for sub_beat in [0.0, 0.5]: events.append((DRUM_NOTES['hat_closed'], float(beat) + sub_beat, 0.2, 70))
    else:
        for beat in range(int(section_beats)):
            events.append((DRUM_NOTES['kick'], float(beat), 0.5, 110))
            if beat % 2 == 1: events.append((DRUM_NOTES['snare'], float(beat), 0.5, 105))
            for sub_beat in [0.0, 0.5]: events.append((DRUM_NOTES['ride'], float(beat) + sub_beat, 0.3, 80))
    if section_type in ['intro', 'chorus']:
        events.append((DRUM_NOTES['crash'], 0.0, 2.0, 115))
    return events

def build_song_structure(params):
    prog = params['chords'] or [CHORDS['C']]
    structure = [
        ('intro', 8, prog[:2] if len(prog) > 1 else prog),
        ('verse', 16, prog),
        ('pre_chorus', 8, prog[-2:] + prog[:2] if len(prog) > 3 else prog),
        ('chorus', 16, prog),
        ('verse', 16, prog),
        ('chorus', 16, prog),
        ('bridge', 8, prog[1:] + prog[:1] if len(prog) > 1 else prog),
        ('chorus', 16, prog),
        ('outro', 8, [prog[-1]])
    ]
    params['duration_beats'] = sum(s[1] for s in structure)
    logger.info(f"Structure: {len(structure)} sections, {params['duration_beats']} beats")
    return structure

# --- [Fungsi Utama Pembuatan MIDI] ---

def create_midi_file(params, output_path):
    try:
        start_time = time.time()
        tempo, ticks_per_beat = params['tempo'], 480
        mid = MidiFile(type=1, ticks_per_beat=ticks_per_beat)

        tracks = {name: MidiTrack() for name in ['melody', 'rhythm_primary', 'rhythm_secondary', 'bass', 'sub_bass', 'drums']}
        for track in tracks.values(): mid.tracks.append(track)
        
        tracks['melody'].append(MetaMessage('set_tempo', tempo=bpm2tempo(tempo), time=0))

        # --- Pengaturan Instrumen dan Kontrol Efek ---
        # Melodi (Ch 0)
        prog = INSTRUMENTS.get(params['instruments']['melody'], 0)
        tracks['melody'].append(Message('program_change', channel=0, program=prog, time=0))
        tracks['melody'].append(Message('control_change', channel=0, control=7, value=100, time=0)) 

        # Rhythm 1 (Ch 1)
        prog = INSTRUMENTS.get(params['instruments']['rhythm_primary'], 0)
        tracks['rhythm_primary'].append(Message('program_change', channel=1, program=prog, time=0))
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=7, value=80, time=0)) 
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=91, value=0, time=0))
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=93, value=0, time=0))
        tracks['rhythm_primary'].append(Message('control_change', channel=1, control=72, value=20, time=0))

        # Rhythm 2 (Ch 2)
        prog = INSTRUMENTS.get(params['instruments']['rhythm_secondary'], 0)
        tracks['rhythm_secondary'].append(Message('program_change', channel=2, program=prog, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=7, value=70, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=91, value=0, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=93, value=0, time=0))
        tracks['rhythm_secondary'].append(Message('control_change', channel=2, control=72, value=20, time=0))

        # Bass (Ch 3)
        prog = INSTRUMENTS.get(params['instruments']['bass'], 0)
        tracks['bass'].append(Message('program_change', channel=3, program=prog, time=0))
        tracks['bass'].append(Message('control_change', channel=3, control=7, value=110, time=0))

        # Sub Bass (Ch 4)
        tracks['sub_bass'].append(Message('program_change', channel=4, program=38, time=0)) # 38 = Synth Bass 1
        tracks['sub_bass'].append(Message('control_change', channel=4, control=7, value=95, time=0)) 
        tracks['sub_bass'].append(Message('control_change', channel=4, control=91, value=0, time=0))
        tracks['sub_bass'].append(Message('control_change', channel=4, control=93, value=0, time=0))
        tracks['sub_bass'].append(Message('control_change', channel=4, control=72, value=10, time=0))

        # --- Proses Pembuatan Lagu per Bagian ---
        song_structure = build_song_structure(params)
        current_beat = 0.0
        all_events = {ch: [] for ch in [0, 1, 2, 3, 4, 9]}
        tempo_events = []

        gen_funcs = {
            0: generate_melody_section, 1: generate_rhythm_primary_section,
            2: generate_rhythm_secondary_section, 3: generate_bass_line_section,
            4: generate_sub_bass_section 
        }

        for i, (stype, sbeats, cprog, *_) in enumerate(song_structure):
            logger.info(f"Generating '{stype}' ({sbeats} beats)")
            is_outro = (stype == 'outro')
            for ch, func in gen_funcs.items():
                for pitch, rel_beat, dur, vel in func(params, stype, sbeats, cprog):
                    if not (is_outro and rel_beat >= sbeats - 2):
                        all_events[ch].append(('note', current_beat + rel_beat, ch, pitch, vel, dur))
            
            fill_dur, has_fill = 2.0, (i < len(song_structure) - 1)
            drum_beats = sbeats - fill_dur if has_fill else sbeats
            for note, rel_beat, dur, vel in generate_drum_pattern_section(params, stype, drum_beats):
                all_events[9].append(('note', current_beat + rel_beat, 9, note, vel, dur))
            if has_fill:
                for note, rel_beat, dur, vel in generate_drum_fill(fill_dur):
                    all_events[9].append(('note', current_beat + drum_beats + rel_beat, 9, note, vel, dur))

            if is_outro:
                for step in range(4):
                    beat_pos = current_beat + (step * (sbeats / 4))
                    new_tempo = tempo * (1.0 - (0.4 * (step / 4)))
                    tempo_events.append(('tempo', beat_pos, bpm2tempo(new_tempo)))
                final_beat, final_chord = current_beat + sbeats - 2, cprog[-1]
                all_events[0].append(('note', final_beat, 0, final_chord[-1] + 12, 80, 4))
                for note in final_chord: all_events[1].append(('note', final_beat, 1, note, 70, 4))
                all_events[3].append(('note', final_beat, 3, final_chord[0] - 24, 90, 4))
                all_events[4].append(('note', final_beat, 4, max(24, min(36, final_chord[0] - 36)), 100, 4))
                all_events[9].append(('note', final_beat, 9, DRUM_NOTES['crash'], 120, 4))
            
            current_beat += sbeats
        
        # --- Proses dan Tulis Event ke File MIDI ---
        master_events = tempo_events
        for ch_events in all_events.values(): master_events.extend(ch_events)
        master_events.sort(key=lambda x: x[1])

        def beats_to_ticks(b): return int(round(b * ticks_per_beat))
        
        last_tick = {track_name: 0 for track_name in tracks.keys()}
        track_map = {0: 'melody', 1: 'rhythm_primary', 2: 'rhythm_secondary', 3: 'bass', 4: 'sub_bass', 9: 'drums'}
        note_offs = []

        for event in master_events:
            etype, abs_beat = event[0], event[1]
            abs_tick = beats_to_ticks(abs_beat)
            if etype == 'tempo':
                track, tempo_val = tracks['melody'], event[2]
                delta = abs_tick - last_tick['melody']
                track.append(MetaMessage('set_tempo', tempo=tempo_val, time=max(0, delta)))
                last_tick['melody'] = abs_tick
            elif etype == 'note':
                _, _, ch, pitch, vel, dur = event
                track_name = track_map[ch]
                track = tracks[track_name]
                delta_on = abs_tick - last_tick[track_name]
                track.append(Message('note_on', channel=ch, note=int(pitch), velocity=int(vel), time=max(0, delta_on)))
                last_tick[track_name] = abs_tick
                note_offs.append((abs_beat + dur, ch, pitch))
        
        note_offs.sort(key=lambda x: x[0])
        for off_beat, ch, pitch in note_offs:
            off_tick = beats_to_ticks(off_beat)
            track_name = track_map[ch]
            track = tracks[track_name]
            delta_off = off_tick - last_tick[track_name]
            track.append(Message('note_off', channel=ch, note=int(pitch), velocity=0, time=max(0, delta_off)))
            last_tick[track_name] = off_tick

        total_ticks = beats_to_ticks(current_beat + 4)
        for name, track in tracks.items():
            track.append(MetaMessage('end_of_track', time=max(0, total_ticks - last_tick[name])))

        mid.save(output_path)
        logger.info(f"MIDI generated in {time.time() - start_time:.1f}s: {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"Critical error in create_midi_file: {e}", exc_info=True)
        return False

# --- [Fungsi Konversi Audio dan Flask Endpoints] ---

def midi_to_audio(midi_path, output_wav_path):
    if not SOUNDFONT_PATH: return False
    try:
        cmd = ['fluidsynth', '-F', str(output_wav_path), '-g', '1.0', '-ni', str(SOUNDFONT_PATH), str(midi_path)]
        logger.info("Rendering MIDI with FluidSynth...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"WAV generated: {output_wav_path.name}")
            return True
        logger.error(f"FluidSynth failed: {result.stderr}")
        return False
    except Exception as e:
        logger.error(f"FluidSynth error: {e}")
        return False

def wav_to_mp3(wav_path, mp3_path):
    try:
        if not wav_path.exists(): return False
        audio = AudioSegment.from_wav(wav_path)

        # Terapkan kompresi dinamis
        compressed_audio = compress_dynamic_range(
            audio,
            threshold=-20.0,  
            ratio=4.0,        
            attack=5.0,       
            release=50.0      
        )

        # Normalisasi audio YANG SUDAH DIKOMPRES
        normalized = pydub_normalize(compressed_audio, headroom=1.0)
        
        normalized.export(mp3_path, format='mp3', bitrate='192k')
        logger.info(f"MP3 created (with compression): {mp3_path.name}")
        return True
    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

def generate_unique_id(lyrics):
    return f"{hashlib.md5(lyrics.encode()).hexdigest()[:8]}_{int(time.time())}"

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html> <html lang="id"> <head> <meta charset="UTF-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0"> <title>🎵 AI Instrumental Generator 🎵</title> <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet"> <style> #waveform { min-height: 80px; } </style> <script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"></script> </head> <body class="bg-gray-100 min-h-screen flex items-center justify-center p-4"> <div class="bg-white p-8 rounded-lg shadow-xl w-full max-w-2xl"> <h1 class="text-3xl font-bold text-center mb-6 text-gray-800">🎵 AI Instrumental Generator 🎵</h1> <form id="musicForm"> <div class="mb-4"> <label for="textInput" class="block text-gray-700 text-sm font-bold mb-2">Lirik / Deskripsi:</label> <textarea id="textInput" rows="6" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Masukkan lirik atau deskripsi singkat..."></textarea> </div> <div class="grid grid-cols-2 gap-4 mb-6"> <div> <label for="genreSelect" class="block text-gray-700 text-sm font-bold mb-2">Genre:</label> <select id="genreSelect" class="w-full p-3 border border-gray-300 rounded-lg"> <option value="auto">🤖 Otomatis</option> <option value="pop">🎤 Pop</option> <option value="rock">🎸 Rock</option> <option value="metal">🤘 Metal</option> <option value="ballad">💔 Ballad</option> <option value="blues">🎷 Blues</option> <option value="jazz">🎹 Jazz</option>
    <option value="hiphop">🎧 Hip-Hop</option>
    <option value="latin">💃 Latin</option> <option value="dangdut">🎶 Dangdut</option> </select> </div> <div> <label for="tempoInput" class="block text-gray-700 text-sm font-bold mb-2">Tempo (BPM):</label> <input type="number" id="tempoInput" class="w-full p-3 border border-gray-300 rounded-lg" placeholder="Auto (60-200)"> </div> </div> <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-bold hover:bg-blue-700 transition">🚀 Generate Instrumental</button> </form> <div id="status" class="text-center mt-4"></div> <div id="audioSection" class="hidden mt-6"> <h2 class="text-xl font-bold text-gray-800 mb-2">Hasil Instrumental</h2> <div id="waveform" class="mb-2"></div> <audio id="audioPlayer" class="w-full" controls></audio> <a id="downloadBtn" class="w-full block text-center bg-green-600 text-white mt-4 py-3 px-4 rounded-lg font-bold hover:bg-green-700 transition" href="#" download>💾 Download MP3</a> </div> </div> <script> let wavesurfer = null; document.getElementById('musicForm').addEventListener('submit', async (e) => { e.preventDefault(); const btn = document.getElementById('generateBtn'); const status = document.getElementById('status'); const audioSection = document.getElementById('audioSection'); const formData = new FormData(e.target); btn.disabled = true; btn.textContent = '🧠 Generating... (bisa 1-2 menit)'; status.textContent = 'Menganalisis lirik dan membuat struktur lagu...'; audioSection.classList.add('hidden'); try { const response = await fetch('/generate-instrumental', { method: 'POST', body: formData }); const data = await response.json(); if (response.ok && data.success) { status.innerHTML = `<p class="text-green-600">🎉 Berhasil! Genre: <strong>${data.genre}</strong>, Tempo: <strong>${data.tempo} BPM</strong></p>`; audioSection.classList.remove('hidden'); const audioPlayer = document.getElementById('audioPlayer'); const downloadBtn = document.getElementById('downloadBtn'); const audioUrl = `/static/audio_output/${data.filename}`; audioPlayer.src = audioUrl; downloadBtn.href = audioUrl; downloadBtn.download = `instrumental_${data.id}.mp3`; if (wavesurfer) wavesurfer.destroy(); wavesurfer = Wavesurfer.create({ container: '#waveform', waveColor: '#4f46e5', progressColor: '#10b981', height: 80, barWidth: 2, normalize: true, }); wavesurfer.load(audioUrl); } else { throw new Error(data.error || 'Terjadi kesalahan.'); } } catch (error) { status.innerHTML = `<p class="text-red-600">❌ Error: ${error.message}</p>`; } finally { btn.disabled = false; btn.textContent = '🚀 Generate Instrumental'; } }); </script> </body> </html>
    """)

@app.route('/generate-instrumental', methods=['POST'])
def generate_instrumental_endpoint():
    start_time = time.time()
    try:
        lyrics = request.form.get('lyrics', '').strip()
        if len(lyrics) < 10: 
            return jsonify({'error': 'Lirik minimal 10 karakter.'}), 400
        
        genre = request.form.get('genre', 'auto').lower()
        if genre == 'auto': genre = detect_genre_from_lyrics(lyrics)
        
        params = get_music_params_from_lyrics(genre, lyrics, request.form.get('tempo', 'auto'))
        unique_id = generate_unique_id(lyrics)
        paths = {p: AUDIO_OUTPUT_DIR / f"{unique_id}.{p}" for p in ['mid', 'wav', 'mp3']}

        if not create_midi_file(params, paths['mid']): raise Exception("Gagal membuat file MIDI.")
        if not midi_to_audio(paths['mid'], paths['wav']): raise Exception("Gagal render audio (pastikan FluidSynth terinstall).")
        if not wav_to_mp3(paths['wav'], paths['mp3']): raise Exception("Gagal konversi ke MP3 (pastikan FFmpeg terinstall).")

        if paths['mid'].exists(): paths['mid'].unlink()
        if paths['wav'].exists(): paths['wav'].unlink()

        logger.info(f"Generation complete in {time.time() - start_time:.1f}s!")
        return jsonify({'success': True, 'filename': paths['mp3'].name, 'genre': genre.capitalize(),
                        'tempo': params['tempo'], 'id': unique_id})
    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)

def cleanup_old_files(directory, max_age_hours=24):
    try:
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        for f in Path(directory).glob("*.{mp3,wav,mid}"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff: f.unlink()
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

if __name__ == '__main__':
    cleanup_old_files(AUDIO_OUTPUT_DIR)
    logger.info(f"🚀 Server running, SoundFont: {SOUNDFONT_PATH.name if SOUNDFONT_PATH else 'Not Found'}")
    app.run(host='0.0.0.0', port=5000, debug=False)
