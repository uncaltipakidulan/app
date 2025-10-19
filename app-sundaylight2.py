import os 
import sys
import time
import random
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import subprocess

# ==================== IMPORTS DENGAN ERROR HANDLING ====================
try:
    from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo
    MIDO_AVAILABLE = True
except ImportError as e:
    MIDO_AVAILABLE = False
    print(f"⚠️  Mido not available: {e}")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError as e:
    GTTS_AVAILABLE = False
    print(f"⚠️  gTTS not available: {e}")

try:
    from pydub import AudioSegment
    from pydub.effects import normalize, compress_dynamic_range
    PYDUB_AVAILABLE = True
except ImportError as e:
    PYDUB_AVAILABLE = False
    print(f"⚠️  Pydub not available: {e}")

# ==================== KONFIGURASI ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Path configuration
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
AUDIO_OUTPUT_DIR = STATIC_DIR / 'audio_output'
VOCAL_OUTPUT_DIR = STATIC_DIR / 'vocal_output'
MERGED_OUTPUT_DIR = STATIC_DIR / 'merged_output'

# Create directories
for directory in [AUDIO_OUTPUT_DIR, VOCAL_OUTPUT_DIR, MERGED_OUTPUT_DIR]:
    os.makedirs(directory, exist_ok=True)

# SoundFont detection
SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',
    BASE_DIR / 'FluidR3_GM.sf2', 
    BASE_DIR / 'TimGM6mb.sf2',
]

for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        logger.info(f"✅ Using SoundFont: {candidate.name}")
        break

# ==================== VOCAL AI YANG LENGKAP ====================

class AdvancedVocalSynthesizer:
    def __init__(self):
        self.available = GTTS_AVAILABLE
        self.setup()
        
    def setup(self):
        if self.available:
            logger.info("✅ gTTS available for vocal synthesis")
        else:
            logger.warning("❌ gTTS not available")
    
    def synthesize_vocals(self, lyrics, output_path, key='C', tempo=120):
        try:
            if not self.available:
                return False, "Vocal AI not available"
            
            processed_lyrics = self._preprocess_lyrics(lyrics, tempo)
            if not processed_lyrics:
                return False, "No valid lyrics"
            
            success, message = self._synthesize_gtts(processed_lyrics, output_path)
            
            if success:
                self._process_vocal_audio(output_path, tempo)
                return True, "Vocal synthesis successful"
            else:
                return False, message
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _preprocess_lyrics(self, lyrics, tempo):
        try:
            if not lyrics or len(lyrics.strip()) < 3:
                return None
            
            cleaned = ' '.join(lyrics.split())
            cleaned = cleaned.replace('\n', '. ')
            
            # Adjust based on tempo
            if tempo > 140:
                # Shorter phrases for fast tempo
                sentences = cleaned.split('.')
                cleaned = '. '.join([s.strip() for s in sentences if s.strip()][:6])
            else:
                sentences = cleaned.split('.') 
                cleaned = '. '.join([s.strip() for s in sentences if s.strip()][:8])
            
            return cleaned[:400]
            
        except Exception as e:
            logger.error(f"Lyrics preprocessing error: {e}")
            return lyrics[:300]
    
    def _synthesize_gtts(self, text, output_path):
        try:
            tts = gTTS(text=text, lang='id', slow=False, lang_check=False)
            tts.save(str(output_path))
            
            if output_path.exists() and output_path.stat().st_size > 1000:
                logger.info(f"✅ Vocal generated: {output_path.name}")
                return True, "Vocal synthesis successful"
            else:
                return False, "Generated file is empty"
                
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            return False, f"gTTS error: {str(e)}"
    
    def _process_vocal_audio(self, vocal_path, tempo):
        try:
            if not PYDUB_AVAILABLE:
                return
                
            audio = AudioSegment.from_mp3(vocal_path)
            
            # Simple tempo-based processing
            if tempo > 140:
                audio = audio.speedup(playback_speed=1.03)
            elif tempo < 80:
                audio = audio.speedup(playback_speed=0.97)
            
            # Basic compression
            audio = compress_dynamic_range(audio, threshold=-20.0, ratio=2.0)
            audio = normalize(audio, headroom=3.0)
            
            audio.export(vocal_path, format="mp3", bitrate="192k")
            logger.info("✅ Vocal audio processed")
            
        except Exception as e:
            logger.error(f"Vocal audio processing error: {e}")

