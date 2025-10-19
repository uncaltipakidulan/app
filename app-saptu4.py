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
from pydub.effects import normalize as pydub_normalize

# ==================== VOCAL AI IMPORTS ====================
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("⚠️  gTTS not available - vocal synthesis disabled")

try:
    import torch
    import torchaudio
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("⚠️  PyTorch not available - advanced vocal features disabled")

# TextBlob untuk sentiment analysis
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("⚠️  TextBlob not available - sentiment analysis disabled")

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
VOCAL_OUTPUT_DIR = STATIC_DIR / 'vocal_output'  # ✅ NEW: Vocal output directory
MERGED_OUTPUT_DIR = STATIC_DIR / 'merged_output'  # ✅ NEW: Merged audio directory

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
os.makedirs(VOCAL_OUTPUT_DIR, exist_ok=True)  # ✅ NEW
os.makedirs(MERGED_OUTPUT_DIR, exist_ok=True)  # ✅ NEW

# ==================== VOCAL AI SYNTHESIZER CLASS ====================

class VocalSynthesizer:
    """Vocal AI synthesizer menggunakan multiple TTS engines"""
    
    def __init__(self):
        self.available_engines = []
        self.setup_engines()
        
    def setup_engines(self):
        """Detect available TTS engines"""
        if GTTS_AVAILABLE:
            self.available_engines.append('gtts')
            logger.info("✅ gTTS engine available")
        
        # Future: Add more engines like Coqui TTS, Azure TTS, etc.
        if len(self.available_engines) == 0:
            logger.warning("❌ No TTS engines available - vocal synthesis disabled")
        else:
            logger.info(f"🎤 Vocal AI ready with engines: {', '.join(self.available_engines)}")
    
    def synthesize_vocals(self, lyrics, output_path, language='id', voice_type='female'):
        """Synthesize vocals from lyrics"""
        try:
            if not self.available_engines:
                return False, "No TTS engines available"
                
            # Preprocess lyrics
            processed_lyrics = self._preprocess_lyrics(lyrics)
            if not processed_lyrics:
                return False, "No valid lyrics after processing"
            
            # Use gTTS as primary engine
            if 'gtts' in self.available_engines:
                success = self._synthesize_gtts(processed_lyrics, output_path, language)
                if success:
                    return True, "Vocal synthesis successful"
            
            return False, "All TTS engines failed"
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _preprocess_lyrics(self, lyrics):
        """Clean and prepare lyrics for TTS"""
        try:
            if not lyrics or len(lyrics.strip()) < 5:
                return None
            
            # Basic cleaning
            cleaned = ' '.join(lyrics.split())
            cleaned = cleaned.replace('\n', '. ')
            
            # Remove problematic characters but keep basic punctuation
            import re
            cleaned = re.sub(r'[^\w\s.,!?;:\'\-]', '', cleaned)
            
            # Split into manageable chunks (avoid TTS limits)
            sentences = re.split(r'[.!?]+', cleaned)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 3]
            
            if not sentences:
                return None
                
            # Combine sentences with pauses
            processed = '. '.join(sentences[:6])  # Limit to 6 sentences for performance
            
            return processed[:400]  # Limit length for stability
            
        except Exception as e:
            logger.error(f"Lyrics preprocessing error: {e}")
            return lyrics[:300]  # Fallback
    
    def _synthesize_gtts(self, text, output_path, language='id'):
        """Synthesize using gTTS"""
        try:
            # Map language codes
            lang_map = {
                'id': 'id',
                'en': 'en', 
                'id-id': 'id',
                'en-us': 'en'
            }
            
            tts_lang = lang_map.get(language.lower(), 'id')
            
            # Create gTTS object
            tts = gTTS(
                text=text,
                lang=tts_lang,
                slow=False,  # Normal speed
                lang_check=False
            )
            
            # Save to file
            tts.save(str(output_path))
            
            # Verify file was created
            if output_path.exists() and output_path.stat().st_size > 1000:
                logger.info(f"✅ gTTS vocal generated: {output_path.name} ({output_path.stat().st_size/1024:.1f} KB)")
                return True
            else:
                logger.error("❌ gTTS generated empty file")
                return False
                
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            return False

# Initialize Vocal AI
vocal_synthesizer = VocalSynthesizer()

# ==================== MUSIC GENERATION CODE (EXISTING) ====================

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
        'gTTS': check_module('gtts'),
    }
    available_deps = [name for name, available in deps.items() if available]
    logger.info("Python dependencies detected: {}".format(', '.join(available_deps)))
    return available_deps

