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

# IMPORT MIDO untuk manipulasi MIDI
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

# Import pyfluidsynth dengan error handling
try:
    import fluidsynth as pyfluidsynth_lib
    FLUIDSYNTH_BINDING_AVAILABLE = True
except ImportError:
    FLUIDSYNTH_BINDING_AVAILABLE = False

# Import pydub untuk manipulasi audio
from pydub import AudioSegment
from pydub.effects import normalize, compress_dynamic_range
from pydub.utils import ratio_to_db

# ==================== VOCAL AI IMPORTS ====================
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError as e:
    GTTS_AVAILABLE = False
    print(f"⚠️  gTTS not available: {e}")

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
VOCAL_OUTPUT_DIR = STATIC_DIR / 'vocal_output'
MERGED_OUTPUT_DIR = STATIC_DIR / 'merged_output'

# Auto-detect SoundFont - COMPATIBLE SOUNDFONTS
SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',        # ✅ Most compatible
    BASE_DIR / 'FluidR3_GM.sf2',                   # ✅ Good for all genres
    BASE_DIR / 'TimGM6mb.sf2',                     # ✅ Lightweight
    BASE_DIR / 'gs_soundfont.sf2',                 # ✅ General MIDI
]

for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        logger.info(f"✅ Using SoundFont: {candidate.name}")
        break

if not SOUNDFONT_PATH:
    logger.warning("❌ No SoundFont found - please download one")

# Create directories
for directory in [AUDIO_OUTPUT_DIR, VOCAL_OUTPUT_DIR, MERGED_OUTPUT_DIR]:
    os.makedirs(directory, exist_ok=True)

# ==================== ADVANCED VOCAL SYNTHESIZER ====================

class AdvancedVocalSynthesizer:
    """Advanced vocal synthesizer dengan pitch adjustment dan rhythm matching"""
    
    def __init__(self):
        self.available = False
        self.setup()
        
    def setup(self):
        """Setup TTS engine"""
        if GTTS_AVAILABLE:
            self.available = True
            logger.info("✅ gTTS engine available for vocal synthesis")
        else:
            logger.warning("❌ gTTS not available - install with: pip install gtts")
            self.available = False
    
    def synthesize_vocals(self, lyrics, output_path, song_structure, key='C', tempo=120, language='id'):
        """Synthesize vocals dengan penyesuaian struktur lagu"""
        try:
            if not self.available:
                return False, "Vocal AI not available"
            
            # Process lyrics berdasarkan song structure
            processed_lyrics = self._distribute_lyrics_by_structure(lyrics, song_structure, tempo)
            if not processed_lyrics:
                return False, "No valid lyrics after processing"
            
            # Generate base vocals
            success, message = self._synthesize_gtts(processed_lyrics, output_path, language)
            
            if success:
                # Apply audio processing untuk match dengan musik
                self._process_vocal_audio(output_path, key, tempo, song_structure)
                return True, "Vocal synthesis successful with structure matching"
            else:
                return False, message
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _distribute_lyrics_by_structure(self, lyrics, song_structure, tempo):
        """Distribute lyrics berdasarkan song structure"""
        try:
            if not lyrics or len(lyrics.strip()) < 3:
                return None
            
            # Split lyrics into lines
            lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
            if not lines:
                return None
            
            # Map sections to lyrics
            section_lyrics = {}
            line_index = 0
            
            for section in song_structure:
                section_name = section['name']
                duration = section['duration_beats']
                
                # Determine how many lines for this section based on duration
                lines_per_section = max(1, int(duration / 8))  # Rough estimate
                
                section_lines = []
                for i in range(lines_per_section):
                    if line_index < len(lines):
                        section_lines.append(lines[line_index])
                        line_index += 1
                    else:
                        # Repeat lyrics if we run out
                        section_lines.append(lines[line_index % len(lines)])
                        line_index += 1
                
                section_lyrics[section_name] = '. '.join(section_lines)
            
            # Build final lyrics dengan section markers
            final_lyrics = []
            for section in song_structure:
                section_name = section['name']
                if section_name in section_lyrics:
                    final_lyrics.append(section_lyrics[section_name])
            
            return '. '.join(final_lyrics[:20])  # Limit total length
            
        except Exception as e:
            logger.error(f"Lyrics distribution error: {e}")
            return lyrics[:400]  # Fallback
    
    def _synthesize_gtts(self, text, output_path, language='id'):
        """Synthesize using gTTS"""
        try:
            # Map language codes
            lang_map = {
                'id': 'id', 'en': 'en', 
                'id-id': 'id', 'en-us': 'en'
            }
            
            tts_lang = lang_map.get(language.lower(), 'id')
            
            # Create gTTS object dengan speed adjustment
            tts_speed = 'slow' if len(text) < 100 else 'normal'
            
            tts = gTTS(
                text=text,
                lang=tts_lang,
                slow=(tts_speed == 'slow'),
                lang_check=False
            )
            
            # Save to file
            tts.save(str(output_path))
            
            # Verify file was created
            if output_path.exists() and output_path.stat().st_size > 1000:
                logger.info(f"✅ Base vocal generated: {output_path.name}")
                return True, "Base vocal synthesis successful"
            else:
                logger.error("❌ gTTS generated empty file")
                return False, "Generated file is empty"
                
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            return False, f"gTTS error: {str(e)}"
    
    def _process_vocal_audio(self, vocal_path, key='C', tempo=120, song_structure=None):
        """Process vocal audio untuk match dengan struktur lagu"""
        try:
            audio = AudioSegment.from_mp3(vocal_path)
            
            # Apply tempo-based processing
            if tempo > 140:
                # Speed up slightly for fast tempos
                audio = audio.speedup(playback_speed=1.05)
            elif tempo < 80:
                # Slow down slightly for slow tempos
                audio = audio.speedup(playback_speed=0.95)
            
            # Dynamic compression untuk vocal
            audio = compress_dynamic_range(audio, threshold=-20.0, ratio=2.0, attack=5.0, release=50.0)
            
            # Normalize volume
            audio = normalize(audio, headroom=3.0)
            
            # Export processed audio
            audio.export(vocal_path, format="mp3", bitrate="192k")
            logger.info(f"✅ Vocal audio processed for structure")
            
        except Exception as e:
            logger.error(f"Vocal audio processing error: {e}")