vocal_synth = AdvancedVocalSynthesizer()

# ==================== INSTRUMENTS & CHORDS LENGKAP ====================

INSTRUMENTS = {
    # Piano
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3, 'Electric Piano 1': 4, 'Electric Piano 2': 5,
    'Harpsichord': 6, 'Clavinet': 7,
    
    # Guitar
    'Nylon String Guitar': 24, 'Steel String Guitar': 25, 'Jazz Electric Guitar': 26,
    'Clean Electric Guitar': 27, 'Muted Electric Guitar': 28, 'Overdriven Guitar': 29,
    'Distortion Guitar': 30, 'Guitar Harmonics': 31,
    
    # Bass
    'Acoustic Bass': 32, 'Electric Bass finger': 33, 'Electric Bass pick': 34,
    'Fretless Bass': 35, 'Slap Bass 1': 36, 'Slap Bass 2': 37, 'Synth Bass 1': 38,
    'Synth Bass 2': 39,
    
    # Strings & Orchestra
    'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43,
    'String Ensemble 1': 48, 'String Ensemble 2': 49, 'Synth Strings 1': 50,
    'Synth Strings 2': 51,
    
    # Brass & Woodwind
    'Trumpet': 56, 'Trombone': 57, 'Tuba': 58, 'French Horn': 60,
    'Brass Section': 61, 'Synth Brass 1': 62, 'Synth Brass 2': 63,
    'Soprano Sax': 64, 'Alto Sax': 65, 'Tenor Sax': 66, 'Baritone Sax': 67,
    'Oboe': 68, 'Bassoon': 70, 'Clarinet': 71, 'Piccolo': 72, 'Flute': 73,
    
    # Synth
    'Lead 1 (square)': 80, 'Lead 2 (sawtooth)': 81, 'Lead 3 (calliope)': 82,
    'Pad 1 (new age)': 88, 'Pad 2 (warm)': 89, 'Pad 3 (polysynth)': 90,
    
    # Ethnic
    'Sitar': 104, 'Banjo': 105, 'Shamisen': 106, 'Koto': 107,
    'Kalimba': 108, 'Bagpipe': 109, 'Fiddle': 110,
}

CHORDS = {
    # Major & Minor
    'C': [60, 64, 67], 'Cm': [60, 63, 67],
    'C#': [61, 65, 68], 'C#m': [61, 64, 68],
    'D': [62, 66, 69], 'Dm': [62, 65, 69],
    'D#': [63, 67, 70], 'D#m': [63, 66, 70],
    'E': [64, 68, 71], 'Em': [64, 67, 71],
    'F': [65, 69, 72], 'Fm': [65, 68, 72],
    'F#': [66, 70, 73], 'F#m': [66, 69, 73],
    'G': [67, 71, 74], 'Gm': [67, 70, 74],
    'G#': [68, 72, 75], 'G#m': [68, 71, 75],
    'A': [69, 73, 76], 'Am': [69, 72, 76],
    'A#': [70, 74, 77], 'A#m': [70, 73, 77],
    'B': [71, 75, 78], 'Bm': [71, 74, 78],
    
    # Seventh Chords
    'C7': [60, 64, 67, 70], 'Cm7': [60, 63, 67, 70],
    'D7': [62, 66, 69, 72], 'Dm7': [62, 65, 69, 72],
    'E7': [64, 68, 71, 74], 'Em7': [64, 67, 71, 74],
    'F7': [65, 69, 72, 75], 'Fm7': [65, 68, 72, 75],
    'G7': [67, 71, 74, 77], 'Gm7': [67, 70, 74, 77],
    'A7': [69, 73, 76, 79], 'Am7': [69, 72, 76, 79],
    'B7': [71, 75, 78, 81], 'Bm7': [71, 74, 78, 81],
    
    # Major 7th
    'Cmaj7': [60, 64, 67, 71], 'Dmaj7': [62, 66, 69, 73],
    'Emaj7': [64, 68, 71, 75], 'Fmaj7': [65, 69, 72, 76],
    'Gmaj7': [67, 71, 74, 78], 'Amaj7': [69, 73, 76, 80],
    'Bmaj7': [71, 75, 78, 82],
}

SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'harmonic minor': [0, 2, 3, 5, 7, 8, 11],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
}

# ==================== GENRE PARAMETERS LENGKAP ====================

GENRE_PARAMS = {
    'pop': {
        'tempo': 120, 'key': 'C', 'scale': 'major', 
        'instruments': {
            'melody': 'Electric Piano 1',
            'rhythm_primary': 'Clean Electric Guitar', 
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Electric Bass finger',
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], 
            ['C', 'F', 'Am', 'G'], ['Dm', 'G', 'C', 'F']
        ],
        'mood': 'happy'
    },
    'poprock': {
        'tempo': 128, 'key': 'G', 'scale': 'major',
        'instruments': {
            'melody': 'Overdriven Guitar',
            'rhythm_primary': 'Clean Electric Guitar',
            'rhythm_secondary': 'Electric Piano 1',
            'bass': 'Electric Bass pick',
        },
        'chord_progressions': [
            ['G', 'D', 'Em', 'C'], ['C', 'G', 'Am', 'F'],
            ['Em', 'C', 'G', 'D'], ['G', 'C', 'D', 'Em']
        ],
        'mood': 'energetic'
    },
    'rock': {
        'tempo': 130, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Electric Bass pick',
        },
        'chord_progressions': [
            ['E', 'D', 'A', 'E'], ['A', 'G', 'D', 'A'],
            ['Em', 'G', 'D', 'A'], ['E5', 'A5', 'B5', 'E5']
        ],
        'mood': 'energetic'
    },
    'slow rock': {
        'tempo': 70, 'key': 'Am', 'scale': 'minor',
        'instruments': {
            'melody': 'Clean Electric Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Fretless Bass',
        },
        'chord_progressions': [
            ['Am', 'G', 'C', 'F'], ['C', 'G', 'Am', 'F'],
            ['Am', 'Dm', 'G', 'C'], ['F', 'C', 'G', 'Am']
        ],
        'mood': 'emotional'
    },
    'ballad': {
        'tempo': 65, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Warm Pad',
            'bass': 'Acoustic Bass',
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'],
            ['F', 'C', 'Dm', 'G'], ['Em', 'Am', 'Dm', 'G']
        ],
        'mood': 'emotional'
    },
    'jazz': {
        'tempo': 120, 'key': 'C', 'scale': 'dorian',
        'instruments': {
            'melody': 'Tenor Sax',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Vibraphone',
            'bass': 'Acoustic Bass',
        },
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'], ['Cm7', 'F7', 'Bbmaj7'],
            ['Am7', 'D7', 'Gmaj7'], ['Em7', 'A7', 'Dmaj7']
        ],
        'mood': 'sophisticated'
    },
    'metal': {
        'tempo': 160, 'key': 'Em', 'scale': 'minor',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Synth Brass 1',
            'bass': 'Slap Bass 1',
        },
        'chord_progressions': [
            ['Em', 'C', 'G', 'D'], ['Am', 'Em', 'F', 'G'],
            ['E5', 'G5', 'D5', 'A5'], ['B5', 'A5', 'G5', 'F#5']
        ],
        'mood': 'intense'
    },
    'dangdut': {
        'tempo': 130, 'key': 'Am', 'scale': 'minor',
        'instruments': {
            'melody': 'Suling',
            'rhythm_primary': 'Kendang',
            'rhythm_secondary': 'Electric Organ',
            'bass': 'Electric Bass finger',
        },
        'chord_progressions': [
            ['Am', 'E7', 'Am', 'E7'], ['Am', 'Dm', 'E7', 'Am'],
            ['Dm', 'Am', 'E7', 'Am'], ['Am', 'G', 'F', 'E7']
        ],
        'mood': 'festive'
    },
    'latin': {
        'tempo': 110, 'key': 'Am', 'scale': 'dorian',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'Congas',
            'bass': 'Acoustic Bass',
        },
        'chord_progressions': [
            ['Am', 'D7', 'Gmaj7', 'Cmaj7'], 
            ['G', 'Bm', 'Em', 'A7'],
            ['Dm', 'G7', 'Cmaj7', 'Fmaj7']
        ],
        'mood': 'rhythmic'
    }
}

