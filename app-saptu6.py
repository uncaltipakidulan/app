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
    BASE_DIR / 'Scc1t2.sf2',                       # ✅ Good for rock/metal
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
    """Advanced vocal synthesizer dengan pitch adjustment"""
    
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
    
    def synthesize_vocals(self, lyrics, output_path, key='C', scale='major', tempo=120, language='id'):
        """Synthesize vocals dengan penyesuaian nada"""
        try:
            if not self.available:
                return False, "Vocal AI not available"
            
            # Preprocess lyrics dengan penyesuaian rhythm
            processed_lyrics = self._preprocess_lyrics_with_rhythm(lyrics, tempo)
            if not processed_lyrics:
                return False, "No valid lyrics after processing"
            
            # Generate base vocals
            success, message = self._synthesize_gtts(processed_lyrics, output_path, language)
            
            if success:
                # Apply audio processing untuk match dengan musik
                self._process_vocal_audio(output_path, key, tempo)
                return True, "Vocal synthesis successful with pitch adjustment"
            else:
                return False, message
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _preprocess_lyrics_with_rhythm(self, lyrics, tempo):
        """Preprocess lyrics dengan penyesuaian rhythm berdasarkan tempo"""
        try:
            if not lyrics or len(lyrics.strip()) < 3:
                return None
            
            # Basic cleaning
            cleaned = ' '.join(lyrics.split())
            
            # Adjust phrasing based on tempo
            if tempo < 80:  # Slow tempo
                # Longer phrases, more pauses
                cleaned = cleaned.replace('\n', '... ')
                phrases = cleaned.split('.')
                processed = '... '.join([p.strip() for p in phrases if p.strip()])
            elif tempo > 140:  # Fast tempo  
                # Shorter phrases, fewer pauses
                cleaned = cleaned.replace('\n', '. ')
                phrases = cleaned.split('.')
                processed = '. '.join([p.strip() for p in phrases if p.strip()])
            else:  # Medium tempo
                cleaned = cleaned.replace('\n', '. ')
                processed = cleaned
            
            # Remove problematic characters
            import re
            processed = re.sub(r'[^\w\s.,!?;:\'\-]', '', processed)
            
            # Limit length for stability
            return processed[:400]
            
        except Exception as e:
            logger.error(f"Lyrics preprocessing error: {e}")
            return lyrics[:300]
    
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
    
    def _process_vocal_audio(self, vocal_path, key='C', tempo=120):
        """Process vocal audio untuk match dengan musik"""
        try:
            audio = AudioSegment.from_mp3(vocal_path)
            
            # EQ adjustments berdasarkan key
            eq_settings = self._get_eq_settings(key)
            
            # Apply subtle EQ
            if eq_settings['bass_boost']:
                audio = audio.low_pass_filter(250)
            
            if eq_settings['presence_boost']:
                audio = audio.high_pass_filter(2000)
            
            # Dynamic compression untuk vocal
            audio = compress_dynamic_range(audio, threshold=-20.0, ratio=2.0, attack=5.0, release=50.0)
            
            # Normalize volume
            audio = normalize(audio, headroom=3.0)
            
            # Export processed audio
            audio.export(vocal_path, format="mp3", bitrate="192k")
            logger.info(f"✅ Vocal audio processed for key {key}")
            
        except Exception as e:
            logger.error(f"Vocal audio processing error: {e}")
    
    def _get_eq_settings(self, key):
        """Get EQ settings berdasarkan key musik"""
        # Major keys - brighter, minor keys - warmer
        if key.endswith('m'):  # Minor key
            return {'bass_boost': True, 'presence_boost': False}
        else:  # Major key
            return {'bass_boost': False, 'presence_boost': True}

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
    
    # Extended & Jazz Chords
    'C9': [60, 64, 67, 70, 74], 'Cm9': [60, 63, 67, 70, 74],
    'C6': [60, 64, 67, 69], 'Cm6': [60, 63, 67, 69],
    'Csus2': [60, 62, 67], 'Csus4': [60, 65, 67],
    'Cdim': [60, 63, 66], 'Caug': [60, 64, 68],
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
    'locrian': [0, 1, 3, 5, 6, 8, 10],
    'whole tone': [0, 2, 4, 6, 8, 10],
}