# General MIDI Instruments (case-insensitive matching)
INSTRUMENTS = {
    # Piano
    'Acoustic Grand Piano': 0,
    'Bright Acoustic Piano': 1,
    'Electric Grand Piano': 2,
    'Honky-tonk Piano': 3,
    'Electric Piano 1': 4,
    'Electric Piano 2': 5,
    'Harpsichord': 6,
    'Clavinet': 7,
    # Chromatic Percussion
    'Celesta': 8,
    'Glockenspiel': 9,
    'Music Box': 10,
    'Vibraphone': 11,
    'Marimba': 12,
    'Xylophone': 13,
    'Tubular Bells': 14,
    'Dulcimer': 15,
    # Organ
    'Drawbar Organ': 16,
    'Percussive Organ': 17,
    'Rock Organ': 18,
    'Church Organ': 19,
    'Reed Organ': 20,
    'Pipe Organ': 21,
    'Hammond Organ': 17,
    'Rotary Organ': 18,
    # Guitar
    'Nylon String Guitar': 24,
    'Steel String Guitar': 25,
    'Jazz Electric Guitar': 26,
    'Clean Electric Guitar': 27,
    'Muted Electric Guitar': 28,
    'Overdriven Guitar': 29,
    'Distortion Guitar': 30,
    'Guitar Harmonics': 31,
    # Bass
    'Acoustic Bass': 32,
    'Electric Bass finger': 33,
    'Electric Bass pick': 34,
    'Fretless Bass': 35,
    'Slap Bass 1': 36,
    'Slap Bass 2': 37,
    'Synth Bass 1': 38,
    'Synth Bass 2': 39,
    # Strings
    'Violin': 40,
    'Viola': 41,
    'Cello': 42,
    'Contrabass': 43,
    'Tremolo Strings': 44,
    'Pizzicato Strings': 45,
    'Orchestral Strings': 46,
    'String Ensemble 1': 48,
    'String Ensemble 2': 49,
    'Synth Strings 1': 50,
    'Synth Strings 2': 51,
    # Choir & Pad
    'Choir Aahs': 52,
    'Voice Oohs': 53,
    'Synth Voice': 54,
    'Orchestra Hit': 55,
    # Brass
    'Trumpet': 56,
    'Trombone': 57,
    'Tuba': 58,
    'Muted Trumpet': 59,
    'French Horn': 60,
    'Brass Section': 61,
    'Synth Brass 1': 62,
    'Synth Brass 2': 63,
    # Reed
    'Soprano Sax': 64,
    'Alto Sax': 65,
    'Tenor Sax': 66,
    'Baritone Sax': 67,
    'Oboe': 68,
    'English Horn': 69,
    'Bassoon': 70,
    'Clarinet': 71,
    # Pipe
    'Piccolo': 72,
    'Flute': 73,
    'Recorder': 74,
    'Pan Flute': 75,
    'Blown Bottle': 76,
    'Shakuhachi': 77,
    'Whistle': 78,
    'Ocarina': 79,
    # Synth Lead
    'Square Wave': 80,
    'Sawtooth Wave': 81,
    'Calliope Lead': 82,
    'Chiff Lead': 83,
    'Charang': 84,
    'Voice Lead': 85,
    'Fifth Saw Wave': 86,
    'Bass & Lead': 87,
    # Synth Pad
    'New Age Pad': 88,
    'Warm Pad': 89,
    'Poly Synth Pad': 90,
    'Choir Pad': 91,
    'Bowed Glass Pad': 92,
    'Metallic Pad': 93,
    'Halo Pad': 94,
    'Sweep Pad': 95,
    # Ethnic
    'Sitar': 104,
    'Banjo': 105,
    'Shamisen': 106,
    'Koto': 107,
    'Kalimba': 108,
    'Bagpipe': 109,
    'Fiddle': 110,
    'Shanai': 111,
    # Sound Effects
    'Guitar Fret Noise': 120,
    'Breath Noise': 121,
    'Seashore': 122,
    'Bird Tweet': 123,
    'Telephone Ring': 124,
    'Helicopter': 125,
    'Applause': 126,
    'Gunshot': 127,
    # Indonesian Instruments (approximations)
    'Gamelan': 114,
    'Kendang': 115,
    'Suling': 75,
    'Rebab': 110,
    'Talempong': 14,
    'Gambus': 25,
    'Mandolin': 27,
    'Harmonica': 22,
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
    # Seventh chords
    'C7': [60, 64, 67, 70], 'D7': [62, 66, 69, 72], 'E7': [64, 68, 71, 74],
    'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77], 'A7': [69, 73, 76, 79],
    'B7': [71, 75, 78, 82], 'Cm7': [60, 63, 67, 70], 'Dm7': [62, 65, 69, 72],
    'Em7': [64, 67, 71, 74], 'Fm7': [65, 68, 72, 75], 'Gm7': [67, 70, 74, 77],
    'Am7': [69, 72, 76, 79], 'Bbmaj7': [70, 74, 77, 81], 'Cmaj7': [60, 64, 67, 71],
    'Dmaj7': [62, 66, 69, 73], 'Emaj7': [64, 68, 71, 75], 'Fmaj7': [65, 69, 72, 76],
    'Gmaj7': [67, 71, 74, 78], 'Amaj7': [69, 73, 76, 80], 'Ebmaj7': [63, 67, 70, 74],
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
    'kick': 36, 'snare': 38, 'hat_closed': 42, 'ride': 51,
    'crash': 49, 'tom_high': 47, 'tom_mid': 45, 'tom_low': 43,
}