# ==================== SONG STRUCTURE SYSTEM ====================

def create_song_structure(genre, total_beats=180):  # ~3 menit untuk tempo 120
    """Create complete song structure dengan minimal 3 menit"""
    
    structures = {
        'pop': ['intro', 'verse1', 'pre_chorus', 'chorus', 'verse2', 'pre_chorus', 'chorus', 'bridge', 'chorus', 'outro'],
        'rock': ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'bridge', 'guitar_solo', 'chorus', 'outro'],
        'ballad': ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'bridge', 'final_chorus', 'outro'],
        'jazz': ['intro', 'head', 'solo1', 'solo2', 'head', 'outro'],
        'metal': ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'breakdown', 'solo', 'chorus', 'outro'],
        'dangdut': ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'interlude', 'chorus', 'outro'],
        'latin': ['intro', 'verse1', 'montuno', 'verse2', 'montuno', 'solo', 'montuno', 'outro']
    }
    
    selected_structure = structures.get(genre, structures['pop'])
    
    # Section durations in beats
    section_durations = {
        'intro': 8, 'verse1': 16, 'verse2': 16, 'pre_chorus': 8,
        'chorus': 16, 'bridge': 16, 'outro': 12, 'guitar_solo': 16,
        'final_chorus': 16, 'head': 16, 'solo1': 16, 'solo2': 16,
        'breakdown': 12, 'solo': 16, 'interlude': 8, 'montuno': 16
    }
    
    song_structure = []
    current_beat = 0
    
    for section_name in selected_structure:
        duration = section_durations.get(section_name, 8)
        
        section_info = {
            'name': section_name,
            'start_beat': current_beat,
            'duration_beats': duration,
            'type': section_name.replace('1', '').replace('2', '').replace('final_', ''),
            'chord_progression': None,
            'instruments': {},
            'has_transition': False
        }
        
        song_structure.append(section_info)
        current_beat += duration
    
    # Add transitions
    for i in range(len(song_structure) - 1):
        song_structure[i]['has_transition'] = True
        song_structure[i]['transition_to'] = song_structure[i + 1]['name']
    
    logger.info(f"Created {genre} structure: {[s['name'] for s in song_structure]} ({current_beat} beats)")
    return song_structure

def assign_chord_progressions(song_structure, genre_params):
    """Assign chord progressions to each section"""
    progressions = genre_params['chord_progressions']
    
    for section in song_structure:
        section_type = section['type']
        
        if section_type == 'intro':
            section['chord_progression'] = progressions[0][:2] if len(progressions[0]) > 2 else progressions[0]
        elif section_type == 'verse':
            section['chord_progression'] = random.choice(progressions)
        elif section_type == 'chorus':
            section['chord_progression'] = progressions[0]
        elif section_type == 'bridge':
            section['chord_progression'] = progressions[-1] if len(progressions) > 1 else progressions[0]
        elif section_type == 'outro':
            section['chord_progression'] = [progressions[0][-1]] if progressions[0] else ['C']
        else:
            section['chord_progression'] = random.choice(progressions)
    
    return song_structure

# ==================== MUSIC GENERATION FUNCTIONS ====================

def generate_unique_id(text):
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

def detect_genre_from_lyrics(lyrics):
    if not lyrics:
        return 'pop'
    
    lyrics_lower = lyrics.lower()
    
    if any(word in lyrics_lower for word in ['metal', 'heavy', 'dark', 'scream']):
        return 'metal'
    elif any(word in lyrics_lower for word in ['jazz', 'sax', 'swing', 'blue']):
        return 'jazz'
    elif any(word in lyrics_lower for word in ['sad', 'heartbreak', 'tears', 'alone']):
        return 'ballad'
    elif any(word in lyrics_lower for word in ['rock', 'guitar', 'energy']):
        return 'rock'
    elif any(word in lyrics_lower for word in ['dangdut', 'koplo', 'tradisional']):
        return 'dangdut'
    elif any(word in lyrics_lower for word in ['latin', 'salsa', 'rumba']):
        return 'latin'
    else:
        return 'pop'