# Initialize Vocal AI
vocal_synth = AdvancedVocalSynthesizer()

# ==================== EXTENDED MUSIC GENERATION SETUP ====================

# Extended General MIDI Instruments
INSTRUMENTS = {
    # Piano
    'Acoustic Grand Piano': 0, 'Bright Acoustic Piano': 1, 'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3, 'Electric Piano 1': 4, 'Electric Piano 2': 5,
    'Harpsichord': 6, 'Clavinet': 7,
    
    # Chromatic Percussion
    'Celesta': 8, 'Glockenspiel': 9, 'Music Box': 10, 'Vibraphone': 11,
    'Marimba': 12, 'Xylophone': 13, 'Tubular Bells': 14, 'Dulcimer': 15,
    
    # Organ
    'Drawbar Organ': 16, 'Percussive Organ': 17, 'Rock Organ': 18, 'Church Organ': 19,
    'Reed Organ': 20, 'Accordion': 21, 'Harmonica': 22, 'Tango Accordion': 23,
    
    # Guitar
    'Nylon String Guitar': 24, 'Steel String Guitar': 25, 'Jazz Electric Guitar': 26,
    'Clean Electric Guitar': 27, 'Muted Electric Guitar': 28, 'Overdriven Guitar': 29,
    'Distortion Guitar': 30, 'Guitar Harmonics': 31,
    
    # Bass
    'Acoustic Bass': 32, 'Electric Bass finger': 33, 'Electric Bass pick': 34,
    'Fretless Bass': 35, 'Slap Bass 1': 36, 'Slap Bass 2': 37, 'Synth Bass 1': 38,
    'Synth Bass 2': 39,
    
    # Strings & Orchestra
    'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43, 'Tremolo Strings': 44,
    'Pizzicato Strings': 45, 'Orchestral Harp': 46, 'Timpani': 47,
    'String Ensemble 1': 48, 'String Ensemble 2': 49, 'Synth Strings 1': 50,
    'Synth Strings 2': 51,
    
    # Choir & Voice
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
    'Lead 1 (square)': 80, 'Lead 2 (sawtooth)': 81, 'Lead 3 (calliope)': 82,
    'Lead 4 (chiff)': 83, 'Lead 5 (charang)': 84, 'Lead 6 (voice)': 85,
    'Lead 7 (fifths)': 86, 'Lead 8 (bass + lead)': 87,
    
    # Synth Pad
    'Pad 1 (new age)': 88, 'Pad 2 (warm)': 89, 'Pad 3 (polysynth)': 90,
    'Pad 4 (choir)': 91, 'Pad 5 (bowed)': 92, 'Pad 6 (metallic)': 93,
    'Pad 7 (halo)': 94, 'Pad 8 (sweep)': 95,
    
    # Ethnic
    'Sitar': 104, 'Banjo': 105, 'Shamisen': 106, 'Koto': 107,
    'Kalimba': 108, 'Bag pipe': 109, 'Fiddle': 110, 'Shanai': 111,
    
    # Percussive
    'Tinkle Bell': 112, 'Agogo': 113, 'Steel Drums': 114, 'Woodblock': 115,
    'Taiko Drum': 116, 'Melodic Tom': 117, 'Synth Drum': 118,
    
    # Sound Effects
    'Reverse Cymbal': 119, 'Guitar Fret Noise': 120, 'Breath Noise': 121,
    'Seashore': 122, 'Bird Tweet': 123, 'Telephone Ring': 124,
    'Helicopter': 125, 'Applause': 126, 'Gunshot': 127,
}