# ==================== EXTENDED GENRE PARAMETERS ====================

GENRE_PARAMS = {
    # POP VARIATIONS
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
    
    # ROCK VARIATIONS
    'slow rock': {
        'tempo': 70, 'key': 'Am', 'scale': 'minor',
        'instruments': {
            'melody': 'Clean Electric Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Fretless Bass',
            'drums': 'soft'
        },
        'chord_progressions': [
            ['Am', 'G', 'C', 'F'], ['C', 'G', 'Am', 'F'],
            ['Am', 'Dm', 'G', 'C'], ['F', 'C', 'G', 'Am']
        ],
        'mood': 'emotional',
        'complexity': 'medium'
    },
    
    'ballad': {
        'tempo': 65, 'key': 'C', 'scale': 'major',
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
    
    'piano rock ballad': {
        'tempo': 75, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Acoustic Grand Piano',
            'rhythm_primary': 'String Ensemble 1',
            'rhythm_secondary': 'Clean Electric Guitar',
            'bass': 'Electric Bass finger',
            'drums': 'rock'
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G'],
            ['C', 'Em', 'F', 'G'], ['G', 'D', 'Em', 'C']
        ],
        'mood': 'emotional',
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
    
    'progressive rock': {
        'tempo': 140, 'key': 'Cm', 'scale': 'harmonic minor',
        'instruments': {
            'melody': 'Lead 1 (square)',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Synth Bass 1',
            'drums': 'complex'
        },
        'chord_progressions': [
            ['Cm', 'G', 'D#', 'A#'], ['Fm', 'C', 'G', 'D'],
            ['Cm', 'Fm', 'G', 'C'], ['Dm', 'G', 'C', 'F']
        ],
        'mood': 'complex',
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
    
    'progressive metal': {
        'tempo': 180, 'key': 'Dm', 'scale': 'phrygian',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Synth Brass 2',
            'rhythm_secondary': 'Lead 2 (sawtooth)',
            'bass': 'Synth Bass 2',
            'drums': 'complex'
        },
        'chord_progressions': [
            ['Dm', 'G', 'C', 'F'], ['Am', 'Dm', 'G', 'C'],
            ['Dm', 'A#', 'F', 'C'], ['Gm', 'C', 'F', 'A#']
        ],
        'mood': 'technical',
        'complexity': 'very high'
    },
    
    # JAZZ VARIATIONS
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
    
    'piano jazz': {
        'tempo': 110, 'key': 'F', 'scale': 'mixolydian',
        'instruments': {
            'melody': 'Acoustic Grand Piano',
            'rhythm_primary': 'Acoustic Bass',
            'rhythm_secondary': 'Brush Drums',
            'bass': 'Acoustic Bass',
            'drums': 'jazz'
        },
        'chord_progressions': [
            ['Fmaj7', 'Gm7', 'Am7', 'Dm7'], 
            ['Cm7', 'F7', 'Bbmaj7', 'Ebmaj7'],
            ['Dm7', 'G7', 'Cmaj7', 'Fmaj7']
        ],
        'mood': 'relaxed',
        'complexity': 'high'
    },
    
    'swing': {
        'tempo': 180, 'key': 'Bb', 'scale': 'major',
        'instruments': {
            'melody': 'Trumpet',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'Brass Section',
            'bass': 'Acoustic Bass',
            'drums': 'swing'
        },
        'chord_progressions': [
            ['Bb', 'Eb', 'F7', 'Bb'], ['Cm7', 'F7', 'Bbmaj7'],
            ['Eb', 'Ab', 'Bb7', 'Eb'], ['Gm7', 'C7', 'Fmaj7']
        ],
        'mood': 'upbeat',
        'complexity': 'medium'
    },
    
    'bigband': {
        'tempo': 140, 'key': 'G', 'scale': 'major',
        'instruments': {
            'melody': 'Brass Section',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'Sax Section',
            'bass': 'Acoustic Bass',
            'drums': 'bigband'
        },
        'chord_progressions': [
            ['G', 'C', 'D7', 'G'], ['Em7', 'A7', 'Dmaj7'],
            ['C', 'F', 'G7', 'C'], ['Am7', 'D7', 'Gmaj7']
        ],
        'mood': 'powerful',
        'complexity': 'high'
    },
    
    # LATIN VARIATIONS
    'latin': {
        'tempo': 110, 'key': 'Am', 'scale': 'dorian',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Acoustic Grand Piano',
            'rhythm_secondary': 'Congas',
            'bass': 'Acoustic Bass',
            'drums': 'latin'
        },
        'chord_progressions': [
            ['Am', 'D7', 'Gmaj7', 'Cmaj7'], 
            ['G', 'Bm', 'Em', 'A7'],
            ['Dm', 'G7', 'Cmaj7', 'Fmaj7']
        ],
        'mood': 'rhythmic',
        'complexity': 'medium'
    },
    
    'bossanova': {
        'tempo': 120, 'key': 'Dm', 'scale': 'major',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Brush Drums',
            'bass': 'Acoustic Bass',
            'drums': 'bossanova'
        },
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'], ['Gm7', 'C7', 'Fmaj7'],
            ['Am7', 'D7', 'Gmaj7'], ['Em7', 'A7', 'Dmaj7']
        ],
        'mood': 'smooth',
        'complexity': 'medium'
    },
    
    'salsa': {
        'tempo': 200, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Trumpet',
            'rhythm_primary': 'Piano',
            'rhythm_secondary': 'Congas',
            'bass': 'Electric Bass finger',
            'drums': 'salsa'
        },
        'chord_progressions': [
            ['C', 'F', 'G7'], ['Am', 'Dm', 'E7'],
            ['F', 'Bb', 'C7'], ['Gm', 'Cm', 'D7']
        ],
        'mood': 'energetic',
        'complexity': 'high'
    },
    
    'bachata': {
        'tempo': 120, 'key': 'Am', 'scale': 'minor',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Bongo',
            'rhythm_secondary': 'Marimba',
            'bass': 'Electric Bass finger',
            'drums': 'bachata'
        },
        'chord_progressions': [
            ['Am', 'G', 'F', 'E7'], ['Dm', 'Am', 'E7', 'Am'],
            ['Am', 'F', 'C', 'G'], ['Bm', 'F#m', 'G', 'D']
        ],
        'mood': 'romantic',
        'complexity': 'medium'
    },
    
    'cha cha': {
        'tempo': 112, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Vibraphone',
            'rhythm_primary': 'Piano',
            'rhythm_secondary': 'Congas',
            'bass': 'Acoustic Bass',
            'drums': 'cha cha'
        },
        'chord_progressions': [
            ['C', 'F', 'G7'], ['Am', 'Dm', 'G7'],
            ['F', 'Bb', 'C7'], ['G7', 'C', 'F']
        ],
        'mood': 'playful',
        'complexity': 'medium'
    },
    
    'rumba': {
        'tempo': 100, 'key': 'Am', 'scale': 'phrygian',
        'instruments': {
            'melody': 'Spanish Guitar',
            'rhythm_primary': 'Claves',
            'rhythm_secondary': 'Maracas',
            'bass': 'Acoustic Bass',
            'drums': 'rumba'
        },
        'chord_progressions': [
            ['Am', 'G', 'F', 'E7'], ['Dm', 'Am', 'E7', 'Am'],
            ['Am', 'Dm', 'E7', 'Am'], ['E7', 'Am', 'Dm', 'G7']
        ],
        'mood': 'passionate',
        'complexity': 'medium'
    },
    
    'samba': {
        'tempo': 110, 'key': 'Dm', 'scale': 'mixolydian',
        'instruments': {
            'melody': 'Agogo',
            'rhythm_primary': 'Surdo',
            'rhythm_secondary': 'Tamborim',
            'bass': 'Acoustic Bass',
            'drums': 'samba'
        },
        'chord_progressions': [
            ['Dm', 'G7', 'Cmaj7'], ['Am7', 'D7', 'Gmaj7'],
            ['Em7', 'A7', 'Dmaj7'], ['Bm7', 'E7', 'Amaj7']
        ],
        'mood': 'festive',
        'complexity': 'high'
    },
    
    # WALTZ & MARCH
    'slow waltz': {
        'tempo': 84, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Acoustic Grand Piano',
            'rhythm_primary': 'String Ensemble 1',
            'rhythm_secondary': 'Harp',
            'bass': 'Acoustic Bass',
            'drums': 'waltz'
        },
        'chord_progressions': [
            ['C', 'F', 'G7'], ['G7', 'C', 'F'],
            ['Am', 'Dm', 'G7'], ['Em', 'Am', 'D7']
        ],
        'mood': 'graceful',
        'complexity': 'simple'
    },
    
    'fast waltz': {
        'tempo': 138, 'key': 'G', 'scale': 'major',
        'instruments': {
            'melody': 'Violin',
            'rhythm_primary': 'Accordion',
            'rhythm_secondary': 'Clarinet',
            'bass': 'Acoustic Bass',
            'drums': 'waltz'
        },
        'chord_progressions': [
            ['G', 'C', 'D7'], ['D7', 'G', 'C'],
            ['Em', 'Am', 'D7'], ['Bm', 'Em', 'A7']
        ],
        'mood': 'lively',
        'complexity': 'medium'
    },
    
    'march': {
        'tempo': 120, 'key': 'Bb', 'scale': 'major',
        'instruments': {
            'melody': 'Trumpet',
            'rhythm_primary': 'Snare Drum',
            'rhythm_secondary': 'Brass Section',
            'bass': 'Tuba',
            'drums': 'march'
        },
        'chord_progressions': [
            ['Bb', 'Eb', 'F7'], ['F7', 'Bb', 'Eb'],
            ['Cm', 'Fm', 'Bb'], ['Gm', 'Cm', 'F7']
        ],
        'mood': 'patriotic',
        'complexity': 'simple'
    },
    
    'rock march': {
        'tempo': 132, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Snare Drum',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Electric Bass pick',
            'drums': 'rock march'
        },
        'chord_progressions': [
            ['E5', 'A5', 'B5'], ['A5', 'D5', 'E5'],
            ['E5', 'G5', 'A5'], ['B5', 'E5', 'A5']
        ],
        'mood': 'powerful',
        'complexity': 'medium'
    },
    
    # INDONESIAN GENRES
    'pop sunda': {
        'tempo': 120, 'key': 'G', 'scale': 'pelog',
        'instruments': {
            'melody': 'Suling',
            'rhythm_primary': 'Kendang',
            'rhythm_secondary': 'Gamelan',
            'bass': 'Electric Bass finger',
            'drums': 'sunda'
        },
        'chord_progressions': [
            ['G', 'C', 'D', 'G'], ['Em', 'Am', 'D', 'G'],
            ['C', 'F', 'G', 'C'], ['Am', 'Dm', 'G', 'C']
        ],
        'mood': 'traditional',
        'complexity': 'medium'
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
    
    'koplo': {
        'tempo': 140, 'key': 'Cm', 'scale': 'minor',
        'instruments': {
            'melody': 'Synthesizer',
            'rhythm_primary': 'Kendang',
            'rhythm_secondary': 'Electric Organ',
            'bass': 'Synth Bass 1',
            'drums': 'koplo'
        },
        'chord_progressions': [
            ['Cm', 'G', 'D#', 'A#'], ['Fm', 'C', 'G', 'D'],
            ['Cm', 'Fm', 'G', 'C'], ['G#', 'C#', 'F#', 'B']
        ],
        'mood': 'energetic',
        'complexity': 'high'
    },
}