def get_music_params_from_lyrics(genre, lyrics, tempo_input='auto'):
    params = GENRE_PARAMS.get(genre, GENRE_PARAMS['pop']).copy()
    params['genre'] = genre
    
    if tempo_input != 'auto':
        try:
            tempo_val = int(tempo_input)
            if 60 <= tempo_val <= 200:
                params['tempo'] = tempo_val
        except ValueError:
            pass
    
    # Create song structure
    song_structure = create_song_structure(genre)
    song_structure = assign_chord_progressions(song_structure, params)
    
    params['song_structure'] = song_structure
    total_beats = sum(s['duration_beats'] for s in song_structure)
    params['total_duration'] = total_beats * 60 / params['tempo']
    
    logger.info(f"Music params: {genre}, tempo={params['tempo']}, duration={params['total_duration']:.1f}s")
    return params

def create_structured_midi(params, output_path):
    """Create structured MIDI file - FIXED VERSION"""
    try:
        if not MIDO_AVAILABLE:
            return False
            
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Set tempo
        tempo = bpm2tempo(params['tempo'])
        track.append(MetaMessage('set_tempo', tempo=tempo))
        
        # Set instrument
        melody_instrument = params['instruments']['melody']
        melody_program = INSTRUMENTS.get(melody_instrument, 0)
        track.append(Message('program_change', program=melody_program, time=0))
        
        song_structure = params['song_structure']
        ticks_per_beat = 480
        current_tick = 0
        
        for section in song_structure:
            section_name = section['name']
            duration_beats = section['duration_beats']
            chords = section['chord_progression']
            
            logger.info(f"Generating section: {section_name} ({duration_beats} beats)")
            
            if not chords:
                chords = [['C']]
            
            # Convert chord names to MIDI notes
            midi_chords = []
            for chord_name in chords:
                if chord_name in CHORDS:
                    midi_chords.append(CHORDS[chord_name])
                else:
                    midi_chords.append(CHORDS['C'])
            
            # Generate notes for this section
            beats_per_chord = duration_beats / len(midi_chords)
            
            for chord_idx, chord_notes in enumerate(midi_chords):
                chord_start_beat = chord_idx * beats_per_chord
                chord_duration_beats = beats_per_chord
                
                # Convert to ticks
                start_ticks = int(chord_start_beat * ticks_per_beat)
                duration_ticks = int(chord_duration_beats * ticks_per_beat * 0.7)  # Note length
                
                # Add some notes from the chord
                for i, note in enumerate(chord_notes[:3]):  # Max 3 notes per chord
                    velocity = 70 + (i * 10)  # Different velocity for each note
                    
                    # Note on
                    track.append(Message('note_on', note=note, velocity=velocity, time=start_ticks))
                    # Note off
                    track.append(Message('note_off', note=note, velocity=0, time=duration_ticks))
                
                # Add transition effect at end of section
                if section.get('has_transition', False) and chord_idx == len(midi_chords) - 1:
                    # Add a cymbal crash
                    track.append(Message('note_on', channel=9, note=49, velocity=100, time=0))
                    track.append(Message('note_off', channel=9, note=49, velocity=0, time=120))
            
            current_tick += int(duration_beats * ticks_per_beat)
        
        # Add fade out for outro
        if song_structure and song_structure[-1]['type'] == 'outro':
            # Slow down tempo for fade out
            fade_tempo = bpm2tempo(params['tempo'] * 0.6)
            track.append(MetaMessage('set_tempo', tempo=fade_tempo, time=current_tick - 480))
        
        mid.save(output_path)
        logger.info(f"Structured MIDI created: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Structured MIDI creation error: {e}")
        return False

def midi_to_audio(midi_path, output_wav_path):
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False
    
    try:
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-ni', str(SOUNDFONT_PATH), str(midi_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"WAV generated: {output_wav_path}")
            return True
        else:
            logger.error(f"FluidSynth failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout")
        return False
    except Exception as e:
        logger.error(f"MIDI to audio error: {e}")
        return False