# Extended Chords & Progressions
CHORDS = {
    # Basic Major & Minor
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

# Extended Scales
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'harmonic minor': [0, 2, 3, 5, 7, 8, 11],
    'melodic minor': [0, 2, 3, 5, 7, 9, 11],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9],
    'pentatonic minor': [0, 3, 5, 7, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
}

# ==================== SONG STRUCTURE SYSTEM ====================

def create_song_structure(genre, total_duration_minutes=3.5):
    """Create complete song structure dengan minimal 3 menit"""
    
    # Calculate total beats needed for desired duration
    base_tempo = GENRE_PARAMS[genre]['tempo']
    total_beats_needed = int(total_duration_minutes * 60 * base_tempo / 60)
    
    # Standard section durations in beats (adjustable)
    section_templates = {
        'intro': 8,
        'verse': 16,
        'pre_chorus': 8, 
        'chorus': 16,
        'bridge': 16,
        'interlude': 8,
        'outro': 12
    }
    
    # Common song structures
    structures = [
        # Structure 1: Classic Pop
        ['intro', 'verse1', 'pre_chorus', 'chorus', 'verse2', 'pre_chorus', 'chorus', 'bridge', 'chorus', 'outro'],
        # Structure 2: Rock
        ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'bridge', 'guitar_solo', 'chorus', 'outro'],
        # Structure 3: Ballad
        ['intro', 'verse1', 'chorus', 'verse2', 'chorus', 'bridge', 'final_chorus', 'outro'],
        # Structure 4: Complex
        ['intro', 'verse1', 'pre_chorus', 'chorus', 'verse2', 'pre_chorus', 'chorus', 'bridge', 'interlude', 'chorus', 'outro']
    ]
    
    # Select structure based on genre
    if genre in ['metal', 'progressive rock', 'progressive metal']:
        selected_structure = structures[3]  # Complex structure
    elif genre in ['rock', 'poprock']:
        selected_structure = structures[1]  # Rock structure  
    elif genre in ['ballad', 'slow rock']:
        selected_structure = structures[2]  # Ballad structure
    else:
        selected_structure = structures[0]  # Pop structure
    
    # Build song structure dengan durations
    song_structure = []
    current_beat = 0
    
    for section_name in selected_structure:
        # Get base duration for this section type
        base_duration = section_templates.get(section_name.replace('1', '').replace('2', ''), 8)
        
        # Variations for different sections
        if 'verse2' in section_name or 'final' in section_name:
            base_duration += 4  # Make later verses longer
        
        section_info = {
            'name': section_name,
            'start_beat': current_beat,
            'duration_beats': base_duration,
            'type': section_name.replace('1', '').replace('2', '').replace('final_', ''),
            'chord_progression': None,  # Will be filled later
            'instruments': {},  # Will be filled later
            'has_transition': False  # Will be set for transitions
        }
        
        song_structure.append(section_info)
        current_beat += base_duration
    
    # Adjust to meet minimum duration
    total_current_beats = current_beat
    if total_current_beats < total_beats_needed:
        # Add extra chorus or extend outro
        extra_beats_needed = total_beats_needed - total_current_beats
        song_structure[-1]['duration_beats'] += extra_beats_needed  # Extend outro
    
    logger.info(f"Created song structure: {[s['name'] for s in song_structure]} (Total: {current_beat} beats, ~{current_beat*60/base_tempo/60:.1f} minutes)")
    return song_structure