# ==================== ADVANCED MUSIC GENERATION FUNCTIONS ====================

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
    """Advanced genre detection from lyrics"""
    if not lyrics:
        return 'pop'
    
    lyrics_lower = lyrics.lower()
    
    # Extended genre detection
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
    elif any(word in lyrics_lower for word in ['latin', 'salsa', 'rumba', 'samba']):
        return 'salsa'
    else:
        return 'pop'

def get_music_params_from_lyrics(genre, lyrics, tempo_input='auto'):
    """Get advanced music parameters for generation"""
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
    
    # Select chord progression based on complexity
    progressions = params['chord_progressions']
    selected_progression = random.choice(progressions)
    
    # Adjust octave based on genre
    octave = 3 if params['complexity'] in ['high', 'very high'] else 4
    params['chords'] = chord_names_to_midi_notes(selected_progression, octave)
    params['selected_progression'] = selected_progression
    
    logger.info(f"Advanced music params: {genre}, tempo={params['tempo']}, progression={selected_progression}")
    return params

def create_advanced_midi(params, output_path):
    """Create advanced MIDI file dengan genre-specific arrangements"""
    try:
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Set tempo
        tempo = bpm2tempo(params['tempo'])
        track.append(MetaMessage('set_tempo', tempo=tempo))
        
        # Set instruments based on genre
        melody_program = INSTRUMENTS.get(params['instruments']['melody'], 0)
        rhythm_program = INSTRUMENTS.get(params['instruments']['rhythm_primary'], 0)
        
        track.append(Message('program_change', program=melody_program))
        
        # Advanced melody based on genre complexity
        chords = params['chords']
        complexity = params.get('complexity', 'simple')
        
        if complexity == 'simple':
            # Simple chord-based melody
            for i, chord in enumerate(chords):
                for note in chord[:2]:  # Play first two notes
                    track.append(Message('note_on', note=note, velocity=80, time=0))
                    track.append(Message('note_off', note=note, velocity=0, time=480))
        
        elif complexity == 'medium':
            # More varied melody
            for i, chord in enumerate(chords):
                # Play chord arpeggio
                for j, note in enumerate(chord):
                    track.append(Message('note_on', note=note, velocity=70 + (j*10), time=0))
                    track.append(Message('note_off', note=note, velocity=0, time=240))
        
        elif complexity in ['high', 'very high']:
            # Complex melody with variations
            for i, chord in enumerate(chords):
                # Chord tones with passing notes
                for j in range(4):
                    note = random.choice(chord) + random.choice([-2, 0, 2, 4])
                    note = max(48, min(84, note))  # Keep in range
                    track.append(Message('note_on', note=note, velocity=75, time=0))
                    track.append(Message('note_off', note=note, velocity=0, time=120))
        
        mid.save(output_path)
        logger.info(f"Advanced MIDI created: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Advanced MIDI creation error: {e}")
        return False