def wav_to_mp3(wav_path, mp3_path):
    try:
        if not PYDUB_AVAILABLE:
            # Fallback to ffmpeg
            cmd = ['ffmpeg', '-i', str(wav_path), '-b:a', '192k', str(mp3_path), '-y']
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            return result.returncode == 0
        
        audio = AudioSegment.from_wav(wav_path)
        audio = normalize(audio, headroom=2.0)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        
        logger.info(f"MP3 created: {mp3_path}")
        return True
    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

def merge_audio(instrumental_path, vocal_path, output_path):
    try:
        if not PYDUB_AVAILABLE:
            return False, "Pydub not available"
            
        instrumental = AudioSegment.from_mp3(instrumental_path)
        vocals = AudioSegment.from_mp3(vocal_path)
        
        # Adjust vocal volume
        vocals = vocals - 3
        
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        mixed = instrumental.overlay(vocals)
        mixed.export(output_path, format="mp3", bitrate="192k")
        
        logger.info(f"Merged audio created: {output_path}")
        return True, "Merge successful"
        
    except Exception as e:
        logger.error(f"Audio merging error: {e}")
        return False, f"Merge error: {str(e)}"

def cleanup_old_files(max_files=5):
    try:
        for directory in [AUDIO_OUTPUT_DIR, VOCAL_OUTPUT_DIR, MERGED_OUTPUT_DIR]:
            files = list(directory.glob("*.mp3")) + list(directory.glob("*.wav")) + list(directory.glob("*.mid"))
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            for old_file in files[max_files:]:
                try:
                    old_file.unlink()
                    logger.info(f"Cleaned up: {old_file.name}")
                except:
                    pass
                    
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# ==================== FLASK ROUTES LENGKAP ====================