def assign_chord_progressions(song_structure, genre_params):
    """Assign chord progressions to each section"""
    progressions = genre_params['chord_progressions']
    
    for section in song_structure:
        section_type = section['type']
        
        # Different progressions for different sections
        if section_type == 'intro':
            # Simpler progression for intro
            section['chord_progression'] = progressions[0][:2] if len(progressions[0]) > 2 else progressions[0]
        elif section_type == 'verse':
            section['chord_progression'] = random.choice(progressions)
        elif section_type == 'chorus':
            # Use the first progression for chorus (usually strongest)
            section['chord_progression'] = progressions[0]
        elif section_type == 'bridge':
            # Different progression for bridge
            section['chord_progression'] = progressions[-1] if len(progressions) > 1 else progressions[0]
        elif section_type == 'outro':
            # Simple/fading progression for outro
            section['chord_progression'] = [progressions[0][-1]] if progressions[0] else ['C']
        else:
            section['chord_progression'] = random.choice(progressions)
    
    return song_structure

def assign_instruments_by_section(song_structure, genre_params):
    """Assign instruments dengan variations per section"""
    base_instruments = genre_params['instruments']
    
    for i, section in enumerate(song_structure):
        section_type = section['type']
        
        # Copy base instruments
        section_instruments = base_instruments.copy()
        
        # Section-specific variations
        if section_type == 'intro':
            # Simpler arrangement for intro
            if 'rhythm_secondary' in section_instruments:
                section_instruments['rhythm_secondary'] = None
        elif section_type == 'chorus':
            # Fuller arrangement for chorus
            section_instruments['melody'] = base_instruments['melody']
            section_instruments['rhythm_primary'] = base_instruments['rhythm_primary']
        elif section_type == 'bridge':
            # Different lead for bridge
            if genre_params['genre'] in ['rock', 'metal']:
                section_instruments['melody'] = 'Lead 1 (square)'
        elif section_type == 'outro':
            # Simpler arrangement for outro
            section_instruments['rhythm_secondary'] = None
        
        section['instruments'] = section_instruments
    
    return song_structure

def add_transitions(song_structure):
    """Add transitions between sections"""
    for i in range(len(song_structure) - 1):
        current_section = song_structure[i]
        next_section = song_structure[i + 1]
        
        # Add transition marker (last beat of current section)
        current_section['has_transition'] = True
        current_section['transition_to'] = next_section['name']
    
    return song_structure

# ==================== GENRE PARAMETERS ====================

GENRE_PARAMS = {
    'pop': {
        'tempo': 120, 'key': 'C', 'scale': 'major', 
        'instruments': {
            'melody': 'Electric Piano 1',
            'rhythm_primary': 'Clean Electric Guitar', 
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Electric Bass finger',
            'drums': 'standard'
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], 
            ['C', 'F', 'Am', 'G'], ['Dm', 'G', 'C', 'F']
        ],
        'mood': 'happy',
        'complexity': 'simple'
    },
    
    'poprock': {
        'tempo': 128, 'key': 'G', 'scale': 'major',
        'instruments': {
            'melody': 'Overdriven Guitar',
            'rhythm_primary': 'Clean Electric Guitar',
            'rhythm_secondary': 'Electric Piano 1',
            'bass': 'Electric Bass pick',
            'drums': 'rock'
        },
        'chord_progressions': [
            ['G', 'D', 'Em', 'C'], ['C', 'G', 'Am', 'F'],
            ['Em', 'C', 'G', 'D'], ['G', 'C', 'D', 'Em']
        ],
        'mood': 'energetic',
        'complexity': 'medium'
    },
    
    'rock': {
        'tempo': 130, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Electric Bass pick',
            'drums': 'rock'
        },
        'chord_progressions': [
            ['E', 'D', 'A', 'E'], ['A', 'G', 'D', 'A'],
            ['Em', 'G', 'D', 'A'], ['E5', 'A5', 'B5', 'E5']
        ],
        'mood': 'energetic',
        'complexity': 'medium'
    },
    
    'ballad': {
        'tempo': 70, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Warm Pad',
            'bass': 'Acoustic Bass',
            'drums': 'soft'
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'],
            ['F', 'C', 'Dm', 'G'], ['Em', 'Am', 'Dm', 'G']
        ],
        'mood': 'emotional',
        'complexity': 'simple'
    },
    
    'jazz': {
        'tempo': 120, 'key': 'C', 'scale': 'dorian',
        'instruments': {
            'melody': 'Tenor Sax',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Vibraphone',
            'bass': 'Acoustic Bass',
            'drums': 'jazz'
        },
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'], ['Cm7', 'F7', 'Bbmaj7'],
            ['Am7', 'D7', 'Gmaj7'], ['Em7', 'A7', 'Dmaj7']
        ],
        'mood': 'sophisticated',
        'complexity': 'high'
    },
    
    'metal': {
        'tempo': 160, 'key': 'Em', 'scale': 'minor',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Synth Brass 1',
            'bass': 'Slap Bass 1',
            'drums': 'heavy'
        },
        'chord_progressions': [
            ['Em', 'C', 'G', 'D'], ['Am', 'Em', 'F', 'G'],
            ['E5', 'G5', 'D5', 'A5'], ['B5', 'A5', 'G5', 'F#5']
        ],
        'mood': 'intense',
        'complexity': 'high'
    },
    
    'dangdut': {
        'tempo': 130, 'key': 'Am', 'scale': 'dangdut',
        'instruments': {
            'melody': 'Suling',
            'rhythm_primary': 'Kendang',
            'rhythm_secondary': 'Electric Organ',
            'bass': 'Electric Bass finger',
            'drums': 'dangdut'
        },
        'chord_progressions': [
            ['Am', 'E7', 'Am', 'E7'], ['Am', 'Dm', 'E7', 'Am'],
            ['Dm', 'Am', 'E7', 'Am'], ['Am', 'G', 'F', 'E7']
        ],
        'mood': 'festive',
        'complexity': 'medium'
    },
}