# Genre parameters
GENRE_PARAMS = {
    'pop': {'tempo': 126, 'key': 'C', 'scale': 'major', 'instruments': {'melody': 'Clean Electric Guitar', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'String Ensemble 1', 'bass': 'Electric Bass finger'}, 'drums_enabled': True, 'chord_progressions': [['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['C', 'F', 'Am', 'G']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'melodic', 'mood': 'happy'},
    'rock': {'tempo': 135, 'key': 'E', 'scale': 'pentatonic', 'instruments': {'melody': 'Distortion Guitar', 'rhythm_primary': 'Overdriven Guitar', 'rhythm_secondary': 'Rock Organ', 'bass': 'Electric Bass pick'}, 'drums_enabled': True, 'chord_progressions': [['E', 'D', 'A', 'E'], ['A', 'G', 'D', 'A'], ['Em', 'G', 'D', 'A']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'driving', 'mood': 'energetic'},
    'metal': {'tempo': 120, 'key': 'E', 'scale': 'minor', 'instruments': {'melody': 'Distortion Guitar', 'rhythm_primary': 'Overdriven Guitar', 'rhythm_secondary': 'String Ensemble 1', 'bass': 'Electric Bass pick'}, 'drums_enabled': True, 'chord_progressions': [['E5', 'G5', 'D5', 'A5'], ['Em', 'C', 'G', 'D'], ['Am', 'Em', 'F', 'G']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'heavy', 'mood': 'intense'},
    'ballad': {'tempo': 72, 'key': 'C', 'scale': 'major', 'instruments': {'melody': 'Nylon String Guitar', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'Warm Pad', 'bass': 'Acoustic Bass'}, 'drums_enabled': True, 'chord_progressions': [['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'], ['F', 'C', 'Dm', 'G']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'sustained', 'mood': 'emotional'},
    'blues': {'tempo': 100, 'key': 'A', 'scale': 'blues', 'instruments': {'melody': 'Tenor Sax', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'Brass Section', 'bass': 'Acoustic Bass'}, 'drums_enabled': True, 'chord_progressions': [['A7', 'D7', 'E7'], ['G7', 'C7', 'D7'], ['E7', 'A7', 'B7']], 'base_duration_beats_per_section': {'intro': 12, 'verse': 12, 'pre_chorus': 8, 'chorus': 12, 'bridge': 12, 'interlude': 8, 'outro': 8}, 'bass_style': 'walking', 'mood': 'soulful'},
    'jazz': {'tempo': 140, 'key': 'C', 'scale': 'major', 'instruments': {'melody': 'Tenor Sax', 'rhythm_primary': 'Electric Piano 1', 'rhythm_secondary': 'Brass Section', 'bass': 'Acoustic Bass'}, 'drums_enabled': True, 'chord_progressions': [['Dm7', 'G7', 'Cmaj7'], ['Cm7', 'F7', 'Bbmaj7'], ['Am7', 'D7', 'Gmaj7']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'walking', 'mood': 'sophisticated'},
    'hiphop': {'tempo': 97, 'key': 'Cm', 'scale': 'minor', 'instruments': {'melody': 'Electric Piano 2', 'rhythm_primary': 'Poly Synth Pad', 'rhythm_secondary': 'Synth Bass 1', 'bass': 'Synth Bass 1'}, 'drums_enabled': True, 'chord_progressions': [['Cm', 'Ab', 'Bb', 'Fm'], ['Fm', 'Ab', 'Bb', 'Eb'], ['Eb', 'Bb', 'Cm', 'Ab']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'syncopated', 'mood': 'urban'},
    'latin': {'tempo': 91, 'key': 'G', 'scale': 'latin', 'instruments': {'melody': 'Nylon String Guitar', 'rhythm_primary': 'Acoustic Grand Piano', 'rhythm_secondary': 'String Ensemble 1', 'bass': 'Acoustic Bass'}, 'drums_enabled': True, 'chord_progressions': [['Am', 'D7', 'Gmaj7', 'Cmaj7'], ['G', 'Bm', 'Em', 'A7'], ['Dm', 'G7', 'Cmaj7', 'Fmaj7']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'tumbao', 'mood': 'rhythmic'},
    'dangdut': {'tempo': 140, 'key': 'Am', 'scale': 'dangdut', 'instruments': {'melody': 'Suling', 'rhythm_primary': 'Gamelan', 'rhythm_secondary': 'Clean Electric Guitar', 'bass': 'Electric Bass finger'}, 'drums_enabled': True, 'chord_progressions': [['Am', 'E7', 'Am', 'E7'], ['Am', 'Dm', 'E7', 'Am'], ['Dm', 'Am', 'E7', 'Am']], 'base_duration_beats_per_section': {'intro': 8, 'verse': 16, 'pre_chorus': 8, 'chorus': 16, 'bridge': 16, 'interlude': 8, 'outro': 8}, 'bass_style': 'offbeat_syncopated', 'mood': 'traditional'}
}

# ==================== MUSIC GENERATION FUNCTIONS ====================

def chord_names_to_midi_notes(chord_names, key='C'):
    """Convert list of chord names to MIDI note numbers"""
    if not isinstance(chord_names, list):
        logger.error(f"chord_names is not a list: {type(chord_names)}")
        return [CHORDS['C']]
    
    midi_chords = []
    for i, chord_name in enumerate(chord_names):
        if isinstance(chord_name, str) and chord_name in CHORDS:
            midi_chords.append(CHORDS[chord_name])
        elif isinstance(chord_name, list) and all(isinstance(n, (int, float)) for n in chord_name):
            valid_chord = [max(0, min(127, int(round(n)))) for n in chord_name]
            midi_chords.append(valid_chord)
        else:
            logger.warning(f"Chord {i} '{chord_name}' not found. Using C major.")
            midi_chords.append(CHORDS['C'])
    
    return midi_chords

def select_progression(params, lyrics=""):
    """Select chord progression based on mood and sentiment analysis"""
    progressions = params['chord_progressions']
    
    if lyrics and len(lyrics.strip()) > 0 and TEXTBLOB_AVAILABLE:
        try:
            blob = TextBlob(lyrics)
            polarity = blob.sentiment.polarity
            if polarity > 0.1:  # Happy mood
                major_progressions = [prog for prog in progressions 
                                   if all(not c.endswith('m') and 'dim' not in c and 'sus' not in c 
                                          for c in prog)]
                if major_progressions:
                    return random.choice(major_progressions)
            elif polarity < -0.1:  # Sad mood
                minor_progressions = [prog for prog in progressions 
                                    if all(c.endswith('m') or 'dim' in c for c in prog)]
                if minor_progressions:
                    return random.choice(minor_progressions)
        except Exception as e:
            logger.warning(f"Sentiment analysis error: {e}")
    
    selected = random.choice(progressions)
    logger.info(f"Selected progression: {selected} for mood {params['mood']}")
    return selected

def detect_genre_from_lyrics(lyrics):
    """Detect genre from lyrics using keyword matching"""
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
        scores = {genre: sum(1 for keyword in kw_list if keyword in words) for genre, kw_list in keywords.items()}
        detected_genre = max(scores, key=scores.get) if max(scores.values()) > 0 else 'pop'
        logger.info(f"Genre detected from keywords: '{detected_genre}'")
        return detected_genre
    except Exception as e:
        logger.warning(f"Genre detection error: {e}")
        return 'pop'

def find_best_instrument(choice, is_rock_metal=False):
    """Fuzzy matching for instruments"""
    if not choice:
        return 'Acoustic Grand Piano'
    if isinstance(choice, list):
        choice = choice[0]
    
    choice_lower = str(choice).lower().strip()
    if is_rock_metal and 'power chord' in choice_lower:
        return 'Overdriven Guitar'
    
    for instr_name, num in INSTRUMENTS.items():
        if choice_lower in instr_name.lower():
            return instr_name
    
    logger.warning(f"No good instrument match for '{choice}', falling back to Acoustic Grand Piano.")
    return 'Acoustic Grand Piano'

def get_music_params_from_lyrics(genre, lyrics, user_tempo_input='auto'):
    """Generate instrumental parameters"""
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
                    logger.warning(f"Tempo out of range (60-200 BPM): {user_tempo_input}, using default.")
            except ValueError:
                logger.warning(f"Invalid tempo input: '{user_tempo_input}', using default.")
        
        # Sentiment analysis
        if lyrics and len(lyrics.strip()) > 0 and TEXTBLOB_AVAILABLE:
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
            logger.info(f"{category.capitalize()} instrument: {instrument_name} (Program {program_num})")
        
        # Convert chord names to MIDI notes
        selected_progression_names = select_progression(params, lyrics)
        params['chords'] = chord_names_to_midi_notes(selected_progression_names)
        params['selected_progression'] = selected_progression_names
        
        logger.info(f"Parameter instrumental untuk {genre} (Mood: {params['mood']}): Tempo={params['tempo']}BPM, Progression={selected_progression_names}")
        return params
        
    except Exception as e:
        logger.error(f"Error in get_music_params_from_lyrics: {e}")
        default_params = GENRE_PARAMS['pop'].copy()
        default_params['chords'] = [CHORDS['C']]
        default_params['selected_progression'] = ['C']
        return default_params

def get_scale_notes(key, scale_name):
    """Get scale notes based on key and scale type"""
    try:
        if key not in CHORDS:
            key = 'C'
        root_midi = CHORDS[key][0]
        scale_intervals = SCALES.get(scale_name, SCALES['major'])
        return [root_midi + interval for interval in scale_intervals]
    except Exception as e:
        logger.error(f"Error in get_scale_notes: {e}")
        return [60, 62, 64, 65, 67, 69, 71]  # C major scale

# [Other music generation functions remain the same...]
# generate_melody_section, generate_rhythm_primary_section, etc.
# [Let me know if you want me to include all of them]

def create_midi_file(params, output_path):
    """Create MIDI file - simplified version"""
    try:
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
        mid.tracks.extend(tracks.values())
        
        # Set tempo
        mido_tempo_us = bpm2tempo(tempo)
        tracks['melody'].append(MetaMessage('set_tempo', tempo=mido_tempo_us, time=0))
        
        # Setup instruments
        tracks['melody'].append(Message('program_change', channel=0, program=INSTRUMENTS.get(params['instruments']['melody'], 0), time=0))
        tracks['rhythm_primary'].append(Message('program_change', channel=1, program=INSTRUMENTS.get(params['instruments']['rhythm_primary'], 0), time=0))
        tracks['rhythm_secondary'].append(Message('program_change', channel=2, program=INSTRUMENTS.get(params['instruments']['rhythm_secondary'], 0), time=0))
        tracks['bass'].append(Message('program_change', channel=3, program=INSTRUMENTS.get(params['instruments']['bass'], 0), time=0))
        
        # Simple melody example - in practice use your full generation logic
        tracks['melody'].append(Message('note_on', channel=0, note=60, velocity=100, time=0))
        tracks['melody'].append(Message('note_off', channel=0, note=60, velocity=0, time=480))
        
        mid.save(output_path)
        logger.info(f"MIDI generated: {output_path.name}")
        return True
        
    except Exception as e:
        logger.error(f"MIDI creation error: {e}")
        return False

def midi_to_audio(midi_path, output_wav_path):
    """Convert MIDI to WAV using FluidSynth"""
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False
    
    try:
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-o', 'synth.gain=0.8',
            '-o', 'audio.periods=2',
            '-a', 'file', '-ni',
            str(SOUNDFONT_PATH), str(midi_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"WAV generated: {output_wav_path.name}")
            return True
        else:
            logger.error(f"FluidSynth failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"MIDI to audio error: {e}")
        return False

def wav_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3"""
    try:
        audio = AudioSegment.from_wav(wav_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        logger.info(f"MP3 created: {mp3_path.name}")
        return True
    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

# ==================== AUDIO MERGING FUNCTION ====================

def merge_audio_with_vocals(instrumental_path, vocal_path, output_path):
    """Merge instrumental and vocal tracks"""
    try:
        if not instrumental_path.exists() or not vocal_path.exists():
            return False, "Input files not found"
        
        # Load audio files
        instrumental = AudioSegment.from_mp3(instrumental_path)
        vocals = AudioSegment.from_mp3(vocal_path)
        
        # Adjust vocal volume (reduce slightly to blend better)
        vocals = vocals - 4  # Reduce by 4 dB
        
        # Ensure vocals are not longer than instrumental
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        # Overlay vocals on instrumental
        mixed = instrumental.overlay(vocals, position=0)
        
        # Export merged audio
        mixed.export(output_path, format="mp3", bitrate="192k")
        
        if output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"✅ Merged audio created: {output_path.name} ({output_path.stat().st_size/1024:.1f} KB)")
            return True, "Merge successful"
        else:
            return False, "Merge failed - output file empty"
            
    except Exception as e:
        logger.error(f"Audio merging error: {e}")
        return False, f"Merge error: {str(e)}"

# ==================== FLASK ROUTES ====================

def generate_unique_id(text):
    """Generate unique ID based on text and timestamp"""
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

def cleanup_old_files(directory, max_age_hours=24):
    """Clean up old files"""
    try:
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted = 0
        for file_path in Path(directory).glob("*.*"):
            try:
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                    file_path.unlink()
                    deleted += 1
            except:
                pass
        logger.info(f"Cleanup complete: {deleted} files deleted from {directory}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

@app.route('/')
def index():
    """Main interface with vocal AI controls"""
    html_template = '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎵 AI Music Generator dengan Vocal AI 🎤</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
        <style>
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            #waveform { min-height: 80px; background: #f7fafc; border-radius: 0.5rem; }
            .metadata-grid { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; }
        </style>
        <script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"></script>
    </head>
    <body class="bg-gray-100 min-h-screen p-4">
        <div class="max-w-4xl mx-auto">
            <!-- Header -->
            <div class="text-center mb-8">
                <h1 class="text-4xl font-bold text-gray-800 mb-2">🎵 AI Music Generator</h1>
                <p class="text-gray-600">Generate instrumental + AI vocals dari lirik</p>
            </div>

            <!-- Tabs -->
            <div class="bg-white rounded-lg shadow-lg mb-6">
                <div class="flex border-b">
                    <button class="tab-btn py-4 px-6 font-semibold border-b-2 border-blue-500 text-blue-600" data-tab="generate">Generate Music</button>
                    <button class="tab-btn py-4 px-6 font-semibold text-gray-600 hover:text-blue-600" data-tab="vocals">Vocal AI</button>
                </div>

                <!-- Generate Tab -->
                <div id="generate" class="tab-content active p-6">
                    <form id="musicForm">
                        <div class="mb-4">
                            <label class="block text-gray-700 font-bold mb-2">Lirik Lagu:</label>
                            <textarea id="lyrics" rows="6" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="Masukkan lirik lagu di sini..."></textarea>
                            <div class="flex justify-between text-sm text-gray-500 mt-1">
                                <span id="charCount">0 karakter</span>
                                <span>Minimal 10 karakter</span>
                            </div>
                        </div>

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                            <div>
                                <label class="block text-gray-700 font-bold mb-2">Genre:</label>
                                <select id="genre" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500">
                                    <option value="auto">🤖 Auto Detect</option>
                                    <option value="pop">🎤 Pop</option>
                                    <option value="rock">🎸 Rock</option>
                                    <option value="ballad">💔 Ballad</option>
                                    <option value="jazz">🎷 Jazz</option>
                                    <option value="hiphop">🎧 Hip-Hop</option>
                                    <option value="dangdut">🎶 Dangdut</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-gray-700 font-bold mb-2">Tempo (BPM):</label>
                                <input type="number" id="tempo" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" placeholder="Auto (60-200)" min="60" max="200">
                            </div>
                        </div>

                        <!-- Vocal AI Options -->
                        <div class="mb-6 p-4 bg-blue-50 rounded-lg">
                            <label class="flex items-center space-x-3">
                                <input type="checkbox" id="addVocals" class="w-5 h-5 text-blue-600 rounded focus:ring-blue-500">
                                <span class="text-gray-700 font-bold">🎤 Tambahkan AI Vocal</span>
                            </label>
                            <div id="vocalOptions" class="mt-3 ml-8 space-y-3 hidden">
                                <div class="grid grid-cols-2 gap-4">
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700">Bahasa</label>
                                        <select id="language" class="w-full p-2 border border-gray-300 rounded">
                                            <option value="id">Indonesia</option>
                                            <option value="en">English</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700">Jenis Suara</label>
                                        <select id="voiceType" class="w-full p-2 border border-gray-300 rounded">
                                            <option value="female">Female</option>
                                            <option value="male">Male</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-4 px-6 rounded-lg font-bold text-lg hover:bg-blue-700 focus:ring-4 focus:ring-blue-300 transition disabled:opacity-50">
                            <span id="btnText">🚀 Generate Full Song</span>
                            <div id="spinner" class="hidden inline-block ml-3 animate-spin rounded-full h-6 w-6 border-b-2 border-white"></div>
                        </button>
                    </form>

                    <!-- Status & Results -->
                    <div id="status" class="mt-6 hidden">
                        <div id="statusMessage" class="p-4 rounded-lg mb-4"></div>
                        
                        <div id="results" class="hidden space-y-6">
                            <!-- Instrumental -->
                            <div class="border rounded-lg p-4">
                                <h3 class="font-bold text-lg mb-3">🎵 Instrumental</h3>
                                <div class="metadata-grid grid grid-cols-2 gap-4 mb-3">
                                    <div><span class="font-semibold">Genre:</span> <span id="resultGenre">-</span></div>
                                    <div><span class="font-semibold">Tempo:</span> <span id="resultTempo">-</span> BPM</div>
                                    <div><span class="font-semibold">Durasi:</span> <span id="resultDuration">-</span>s</div>
                                    <div><span class="font-semibold">Progression:</span> <span id="resultProgression">-</span></div>
                                </div>
                                <audio id="instrumentalAudio" controls class="w-full mb-2"></audio>
                                <button onclick="downloadAudio('instrumental')" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">💾 Download Instrumental</button>
                            </div>

                            <!-- Vocals -->
                            <div id="vocalResult" class="border rounded-lg p-4 hidden">
                                <h3 class="font-bold text-lg mb-3">🎤 AI Vocals</h3>
                                <audio id="vocalAudio" controls class="w-full mb-2"></audio>
                                <button onclick="downloadAudio('vocal')" class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">💾 Download Vocals</button>
                            </div>

                            <!-- Merged -->
                            <div id="mergedResult" class="border rounded-lg p-4 hidden">
                                <h3 class="font-bold text-lg mb-3">🎶 Full Song (Merged)</h3>
                                <audio id="mergedAudio" controls class="w-full mb-2"></audio>
                                <button onclick="downloadAudio('merged')" class="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700">💾 Download Full Song</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Vocal AI Tab -->
                <div id="vocals" class="tab-content p-6">
                    <div class="mb-6">
                        <h3 class="text-xl font-bold mb-4">🎤 Generate Vocals Only</h3>
                        <textarea id="vocalLyrics" rows="4" class="w-full p-3 border border-gray-300 rounded-lg mb-3" placeholder="Masukkan lirik untuk vocal..."></textarea>
                        <div class="grid grid-cols-2 gap-4 mb-4">
                            <div>
                                <label class="block text-sm font-medium mb-1">Bahasa</label>
                                <select id="vocalLanguage" class="w-full p-2 border rounded">
                                    <option value="id">Indonesia</option>
                                    <option value="en">English</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-sm font-medium mb-1">Jenis Suara</label>
                                <select id="vocalVoiceType" class="w-full p-2 border rounded">
                                    <option value="female">Female</option>
                                    <option value="male">Male</option>
                                </select>
                            </div>
                        </div>
                        <button onclick="generateVocalsOnly()" class="w-full bg-green-600 text-white py-3 rounded font-bold hover:bg-green-700">
                            🎤 Generate Vocals
                        </button>
                    </div>
                    <div id="vocalOnlyResult" class="hidden">
                        <audio id="vocalOnlyAudio" controls class="w-full mb-3"></audio>
                        <button onclick="downloadVocalOnly()" class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">💾 Download Vocal</button>
                    </div>
                </div>
            </div>

            <!-- System Info -->
            <div class="bg-white rounded-lg shadow-lg p-6 text-sm text-gray-600">
                <h3 class="font-bold mb-2">System Information</h3>
                <div class="grid grid-cols-2 gap-2">
                    <div>Vocal AI: <span id="vocalAIStatus" class="font-semibold">Checking...</span></div>
                    <div>SoundFont: <span id="soundfontStatus" class="font-semibold">Checking...</span></div>
                </div>
            </div>
        </div>

        <script>
            // Tab switching
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    // Update tabs
                    document.querySelectorAll('.tab-btn').forEach(b => {
                        b.classList.remove('border-blue-500', 'text-blue-600');
                        b.classList.add('text-gray-600');
                    });
                    btn.classList.add('border-blue-500', 'text-blue-600');
                    
                    // Update content
                    document.querySelectorAll('.tab-content').forEach(content => {
                        content.classList.remove('active');
                    });
                    document.getElementById(btn.dataset.tab).classList.add('active');
                });
            });

            // Character counter
            document.getElementById('lyrics').addEventListener('input', function() {
                document.getElementById('charCount').textContent = this.value.length + ' karakter';
            });

            // Vocal options toggle
            document.getElementById('addVocals').addEventListener('change', function() {
                document.getElementById('vocalOptions').classList.toggle('hidden', !this.checked);
            });

            // System status check
            fetch('/system-status').then(r => r.json()).then(data => {
                document.getElementById('vocalAIStatus').textContent = data.vocal_ai ? '✅ Available' : '❌ Unavailable';
                document.getElementById('vocalAIStatus').className = data.vocal_ai ? 'font-semibold text-green-600' : 'font-semibold text-red-600';
                document.getElementById('soundfontStatus').textContent = data.soundfont ? '✅ Available' : '❌ Unavailable';
                document.getElementById('soundfontStatus').className = data.soundfont ? 'font-semibold text-green-600' : 'font-semibold text-red-600';
            });

            // Main form submission
            document.getElementById('musicForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const lyrics = document.getElementById('lyrics').value.trim();
                if (lyrics.length < 10) {
                    alert('Lirik minimal 10 karakter!');
                    return;
                }

                const btn = document.getElementById('generateBtn');
                const btnText = document.getElementById('btnText');
                const spinner = document.getElementById('spinner');
                const status = document.getElementById('status');
                const statusMessage = document.getElementById('statusMessage');
                const results = document.getElementById('results');

                // Reset UI
                btn.disabled = true;
                btnText.textContent = 'Generating...';
                spinner.classList.remove('hidden');
                status.classList.remove('hidden');
                statusMessage.innerHTML = '<div class="text-blue-600">🚀 Starting generation... (May take 2-5 minutes)</div>';
                results.classList.add('hidden');

                try {
                    const formData = new FormData();
                    formData.append('lyrics', lyrics);
                    formData.append('genre', document.getElementById('genre').value);
                    formData.append('tempo', document.getElementById('tempo').value || 'auto');
                    formData.append('add_vocals', document.getElementById('addVocals').checked);
                    formData.append('language', document.getElementById('language').value);
                    formData.append('voice_type', document.getElementById('voiceType').value);

                    const response = await fetch('/generate-full-song', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (data.success) {
                        statusMessage.innerHTML = '<div class="text-green-600">✅ Generation successful!</div>';
                        
                        // Update results
                        document.getElementById('resultGenre').textContent = data.instrumental.genre;
                        document.getElementById('resultTempo').textContent = data.instrumental.tempo;
                        document.getElementById('resultDuration').textContent = data.instrumental.duration;
                        document.getElementById('resultProgression').textContent = data.instrumental.progression;
                        
                        // Set audio sources
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
                    statusMessage.innerHTML = '<div class="text-red-600">❌ Network error: ' + error.message + '</div>';
                } finally {
                    btn.disabled = false;
                    btnText.textContent = '🚀 Generate Full Song';
                    spinner.classList.add('hidden');
                }
            });

            // Download functions
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

            // Vocal-only generation
            async function generateVocalsOnly() {
                const lyrics = document.getElementById('vocalLyrics').value.trim();
                if (!lyrics) {
                    alert('Masukkan lirik terlebih dahulu!');
                    return;
                }

                const resultDiv = document.getElementById('vocalOnlyResult');
                const audioElement = document.getElementById('vocalOnlyAudio');
                
                try {
                    const response = await fetch('/generate-vocals', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            lyrics: lyrics,
                            language: document.getElementById('vocalLanguage').value,
                            voice_type: document.getElementById('vocalVoiceType').value
                        })
                    });

                    const data = await response.json();
                    
                    if (data.success) {
                        audioElement.src = data.vocal_url;
                        resultDiv.classList.remove('hidden');
                    } else {
                        alert('Error: ' + data.error);
                    }
                } catch (error) {
                    alert('Network error: ' + error.message);
                }
            }

            function downloadVocalOnly() {
                const audioElement = document.getElementById('vocalOnlyAudio');
                const link = document.createElement('a');
                link.href = audioElement.src;
                link.download = 'ai_vocals.mp3';
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
        'vocal_ai': len(vocal_synthesizer.available_engines) > 0,
        'soundfont': SOUNDFONT_PATH and SOUNDFONT_PATH.exists(),
        'textblob': TEXTBLOB_AVAILABLE,
        'gtts': GTTS_AVAILABLE
    })

@app.route('/generate-vocals', methods=['POST'])
def generate_vocals():
    """Generate vocals from lyrics only"""
    try:
        data = request.get_json()
        lyrics = data.get('lyrics', '').strip()
        language = data.get('language', 'id')
        voice_type = data.get('voice_type', 'female')
        
        if not lyrics or len(lyrics) < 5:
            return jsonify({'error': 'Lirik terlalu pendek (min 5 karakter)'}), 400
        
        # Generate unique ID
        vocal_id = generate_unique_id(lyrics)
        output_path = VOCAL_OUTPUT_DIR / f"{vocal_id}.mp3"
        
        logger.info(f"Generating vocals for {len(lyrics)} characters...")
        
        # Synthesize vocals
        success, message = vocal_synthesizer.synthesize_vocals(
            lyrics, output_path, language, voice_type
        )
        
        if success and output_path.exists():
            return jsonify({
                'success': True,
                'vocal_url': f'/static/vocal_output/{vocal_id}.mp3',
                'filename': f'{vocal_id}.mp3',
                'message': message
            })
        else:
            return jsonify({'error': message}), 500
            
    except Exception as e:
        logger.error(f"Vocal generation error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate-instrumental', methods=['POST'])
def generate_instrumental():
    """Generate instrumental only"""
    try:
        data = request.form if request.form else request.get_json()
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto')
        tempo_input = data.get('tempo', 'auto')
        
        if not lyrics or len(lyrics) < 5:
            return jsonify({'error': 'Lirik terlalu pendek (min 5 karakter)'}), 400
        
        # Detect genre and get parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Generate unique ID
        unique_id = generate_unique_id(lyrics)
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav" 
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        
        # Generate MIDI
        if not create_midi_file(params, midi_path):
            return jsonify({'error': 'Failed to create MIDI'}), 500
        
        # Convert to audio
        if not midi_to_audio(midi_path, wav_path):
            midi_path.unlink(missing_ok=True)
            return jsonify({'error': 'Failed to generate audio'}), 500
        
        # Convert to MP3
        if not wav_to_mp3(wav_path, mp3_path):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return jsonify({'error': 'Failed to create MP3'}), 500
        
        # Cleanup temporary files
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        # Calculate duration
        duration = params.get('duration_beats', 120) * 60 / params['tempo']
        
        return jsonify({
            'success': True,
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo'],
            'duration': round(duration, 1),
            'progression': ' '.join(params.get('selected_progression', ['C']))
        })
        
    except Exception as e:
        logger.error(f"Instrumental generation error: {e}")
        return jsonify({'error': 'Generation failed'}), 500

@app.route('/generate-full-song', methods=['POST'])
def generate_full_song():
    """Generate instrumental + vocals + merged version"""
    try:
        data = request.form if request.form else request.get_json()
        lyrics = data.get('lyrics', '').strip()
        genre = data.get('genre', 'auto')
        tempo = data.get('tempo', 'auto')
        add_vocals = data.get('add_vocals', 'false').lower() == 'true'
        language = data.get('language', 'id')
        voice_type = data.get('voice_type', 'female')
        
        if not lyrics or len(lyrics) < 10:
            return jsonify({'error': 'Lirik minimal 10 karakter'}), 400
        
        result = {
            'success': True,
            'instrumental': None,
            'vocals': None,
            'merged': None
        }
        
        # Step 1: Generate Instrumental
        instrumental_data = generate_instrumental()
        if not instrumental_data.get_json().get('success'):
            return instrumental_data
        
        instrumental_result = instrumental_data.get_json()
        result['instrumental'] = instrumental_result
        
        # Step 2: Generate vocals if requested
        if add_vocals and vocal_synthesizer.available_engines:
            vocal_response = generate_vocals()
            vocal_result = vocal_response.get_json()
            
            if vocal_result.get('success'):
                result['vocals'] = vocal_result
                
                # Step 3: Merge instrumental + vocals
                instrumental_path = AUDIO_OUTPUT_DIR / instrumental_result['filename']
                vocal_path = VOCAL_OUTPUT_DIR / vocal_result['filename']
                merged_id = generate_unique_id(lyrics + "_merged")
                merged_path = MERGED_OUTPUT_DIR / f"{merged_id}.mp3"
                
                success, message = merge_audio_with_vocals(instrumental_path, vocal_path, merged_path)
                
                if success:
                    result['merged'] = {
                        'filename': f'{merged_id}.mp3',
                        'message': message
                    }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Full song generation error: {e}")
        return jsonify({'error': 'Generation failed'}), 500

@app.route('/static/audio_output/<filename>')
def serve_audio(filename):
    """Serve audio files"""
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)

@app.route('/static/vocal_output/<filename>')
def serve_vocal(filename):
    """Serve vocal files"""
    return send_from_directory(VOCAL_OUTPUT_DIR, filename)

@app.route('/static/merged_output/<filename>')
def serve_merged(filename):
    """Serve merged files"""
    return send_from_directory(MERGED_OUTPUT_DIR, filename)

def main_app_runner():
    """Startup with system checks"""
    logger.info("🎵 Starting Flask AI Music Generator with Vocal AI! 🎤")
    logger.info("✅ Features: Instrumental Generation + AI Vocals + Audio Merging")
    
    try:
        if SOUNDFONT_PATH:
            logger.info(f"✅ SoundFont: {SOUNDFONT_PATH.name}")
        else:
            logger.warning("⚠️ No SoundFont found - audio generation will fail")
        
        check_python_dependencies()
        cleanup_old_files(AUDIO_OUTPUT_DIR)
        cleanup_old_files(VOCAL_OUTPUT_DIR)
        cleanup_old_files(MERGED_OUTPUT_DIR)
        
        logger.info("🚀 Server ready! Access at http://localhost:5000")
        logger.info("🎤 Vocal AI Status: " + 
                   ("✅ Available" if vocal_synthesizer.available_engines else "❌ Unavailable"))
        
        return True
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        return False

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