@app.route('/')
def index():
    html_template = '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Music Generator - Full Features</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 min-h-screen p-4">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white rounded-lg shadow-lg p-6">
                <h1 class="text-3xl font-bold text-center mb-2">🎵 AI Music Generator - Full Features</h1>
                <p class="text-center text-gray-600 mb-6">8 Genre • Song Structure • 3+ Minutes • Vocal AI</p>
                
                <form id="musicForm" class="space-y-4">
                    <div>
                        <label class="block font-semibold mb-2">Lirik Lagu:</label>
                        <textarea id="lyrics" rows="4" class="w-full p-3 border rounded" placeholder="Masukkan lirik lagu..."></textarea>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block font-semibold mb-2">Genre:</label>
                            <select id="genre" class="w-full p-2 border rounded">
                                <option value="auto">Auto Detect</option>
                                <option value="pop">Pop</option>
                                <option value="poprock">Pop Rock</option>
                                <option value="rock">Rock</option>
                                <option value="slow rock">Slow Rock</option>
                                <option value="ballad">Ballad</option>
                                <option value="jazz">Jazz</option>
                                <option value="metal">Metal</option>
                                <option value="dangdut">Dangdut</option>
                                <option value="latin">Latin</option>
                            </select>
                        </div>
                        <div>
                            <label class="block font-semibold mb-2">Tempo (BPM):</label>
                            <input type="number" id="tempo" class="w-full p-2 border rounded" placeholder="Auto" min="60" max="200">
                        </div>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input type="checkbox" id="addVocals" checked>
                        <label class="font-semibold">Tambahkan AI Vocal (Structure Matched)</label>
                    </div>
                    
                    <div class="bg-blue-50 p-3 rounded">
                        <h4 class="font-semibold text-blue-800">🎼 Song Structure:</h4>
                        <p class="text-sm text-blue-600">Setiap genre memiliki struktur unik: Intro → Verse → Chorus → Bridge → Outro</p>
                        <p class="text-sm text-blue-600">Durasi: Minimal 3 menit dengan transitions</p>
                    </div>
                    
                    <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 rounded font-bold hover:bg-blue-700">
                        🚀 Generate Full Song (3+ Minutes)
                    </button>
                </form>
                
                <div id="status" class="mt-4 hidden">
                    <div id="statusMessage" class="p-3 rounded"></div>
                </div>
                
                <div id="results" class="mt-6 space-y-4 hidden">
                    <div class="border rounded p-4">
                        <h3 class="font-bold mb-2">🎵 Instrumental (Structured)</h3>
                        <div id="structureInfo" class="text-sm text-gray-600 mb-2"></div>
                        <audio id="instrumentalAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('instrumental')" class="bg-blue-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                    
                    <div id="vocalResult" class="border rounded p-4 hidden">
                        <h3 class="font-bold mb-2">🎤 AI Vocals</h3>
                        <audio id="vocalAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('vocal')" class="bg-green-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                    
                    <div id="mergedResult" class="border rounded p-4 hidden">
                        <h3 class="font-bold mb-2">🎶 Full Song</h3>
                        <audio id="mergedAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('merged')" class="bg-purple-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                </div>
            </div>
            
            <div class="mt-4 text-center text-sm text-gray-600">
                <div>Vocal AI: <span id="vocalStatus" class="font-semibold">Checking...</span></div>
                <div>MIDI: <span id="midiStatus" class="font-semibold">Checking...</span></div>
                <div>Audio: <span id="audioStatus" class="font-semibold">Checking...</span></div>
            </div>
        </div>

        <script>
            fetch('/system-status').then(r => r.json()).then(data => {
                document.getElementById('vocalStatus').textContent = data.vocal_ai ? '✅' : '❌';
                document.getElementById('midiStatus').textContent = data.midi ? '✅' : '❌';
                document.getElementById('audioStatus').textContent = data.audio ? '✅' : '❌';
            });

            document.getElementById('musicForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const lyrics = document.getElementById('lyrics').value.trim();
                if (!lyrics) {
                    alert('Masukkan lirik terlebih dahulu!');
                    return;
                }

                const btn = document.getElementById('generateBtn');
                const status = document.getElementById('status');
                const statusMessage = document.getElementById('statusMessage');
                const results = document.getElementById('results');
                const structureInfo = document.getElementById('structureInfo');

                btn.disabled = true;
                btn.textContent = 'Generating Full Song...';
                status.className = 'bg-blue-100 text-blue-800 p-3 rounded';
                statusMessage.textContent = '🚀 Generating 3+ minute structured song... (3-4 minutes)';
                status.classList.remove('hidden');
                results.classList.add('hidden');

                try {
                    const formData = new FormData();
                    formData.append('lyrics', lyrics);
                    formData.append('genre', document.getElementById('genre').value);
                    formData.append('tempo', document.getElementById('tempo').value || 'auto');
                    formData.append('add_vocals', document.getElementById('addVocals').checked);

                    const response = await fetch('/generate-full-song', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (data.success) {
                        status.className = 'bg-green-100 text-green-800 p-3 rounded';
                        statusMessage.textContent = '✅ Full song generation successful!';
                        
                        if (data.instrumental && data.instrumental.structure) {
                            structureInfo.innerHTML = `<strong>Structure:</strong> ${data.instrumental.structure.join(' → ')}<br>
                                                      <strong>Duration:</strong> ${data.instrumental.duration} minutes<br>
                                                      <strong>Genre:</strong> ${data.instrumental.genre}`;
                        }
                        
                        document.getElementById('instrumentalAudio').src = '/static/audio_output/' + data.instrumental.filename;
                        
                        if (data.vocals) {
                            document.getElementById('vocalResult').classList.remove('hidden');
                            document.getElementById('vocalAudio').src = '/static/vocal_output/' + data.vocals.filename;
                        }
                        
                        if (data.merged) {
                            document.getElementById('mergedResult').classList.remove('hidden');
                            document.getElementById('mergedAudio').src = '/static/merged_output/' + data.merged.filename;
                        }
                        
                        results.classList.remove('hidden');
                    } else {
                        status.className = 'bg-red-100 text-red-800 p-3 rounded';
                        statusMessage.textContent = '❌ ' + (data.error || 'Generation failed');
                    }

                } catch (error) {
                    status.className = 'bg-red-100 text-red-800 p-3 rounded';
                    statusMessage.textContent = '❌ Network error';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '🚀 Generate Full Song (3+ Minutes)';
                }
            });

            function downloadAudio(type) {
                let audioElement, filename;
                switch(type) {
                    case 'instrumental':
                        audioElement = document.getElementById('instrumentalAudio');
                        filename = 'instrumental.mp3';
                        break;
                    case 'vocal':
                        audioElement = document.getElementById('vocalAudio');
                        filename = 'vocals.mp3';
                        break;
                    case 'merged':
                        audioElement = document.getElementById('mergedAudio');
                        filename = 'full_song.mp3';
                        break;
                }
                
                const link = document.createElement('a');
                link.href = audioElement.src;
                link.download = filename;
                link.click();
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_template)