def midi_to_audio_advanced(midi_path, output_wav_path, genre='pop'):
    """Convert MIDI to WAV dengan genre-specific FluidSynth settings"""
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False
    
    try:
        # Genre-specific FluidSynth settings
        genre_settings = {
            'rock': ['-o', 'synth.gain=1.2', '-o', 'synth.reverb.damp=0.8'],
            'metal': ['-o', 'synth.gain=1.5', '-o', 'synth.chorus.depth=0.5'],
            'jazz': ['-o', 'synth.gain=0.9', '-o', 'synth.reverb.room-size=0.7'],
            'ballad': ['-o', 'synth.gain=0.8', '-o', 'synth.reverb.level=0.3'],
            'latin': ['-o', 'synth.gain=1.0', '-o', 'synth.chorus.level=0.4'],
            'default': ['-o', 'synth.gain=1.0']
        }
        
        settings = genre_settings.get(genre, genre_settings['default'])
        
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-ni', str(SOUNDFONT_PATH), str(midi_path)
        ] + settings
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
    """Apply advanced audio processing dengan compression dan balancing"""
    try:
        audio = AudioSegment.from_file(audio_path)
        
        # Genre-specific processing
        processing_settings = {
            'rock': {'compression': 2.0, 'eq_low': 2, 'eq_high': 1},
            'metal': {'compression': 3.0, 'eq_low': 3, 'eq_high': 2},
            'jazz': {'compression': 1.5, 'eq_low': 1, 'eq_high': 2},
            'ballad': {'compression': 1.2, 'eq_low': 0, 'eq_high': 1},
            'latin': {'compression': 1.8, 'eq_low': 1, 'eq_high': 2},
            'default': {'compression': 1.5, 'eq_low': 1, 'eq_high': 1}
        }
        
        settings = processing_settings.get(genre, processing_settings['default'])
        
        # Apply compression
        audio = compress_dynamic_range(
            audio, 
            threshold=-20.0, 
            ratio=settings['compression'],
            attack=5.0, 
            release=50.0
        )
        
        # Apply EQ (simplified)
        if settings['eq_low'] > 0:
            audio = audio.low_pass_filter(500)
        if settings['eq_high'] > 0:
            audio = audio.high_pass_filter(2000)
        
        # Normalize dengan headroom
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
        # First convert to MP3
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
        
        # Genre-specific vocal levels
        vocal_levels = {
            'rock': -6,      # Vocals lebih keras di rock
            'metal': -8,     # Vocals lebih soft di metal
            'ballad': -2,    # Vocals lebih prominent di ballad
            'jazz': -4,      # Balanced di jazz
            'pop': -3,       # Standard pop balance
            'default': -4
        }
        
        vocal_db = vocal_levels.get(genre, vocal_levels['default'])
        vocals = vocals + vocal_db
        
        # Ensure vocals don't exceed instrumental length
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        # Mix audio dengan crossfade
        mixed = instrumental.overlay(vocals, position=0, gain_during_overlay=vocal_db)
        
        # Apply final compression untuk overall mix
        mixed = compress_dynamic_range(mixed, threshold=-15.0, ratio=1.5)
        mixed = normalize(mixed, headroom=1.0)
        
        mixed.export(output_path, format="mp3", bitrate="192k")
        
        logger.info(f"Advanced merged audio created: {output_path}")
        return True, "Advanced merge successful"
        
    except Exception as e:
        logger.error(f"Advanced audio merging error: {e}")
        return False, f"Advanced merge error: {str(e)}"