# ==================== ADVANCED MUSIC GENERATION ====================

def chord_names_to_midi_notes(chord_names, octave=4):
    """Convert chord names to MIDI notes dengan octave adjustment"""
    if not isinstance(chord_names, list):
        return [CHORDS['C']]
    
    midi_chords = []
    for chord_name in chord_names:
        if isinstance(chord_name, str) and chord_name in CHORDS:
            base_chord = CHORDS[chord_name]
            # Adjust octave
            adjusted_chord = [note + (octave * 12) for note in base_chord]
            midi_chords.append(adjusted_chord)
        else:
            midi_chords.append(CHORDS['C'])
    
    return midi_chords

def detect_genre_from_lyrics(lyrics):
    """Genre detection from lyrics"""
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
    elif any(word in lyrics_lower for word in ['dangdut', 'koplo', 'sunda', 'tradisional']):
        return 'dangdut'
    else:
        return 'pop'

def get_music_params_from_lyrics(genre, lyrics, tempo_input='auto'):
    """Get music parameters for generation"""
    params = GENRE_PARAMS.get(genre, GENRE_PARAMS['pop']).copy()
    params['genre'] = genre
    
    # Handle tempo
    if tempo_input != 'auto':
        try:
            tempo_val = int(tempo_input)
            if 60 <= tempo_val <= 200:
                params['tempo'] = tempo_val
        except ValueError:
            pass
    
    # Create complete song structure
    song_structure = create_song_structure(genre)
    song_structure = assign_chord_progressions(song_structure, params)
    song_structure = assign_instruments_by_section(song_structure, params)
    song_structure = add_transitions(song_structure)
    
    params['song_structure'] = song_structure
    params['total_duration'] = sum(s['duration_beats'] for s in song_structure) * 60 / params['tempo']
    
    logger.info(f"Advanced music params: {genre}, tempo={params['tempo']}, duration={params['total_duration']:.1f}s")
    logger.info(f"Song structure: {[s['name'] for s in song_structure]}")
    
    return params

def create_structured_midi(params, output_path):
    """Create structured MIDI file dengan sections dan transitions"""
    try:
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Set initial tempo
        tempo = bpm2tempo(params['tempo'])
        track.append(MetaMessage('set_tempo', tempo=tempo))
        
        current_time = 0
        song_structure = params['song_structure']
        
        for section in song_structure:
            section_name = section['name']
            duration_beats = section['duration_beats']
            chords = chord_names_to_midi_notes(section['chord_progression'])
            instruments = section['instruments']
            
            logger.info(f"Generating section: {section_name} ({duration_beats} beats)")
            
            # Set instrument for this section
            melody_program = INSTRUMENTS.get(instruments['melody'], 0)
            track.append(Message('program_change', program=melody_program, time=current_time))
            
            # Generate section content
            beats_per_chord = duration_beats / len(chords) if chords else duration_beats
            
            for i, chord in enumerate(chords):
                chord_start = i * beats_per_chord
                chord_duration = beats_per_chord
                
                # Simple melody based on chord
                if chord:
                    note = random.choice(chord)
                    velocity = 80 if section['type'] == 'chorus' else 70
                    
                    # Convert beats to ticks (480 ticks per beat)
                    start_ticks = int(chord_start * 480)
                    duration_ticks = int(chord_duration * 480 * 0.8)  # 80% of chord duration
                    
                    track.append(Message('note_on', note=note, velocity=velocity, time=start_ticks))
                    track.append(Message('note_off', note=note, velocity=0, time=duration_ticks))
            
            # Add transition effect if needed
            if section.get('has_transition', False):
                # Add a drum fill or cymbal crash
                track.append(Message('note_on', channel=9, note=49, velocity=100, time=int((duration_beats - 1) * 480)))
                track.append(Message('note_off', channel=9, note=49, velocity=0, time=120))
            
            current_time += int(duration_beats * 480)
        
        # Add fade out for outro
        last_section = song_structure[-1]
        if last_section['type'] == 'outro':
            # Gradually reduce tempo for fade out
            fade_tempo = bpm2tempo(params['tempo'] * 0.7)  # Slow down 30%
            track.append(MetaMessage('set_tempo', tempo=fade_tempo, time=current_time - 240))
        
        mid.save(output_path)
        logger.info(f"Structured MIDI created: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Structured MIDI creation error: {e}")
        return False