@app.route('/system-status')
def system_status():
    return jsonify({
        'vocal_ai': vocal_synth.available,
        'midi': MIDO_AVAILABLE,
        'audio': PYDUB_AVAILABLE,
        'soundfont': SOUNDFONT_PATH and SOUNDFONT_PATH.exists()
    })

@app.route('/generate-full-song', methods=['POST'])
def generate_full_song():
    try:
        data = request.form.to_dict()
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto')
        tempo_input = data.get('tempo', 'auto')
        add_vocals = data.get('add_vocals', 'false').lower() == 'true'
        
        if not lyrics:
            return jsonify({'error': 'Lirik diperlukan'}), 400
        
        unique_id = generate_unique_id(lyrics)
        
        result = {
            'success': True,
            'instrumental': None,
            'vocals': None, 
            'merged': None
        }
        
        # Step 1: Generate instrumental
        logger.info("Step 1: Generating structured instrumental...")
        
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        if not create_structured_midi(params, midi_path):
            return jsonify({'error': 'MIDI creation failed'}), 500
        
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav"
        if not midi_to_audio(midi_path, wav_path):
            midi_path.unlink(missing_ok=True)
            return jsonify({'error': 'Audio conversion failed'}), 500
        
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        if not wav_to_mp3(wav_path, mp3_path):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return jsonify({'error': 'MP3 conversion failed'}), 500
        
        # Cleanup temporary files
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        result['instrumental'] = {
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo'],
            'duration': f"{params['total_duration']/60:.1f}",
            'structure': [s['name'] for s in params['song_structure']]
        }
        
        # Step 2: Generate vocals
        if add_vocals and vocal_synth.available:
            logger.info("Step 2: Generating vocals...")
            
            vocal_path = VOCAL_OUTPUT_DIR / f"{unique_id}.mp3"
            success, message = vocal_synth.synthesize_vocals(lyrics, vocal_path, params['key'], params['tempo'])
            
            if success:
                result['vocals'] = {
                    'filename': f'{unique_id}.mp3',
                    'message': message
                }
                
                # Step 3: Merge audio
                logger.info("Step 3: Merging audio...")
                
                merged_id = generate_unique_id(lyrics + "_merged")
                merged_path = MERGED_OUTPUT_DIR / f"{merged_id}.mp3"
                
                success, message = merge_audio(mp3_path, vocal_path, merged_path)
                if success:
                    result['merged'] = {
                        'filename': f'{merged_id}.mp3',
                        'message': message
                    }
        
        # Cleanup
        cleanup_old_files(5)
        
        logger.info("✅ Full song generation completed")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Full song generation error: {e}")
        cleanup_old_files(3)
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

# File serving routes
@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)

@app.route('/static/vocal_output/<filename>')
def serve_vocal(filename):
    return send_from_directory(VOCAL_OUTPUT_DIR, filename)

@app.route('/static/merged_output/<filename>')
def serve_merged(filename):
    return send_from_directory(MERGED_OUTPUT_DIR, filename)

def main():
    logger.info("🎵 Starting Full Feature Music Generator")
    logger.info(f"✅ MIDI: {'Available' if MIDO_AVAILABLE else 'Not Available'}")
    logger.info(f"✅ Vocal AI: {'Available' if vocal_synth.available else 'Not Available'}")
    logger.info(f"✅ Audio Processing: {'Available' if PYDUB_AVAILABLE else 'Not Available'}")
    logger.info(f"✅ SoundFont: {'Available' if SOUNDFONT_PATH else 'Not Found'}")
    logger.info(f"✅ Genres: {len(GENRE_PARAMS)} genres available")
    
    cleanup_old_files(3)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

if __name__ == '__main__':
    main()