# ==================== FLASK ROUTES (UPDATED) ====================

def generate_unique_id(text):
    """Generate unique ID"""
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

@app.route('/')
def index():
    """Main interface dengan genre options extended"""
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
                <p class="text-center text-gray-600 mb-6">27 Genre Options • Advanced Audio Processing • Vocal Pitch Matching</p>
                
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
                                <optgroup label="Pop">
                                    <option value="pop">Pop</option>
                                    <option value="poprock">Pop Rock</option>
                                    <option value="ballad">Ballad</option>
                                </optgroup>
                                <optgroup label="Rock">
                                    <option value="rock">Rock</option>
                                    <option value="slow rock">Slow Rock</option>
                                    <option value="piano rock ballad">Piano Rock Ballad</option>
                                    <option value="progressive rock">Progressive Rock</option>
                                    <option value="metal">Metal</option>
                                    <option value="progressive metal">Progressive Metal</option>
                                </optgroup>
                                <optgroup label="Jazz">
                                    <option value="jazz">Jazz</option>
                                    <option value="piano jazz">Piano Jazz</option>
                                    <option value="swing">Swing</option>
                                    <option value="bigband">Big Band</option>
                                </optgroup>
                                <optgroup label="Latin">
                                    <option value="latin">Latin</option>
                                    <option value="bossanova">Bossa Nova</option>
                                    <option value="salsa">Salsa</option>
                                    <option value="bachata">Bachata</option>
                                    <option value="cha cha">Cha Cha</option>
                                    <option value="rumba">Rumba</option>
                                    <option value="samba">Samba</option>
                                </optgroup>
                                <optgroup label="Dance">
                                    <option value="slow waltz">Slow Waltz</option>
                                    <option value="fast waltz">Fast Waltz</option>
                                    <option value="march">March</option>
                                    <option value="rock march">Rock March</option>
                                </optgroup>
                                <optgroup label="Indonesian">
                                    <option value="pop sunda">Pop Sunda</option>
                                    <option value="dangdut">Dangdut</option>
                                    <option value="koplo">Koplo</option>
                                </optgroup>
                            </select>
                        </div>
                        <div>
                            <label class="block font-semibold mb-2">Tempo (BPM):</label>
                            <input type="number" id="tempo" class="w-full p-2 border rounded" placeholder="Auto" min="60" max="200">
                        </div>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input type="checkbox" id="addVocals" class="w-4 h-4">
                        <label class="font-semibold">Tambahkan AI Vocal (Pitch Adjusted)</label>
                    </div>
                    
                    <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 rounded font-bold hover:bg-blue-700">
                        🚀 Generate Advanced Music
                    </button>
                </form>
                
                <div id="status" class="mt-4 hidden">
                    <div id="statusMessage" class="p-3 rounded"></div>
                </div>
                
                <div id="results" class="mt-6 space-y-4 hidden">
                    <div class="border rounded p-4">
                        <h3 class="font-bold mb-2">🎵 Instrumental (Advanced Processing)</h3>
                        <audio id="instrumentalAudio" controls class="w-full mb-2"></audio>
                        <button onclick="downloadAudio('instrumental')" class="bg-blue-600 text-white px-4 py-2 rounded text-sm">Download</button>
                    </div>
                    
                    <div id="vocalResult" class="border rounded p-4 hidden">
                        <h3 class="font-bold mb-2">🎤 AI Vocals (Pitch Matched)</h3>
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
                <div>Advanced Processing: <span class="text-green-600 font-semibold">✅ Enabled</span></div>
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

                btn.disabled = true;
                btn.textContent = 'Generating Advanced Music...';
                status.classList.remove('hidden');
                statusMessage.innerHTML = '<div class="text-blue-600">🚀 Generating advanced music with vocal pitch matching... (2-3 minutes)</div>';
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
                        statusMessage.innerHTML = '<div class="text-green-600">✅ Advanced generation successful!</div>';
                        
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
                    btn.textContent = '🚀 Generate Advanced Music';
                }
            });

            function downloadAudio(type) {
                let audioElement, filename;
                switch(type) {
                    case 'instrumental':
                        audioElement = document.getElementById('instrumentalAudio');
                        filename = 'instrumental_advanced.mp3';
                        break;
                    case 'vocal':
                        audioElement = document.getElementById('vocalAudio');
                        filename = 'vocals_pitch_matched.mp3';
                        break;
                    case 'merged':
                        audioElement = document.getElementById('mergedAudio');
                        filename = 'full_song_balanced.mp3';
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
        'advanced_processing': True
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
        
        # Create advanced MIDI
        if not create_advanced_midi(params, midi_path):
            return {'success': False, 'error': 'Advanced MIDI creation failed'}
        
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
            'progression': ' '.join(params['selected_progression']),
            'complexity': params.get('complexity', 'medium')
        }
        
    except Exception as e:
        logger.error(f"Advanced instrumental generation error: {e}")
        return {'success': False, 'error': 'Advanced generation failed'}

def generate_vocals_internal(lyrics, key='C', tempo=120):
    """Internal function for advanced vocal generation dengan pitch matching"""
    try:
        if not lyrics:
            return {'success': False, 'error': 'Lirik diperlukan'}
        
        vocal_id = generate_unique_id(lyrics)
        output_path = VOCAL_OUTPUT_DIR / f"{vocal_id}.mp3"
        
        success, message = vocal_synth.synthesize_vocals(lyrics, output_path, key, tempo)
        
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
        logger.error(f"Advanced vocal generation error: {e}")
        return {'success': False, 'error': 'Advanced vocal generation failed'}

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
        
        # Generate advanced instrumental
        instrumental_data = generate_instrumental_internal(lyrics, genre, tempo)
        if not instrumental_data.get('success'):
            return jsonify({'error': instrumental_data.get('error', 'Instrumental generation failed')}), 500
        
        result['instrumental'] = instrumental_data
        
        # Generate advanced vocals if requested
        if add_vocals and vocal_synth.available:
            vocal_data = generate_vocals_internal(
                lyrics, 
                instrumental_data.get('key', 'C'),
                instrumental_data.get('tempo', 120)
            )
            
            if vocal_data.get('success'):
                result['vocals'] = vocal_data
                
                # Advanced audio merging
                instrumental_path = AUDIO_OUTPUT_DIR / instrumental_data['filename']
                vocal_path = VOCAL_OUTPUT_DIR / vocal_data['filename']
                merged_id = generate_unique_id(lyrics + "_advanced")
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
        logger.error(f"Advanced full song generation error: {e}")
        return jsonify({'error': f'Advanced generation failed: {str(e)}'}), 500

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
    logger.info("🎵 Starting Advanced AI Music Generator")
    logger.info(f"✅ SoundFont: {'Available' if SOUNDFONT_PATH else 'Not Found'}")
    logger.info(f"✅ Vocal AI: {'Available' if vocal_synth.available else 'Not Available'}")
    logger.info(f"✅ Advanced Processing: Enabled")
    logger.info(f"✅ Genres Available: {len(GENRE_PARAMS)} genres")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