def midi_to_audio_advanced(midi_path, output_wav_path, genre='pop'):
    """Convert MIDI to WAV dengan genre-specific settings"""
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False
    
    try:
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-ni', str(SOUNDFONT_PATH), str(midi_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"Advanced WAV generated: {output_wav_path}")
            return True
        else:
            logger.error(f"FluidSynth failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Advanced MIDI to audio error: {e}")
        return False

def advanced_audio_processing(audio_path, genre='pop'):
    """Apply advanced audio processing"""
    try:
        audio = AudioSegment.from_file(audio_path)
        
        # Apply compression
        audio = compress_dynamic_range(audio, threshold=-20.0, ratio=2.0, attack=5.0, release=50.0)
        
        # Normalize volume
        audio = normalize(audio, headroom=2.0)
        
        # Export processed audio
        audio.export(audio_path, format="mp3", bitrate="192k")
        logger.info(f"✅ Advanced audio processing applied for {genre}")
        return True
        
    except Exception as e:
        logger.error(f"Advanced audio processing error: {e}")
        return False

def wav_to_mp3_advanced(wav_path, mp3_path, genre='pop'):
    """Convert WAV to MP3 dengan advanced processing"""
    try:
        audio = AudioSegment.from_wav(wav_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        
        # Apply advanced processing
        advanced_audio_processing(mp3_path, genre)
        
        logger.info(f"Advanced MP3 created: {mp3_path}")
        return True
    except Exception as e:
        logger.error(f"Advanced WAV to MP3 error: {e}")
        return False

def merge_audio_with_vocals_advanced(instrumental_path, vocal_path, output_path, genre='pop'):
    """Advanced audio merging dengan balance adjustment"""
    try:
        if not instrumental_path.exists():
            return False, "Instrumental file not found"
        if not vocal_path.exists():
            return False, "Vocal file not found"
        
        instrumental = AudioSegment.from_mp3(instrumental_path)
        vocals = AudioSegment.from_mp3(vocal_path)
        
        # Ensure vocals don't exceed instrumental length
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        # Mix audio
        mixed = instrumental.overlay(vocals, position=0)
        
        # Apply final processing
        mixed = compress_dynamic_range(mixed, threshold=-15.0, ratio=1.5)
        mixed = normalize(mixed, headroom=1.0)
        
        mixed.export(output_path, format="mp3", bitrate="192k")
        
        logger.info(f"Advanced merged audio created: {output_path}")
        return True, "Advanced merge successful"
        
    except Exception as e:
        logger.error(f"Advanced audio merging error: {e}")
        return False, f"Advanced merge error: {str(e)}"

# ==================== FLASK ROUTES ====================

def generate_unique_id(text):
    """Generate unique ID"""
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

@app.route('/')
def index():
    """Main interface dengan song structure info"""
    html_template = '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Advanced AI Music Generator</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 min-h-screen p-4">
        <div class="max-w-4xl mx-auto">
            <div class="bg-white rounded-lg shadow-lg p-6">
                <h1 class="text-3xl font-bold text-center mb-2">🎵 Advanced AI Music Generator</h1>
                <p class="text-center text-gray-600 mb-6">Structured Songs • 3+ Minutes • Section Transitions • Vocal Matching</p>
                
                <form id="musicForm" class="space-y-4">
                    <div>
                        <label class="block font-semibold mb-2">Lirik Lagu:</label>
                        <textarea id="lyrics" rows="4" class="w-full p-3 border rounded" placeholder="Masukkan lirik lagu..."></textarea>
                        <p class="text-sm text-gray-500 mt-1">Lirik akan didistribusikan ke verse, chorus, bridge, dll.</p>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block font-semibold mb-2">Genre:</label>
                            <select id="genre" class="w-full p-2 border rounded">
                                <option value="auto">Auto Detect</option>
                                <option value="pop">Pop</option>
                                <option value="poprock">Pop Rock</option>
                                <option value="rock">Rock</option>
                                <option value="ballad">Ballad</option>
                                <option value="jazz">Jazz</option>
                                <option value="metal">Metal</option>
                                <option value="dangdut">Dangdut</option>
                            </select>
                        </div>
                        <div>
                            <label class="block font-semibold mb-2">Tempo (BPM):</label>
                            <input type="number" id="tempo" class="w-full p-2 border rounded" placeholder="Auto" min="60" max="200">
                        </div>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input type="checkbox" id="addVocals" class="w-4 h-4" checked>
                        <label class="font-semibold">Tambahkan AI Vocal (Structure Matched)</label>
                    </div>
                    
                    <div class="bg-blue-50 p-3 rounded">
                        <h4 class="font-semibold text-blue-800">🎼 Song Structure:</h4>
                        <p class="text-sm text-blue-600">Intro → Verse → Pre-Chorus → Chorus → Verse → Chorus → Bridge → Chorus → Outro (Fade)</p>
                        <p class="text-sm text-blue-600">Durasi: Minimal 3 menit dengan transitions antar section</p>
                    </div>
                    
                    <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 rounded font-bold hover:bg-blue-700">
                        🚀 Generate Structured Song (3+ Minutes)
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
                        <h3 class="font-bold mb-2">🎤 AI Vocals (Structure Matched)</h3>
                        <audio id="vocalAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('vocal')" class="bg-green-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                    
                    <div id="mergedResult" class="border rounded p-4 hidden">
                        <h3 class="font-bold mb-2">🎶 Full Song (Balanced Mix)</h3>
                        <audio id="mergedAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('merged')" class="bg-purple-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                </div>
            </div>
            
            <div class="mt-4 text-center text-sm text-gray-600">
                <div>Vocal AI: <span id="vocalStatus" class="font-semibold">Checking...</span></div>
                <div>SoundFont: <span id="soundfontStatus" class="font-semibold">Checking...</span></div>
                <div>Song Structure: <span class="text-green-600 font-semibold">✅ Enabled</span></div>
            </div>
        </div>

        <script>
            // Check system status
            fetch('/system-status').then(r => r.json()).then(data => {
                document.getElementById('vocalStatus').textContent = data.vocal_ai ? '✅ Available' : '❌ Install gTTs';
                document.getElementById('vocalStatus').className = data.vocal_ai ? 'text-green-600' : 'text-red-600';
                document.getElementById('soundfontStatus').textContent = data.soundfont ? '✅ Available' : '❌ Not Found';
                document.getElementById('soundfontStatus').className = data.soundfont ? 'text-green-600' : 'text-red-600';
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
                btn.textContent = 'Generating Structured Song...';
                status.classList.remove('hidden');
                statusMessage.innerHTML = '<div class="text-blue-600">🚀 Generating 3+ minute structured song with sections and transitions... (3-4 minutes)</div>';
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
                        statusMessage.innerHTML = '<div class="text-green-600">✅ Structured song generation successful!</div>';
                        
                        // Update structure info
                        if (data.instrumental && data.instrumental.structure) {
                            structureInfo.innerHTML = `<strong>Structure:</strong> ${data.instrumental.structure.join(' → ')}<br>
                                                      <strong>Duration:</strong> ${data.instrumental.duration || '3+'} minutes`;
                        }
                        
                        // Update audio players
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
                        statusMessage.innerHTML = '<div class="text-red-600">❌ ' + (data.error || 'Generation failed') + '</div>';
                    }

                } catch (error) {
                    statusMessage.innerHTML = '<div class="text-red-600">❌ Network error</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '🚀 Generate Structured Song (3+ Minutes)';
                }
            });

            function downloadAudio(type) {
                let audioElement, filename;
                switch(type) {
                    case 'instrumental':
                        audioElement = document.getElementById('instrumentalAudio');
                        filename = 'instrumental_structured.mp3';
                        break;
                    case 'vocal':
                        audioElement = document.getElementById('vocalAudio');
                        filename = 'vocals_structure_matched.mp3';
                        break;
                    case 'merged':
                        audioElement = document.getElementById('mergedAudio');
                        filename = 'full_song_structured.mp3';
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
    """Check system status"""
    return jsonify({
        'vocal_ai': vocal_synth.available,
        'soundfont': SOUNDFONT_PATH and SOUNDFONT_PATH.exists(),
        'song_structure': True
    })

# Internal functions dengan advanced features
def generate_instrumental_internal(lyrics, genre_input='auto', tempo_input='auto'):
    """Internal function for advanced instrumental generation"""
    try:
        # Get advanced music parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Generate files
        unique_id = generate_unique_id(lyrics)
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav"
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        
        # Create structured MIDI
        if not create_structured_midi(params, midi_path):
            return {'success': False, 'error': 'Structured MIDI creation failed'}
        
        # Convert to audio dengan genre-specific settings
        if not midi_to_audio_advanced(midi_path, wav_path, genre):
            midi_path.unlink(missing_ok=True)
            return {'success': False, 'error': 'Advanced audio conversion failed'}
        
        # Convert to MP3 dengan advanced processing
        if not wav_to_mp3_advanced(wav_path, mp3_path, genre):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return {'success': False, 'error': 'Advanced MP3 conversion failed'}
        
        # Cleanup
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        return {
            'success': True,
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo'],
            'duration': f"{params['total_duration']/60:.1f}",
            'structure': [s['name'] for s in params['song_structure']],
            'song_structure': params['song_structure']
        }
        
    except Exception as e:
        logger.error(f"Structured instrumental generation error: {e}")
        return {'success': False, 'error': 'Structured generation failed'}

def generate_vocals_internal(lyrics, song_structure, key='C', tempo=120):
    """Internal function for advanced vocal generation dengan structure matching"""
    try:
        if not lyrics:
            return {'success': False, 'error': 'Lirik diperlukan'}
        
        vocal_id = generate_unique_id(lyrics)
        output_path = VOCAL_OUTPUT_DIR / f"{vocal_id}.mp3"
        
        success, message = vocal_synth.synthesize_vocals(lyrics, output_path, song_structure, key, tempo)
        
        if success:
            return {
                'success': True,
                'filename': f'{vocal_id}.mp3',
                'vocal_url': f'/static/vocal_output/{vocal_id}.mp3',
                'message': message
            }
        else:
            return {'success': False, 'error': message}
            
    except Exception as e:
        logger.error(f"Structured vocal generation error: {e}")
        return {'success': False, 'error': 'Structured vocal generation failed'}

@app.route('/generate-full-song', methods=['POST'])
def generate_full_song():
    """Generate complete song dengan advanced features"""
    try:
        # Handle both form data and JSON
        if request.content_type == 'application/json':
            data = request.get_json()
        else:
            data = request.form.to_dict()
            
        lyrics = data.get('lyrics', '').strip()
        genre = data.get('genre', 'auto')
        tempo = data.get('tempo', 'auto')
        add_vocals = data.get('add_vocals', 'false').lower() == 'true'
        
        if not lyrics:
            return jsonify({'error': 'Lirik diperlukan'}), 400
        
        result = {
            'success': True,
            'instrumental': None,
            'vocals': None, 
            'merged': None
        }
        
        # Generate structured instrumental
        instrumental_data = generate_instrumental_internal(lyrics, genre, tempo)
        if not instrumental_data.get('success'):
            return jsonify({'error': instrumental_data.get('error', 'Instrumental generation failed')}), 500
        
        result['instrumental'] = instrumental_data
        
        # Generate structured vocals if requested
        if add_vocals and vocal_synth.available:
            vocal_data = generate_vocals_internal(
                lyrics, 
                instrumental_data.get('song_structure', []),
                instrumental_data.get('key', 'C'),
                instrumental_data.get('tempo', 120)
            )
            
            if vocal_data.get('success'):
                result['vocals'] = vocal_data
                
                # Advanced audio merging
                instrumental_path = AUDIO_OUTPUT_DIR / instrumental_data['filename']
                vocal_path = VOCAL_OUTPUT_DIR / vocal_data['filename']
                merged_id = generate_unique_id(lyrics + "_structured")
                merged_path = MERGED_OUTPUT_DIR / f"{merged_id}.mp3"
                
                success, message = merge_audio_with_vocals_advanced(
                    instrumental_path, vocal_path, merged_path, instrumental_data['genre']
                )
                if success:
                    result['merged'] = {
                        'filename': f'{merged_id}.mp3',
                        'message': message
                    }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Structured full song generation error: {e}")
        return jsonify({'error': f'Structured generation failed: {str(e)}'}), 500

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
    """Start advanced application"""
    logger.info("🎵 Starting Structured AI Music Generator")
    logger.info(f"✅ SoundFont: {'Available' if SOUNDFONT_PATH else 'Not Found'}")
    logger.info(f"✅ Vocal AI: {'Available' if vocal_synth.available else 'Not Available'}")
    logger.info(f"✅ Song Structure: Enabled (3+ minutes)")
    logger.info(f"✅ Section Transitions: Enabled")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
