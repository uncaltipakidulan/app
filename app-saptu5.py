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
    import requests
    from io import BytesIO
    GTTS_AVAILABLE = True
except ImportError as e:
    GTTS_AVAILABLE = False
    print(f"⚠️  gTTS not available: {e}")

try:
    import torch
    import torchaudio
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# TextBlob untuk sentiment analysis
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

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

# Auto-detect SoundFont
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
    logger.warning("No SoundFont found - audio generation will fail")

# Create directories
for directory in [AUDIO_OUTPUT_DIR, VOCAL_OUTPUT_DIR, MERGED_OUTPUT_DIR]:
    os.makedirs(directory, exist_ok=True)

# ==================== SIMPLE VOCAL SYNTHESIZER ====================

class SimpleVocalSynthesizer:
    """Simple vocal synthesizer dengan fallback options"""
    
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
    
    def synthesize_vocals(self, lyrics, output_path, language='id', voice_type='female'):
        """Synthesize vocals from lyrics"""
        try:
            if not self.available:
                return False, "Vocal AI not available - install gTTs: pip install gtts"
            
            # Preprocess lyrics
            processed_lyrics = self._preprocess_lyrics(lyrics)
            if not processed_lyrics:
                return False, "No valid lyrics after processing"
            
            return self._synthesize_gtts(processed_lyrics, output_path, language)
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _preprocess_lyrics(self, lyrics):
        """Clean and prepare lyrics for TTS"""
        try:
            if not lyrics or len(lyrics.strip()) < 3:
                return None
            
            # Basic cleaning
            cleaned = ' '.join(lyrics.split())
            cleaned = cleaned.replace('\n', '. ')
            
            # Remove problematic characters
            import re
            cleaned = re.sub(r'[^\w\s.,!?;:\'\-]', '', cleaned)
            
            # Limit length for stability
            return cleaned[:300]
            
        except Exception as e:
            logger.error(f"Lyrics preprocessing error: {e}")
            return lyrics[:200]  # Fallback
    
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
                slow=False,
                lang_check=False
            )
            
            # Save to file
            tts.save(str(output_path))
            
            # Verify file was created
            if output_path.exists() and output_path.stat().st_size > 1000:
                logger.info(f"✅ Vocal generated: {output_path.name} ({output_path.stat().st_size/1024:.1f} KB)")
                return True, "Vocal synthesis successful"
            else:
                logger.error("❌ gTTS generated empty file")
                return False, "Generated file is empty"
                
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            return False, f"gTTS error: {str(e)}"

# Initialize Vocal AI
vocal_synth = SimpleVocalSynthesizer()

# ==================== MUSIC GENERATION SETUP ====================

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
    'Violin': 40, 'Viola': 41, 'Cello': 42, 'Contrabass': 43, 'Tremolo Strings': 44,
    'Pizzicato Strings': 45, 'Orchestral Strings': 46, 'String Ensemble 1': 48,
    'String Ensemble 2': 49, 'Synth Strings 1': 50, 'Synth Strings 2': 51,
    'Choir Aahs': 52, 'Voice Oohs': 53, 'Synth Voice': 54, 'Orchestra Hit': 55,
    'Trumpet': 56, 'Trombone': 57, 'Tuba': 58, 'Muted Trumpet': 59, 'French Horn': 60,
    'Brass Section': 61, 'Synth Brass 1': 62, 'Synth Brass 2': 63, 'Soprano Sax': 64,
    'Alto Sax': 65, 'Tenor Sax': 66, 'Baritone Sax': 67, 'Oboe': 68, 'English Horn': 69,
    'Bassoon': 70, 'Clarinet': 71, 'Piccolo': 72, 'Flute': 73, 'Recorder': 74,
    'Pan Flute': 75, 'Blown Bottle': 76, 'Shakuhachi': 77, 'Whistle': 78, 'Ocarina': 79,
    'Square Wave': 80, 'Sawtooth Wave': 81, 'Calliope Lead': 82, 'Chiff Lead': 83,
    'Charang': 84, 'Voice Lead': 85, 'Fifth Saw Wave': 86, 'Bass & Lead': 87,
    'New Age Pad': 88, 'Warm Pad': 89, 'Poly Synth Pad': 90, 'Choir Pad': 91,
    'Bowed Glass Pad': 92, 'Metallic Pad': 93, 'Halo Pad': 94, 'Sweep Pad': 95,
    'Sitar': 104, 'Banjo': 105, 'Shamisen': 106, 'Koto': 107, 'Kalimba': 108,
    'Bagpipe': 109, 'Fiddle': 110, 'Shanai': 111, 'Gamelan': 114, 'Kendang': 115,
    'Suling': 75, 'Rebab': 110, 'Talempong': 14, 'Gambus': 25,
}

# Chords (MIDI note numbers, C4 = 60)
CHORDS = {
    'C': [60, 64, 67], 'C#': [61, 65, 68], 'Db': [61, 65, 68], 'D': [62, 66, 69],
    'D#': [63, 67, 70], 'Eb': [63, 67, 70], 'E': [64, 68, 71], 'F': [65, 69, 72],
    'F#': [66, 70, 73], 'Gb': [66, 70, 73], 'G': [67, 71, 74], 'G#': [68, 72, 75],
    'Ab': [68, 72, 75], 'A': [69, 73, 76], 'A#': [70, 74, 77], 'Bb': [70, 74, 77],
    'B': [71, 75, 78], 'Cm': [60, 63, 67], 'C#m': [61, 64, 68], 'Dm': [62, 65, 69],
    'D#m': [63, 66, 70], 'Em': [64, 67, 71], 'Fm': [65, 68, 72], 'F#m': [66, 69, 73],
    'Gm': [67, 70, 74], 'G#m': [68, 71, 75], 'Am': [69, 72, 76], 'A#m': [70, 73, 77],
    'Bm': [71, 74, 78], 'C7': [60, 64, 67, 70], 'D7': [62, 66, 69, 72],
    'E7': [64, 68, 71, 74], 'F7': [65, 69, 72, 75], 'G7': [67, 71, 74, 77],
    'A7': [69, 73, 76, 79], 'B7': [71, 75, 78, 82], 'Cm7': [60, 63, 67, 70],
    'Dm7': [62, 65, 69, 72], 'Em7': [64, 67, 71, 74], 'Fm7': [65, 68, 72, 75],
    'Gm7': [67, 70, 74, 77], 'Am7': [69, 72, 76, 79],
}

# Scales
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'blues': [0, 3, 5, 6, 7, 10],
    'pentatonic': [0, 2, 4, 7, 9],
}

# Genre parameters
GENRE_PARAMS = {
    'pop': {
        'tempo': 120, 'key': 'C', 'scale': 'major', 
        'instruments': {
            'melody': 'Electric Piano 1',
            'rhythm_primary': 'Clean Electric Guitar', 
            'rhythm_secondary': 'String Ensemble 1',
            'bass': 'Electric Bass finger'
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'],
            ['Am', 'F', 'C', 'G'], 
            ['C', 'F', 'Am', 'G']
        ],
        'mood': 'happy'
    },
    'rock': {
        'tempo': 130, 'key': 'E', 'scale': 'pentatonic',
        'instruments': {
            'melody': 'Distortion Guitar',
            'rhythm_primary': 'Overdriven Guitar',
            'rhythm_secondary': 'Rock Organ',
            'bass': 'Electric Bass pick'
        },
        'chord_progressions': [
            ['E', 'D', 'A', 'E'],
            ['A', 'G', 'D', 'A'],
            ['Em', 'G', 'D', 'A']
        ],
        'mood': 'energetic'
    },
    'ballad': {
        'tempo': 70, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Nylon String Guitar',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Warm Pad',
            'bass': 'Acoustic Bass'
        },
        'chord_progressions': [
            ['C', 'G', 'Am', 'F'],
            ['Am', 'F', 'C', 'G'],
            ['F', 'C', 'Dm', 'G']
        ],
        'mood': 'emotional'
    },
    'jazz': {
        'tempo': 120, 'key': 'C', 'scale': 'major',
        'instruments': {
            'melody': 'Tenor Sax',
            'rhythm_primary': 'Electric Piano 1',
            'rhythm_secondary': 'Brass Section', 
            'bass': 'Acoustic Bass'
        },
        'chord_progressions': [
            ['Dm7', 'G7', 'Cmaj7'],
            ['Cm7', 'F7', 'Bbmaj7'],
            ['Am7', 'D7', 'Gmaj7']
        ],
        'mood': 'sophisticated'
    }
}

# ==================== MUSIC GENERATION FUNCTIONS ====================

def chord_names_to_midi_notes(chord_names):
    """Convert chord names to MIDI notes"""
    if not isinstance(chord_names, list):
        return [CHORDS['C']]
    
    midi_chords = []
    for chord_name in chord_names:
        if isinstance(chord_name, str) and chord_name in CHORDS:
            midi_chords.append(CHORDS[chord_name])
        else:
            midi_chords.append(CHORDS['C'])
    
    return midi_chords

def detect_genre_from_lyrics(lyrics):
    """Simple genre detection from lyrics"""
    if not lyrics:
        return 'pop'
    
    lyrics_lower = lyrics.lower()
    
    if any(word in lyrics_lower for word in ['rock', 'guitar', 'energy', 'power']):
        return 'rock'
    elif any(word in lyrics_lower for word in ['jazz', 'sax', 'swing', 'blue']):
        return 'jazz' 
    elif any(word in lyrics_lower for word in ['sad', 'heartbreak', 'tears', 'alone']):
        return 'ballad'
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
    
    # Select chord progression
    progressions = params['chord_progressions']
    selected_progression = random.choice(progressions)
    params['chords'] = chord_names_to_midi_notes(selected_progression)
    params['selected_progression'] = selected_progression
    
    logger.info(f"Music params: {genre}, tempo={params['tempo']}, progression={selected_progression}")
    return params

def create_simple_midi(params, output_path):
    """Create a simple MIDI file for testing"""
    try:
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Set tempo
        tempo = bpm2tempo(params['tempo'])
        track.append(MetaMessage('set_tempo', tempo=tempo))
        
        # Set instrument
        melody_program = INSTRUMENTS.get(params['instruments']['melody'], 0)
        track.append(Message('program_change', program=melody_program))
        
        # Simple melody based on chords
        chords = params['chords']
        for i, chord in enumerate(chords):
            for note in chord[:2]:  # Play first two notes of chord
                track.append(Message('note_on', note=note, velocity=80, time=0))
                track.append(Message('note_off', note=note, velocity=0, time=480))
        
        mid.save(output_path)
        logger.info(f"MIDI created: {output_path}")
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
            '-ni', str(SOUNDFONT_PATH), str(midi_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"WAV generated: {output_wav_path}")
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
        logger.info(f"MP3 created: {mp3_path}")
        return True
    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

def merge_audio_with_vocals(instrumental_path, vocal_path, output_path):
    """Merge instrumental and vocal tracks"""
    try:
        if not instrumental_path.exists():
            return False, "Instrumental file not found"
        if not vocal_path.exists():
            return False, "Vocal file not found"
        
        instrumental = AudioSegment.from_mp3(instrumental_path)
        vocals = AudioSegment.from_mp3(vocal_path)
        
        # Adjust volumes
        vocals = vocals - 3  # Reduce vocal volume slightly
        
        # Ensure vocals don't exceed instrumental length
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        # Mix audio
        mixed = instrumental.overlay(vocals)
        mixed.export(output_path, format="mp3", bitrate="192k")
        
        logger.info(f"Merged audio created: {output_path}")
        return True, "Merge successful"
        
    except Exception as e:
        logger.error(f"Audio merging error: {e}")
        return False, f"Merge error: {str(e)}"

# ==================== FLASK ROUTES ====================

def generate_unique_id(text):
    """Generate unique ID"""
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

@app.route('/')
def index():
    """Main interface"""
    html_template = '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Music Generator</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 min-h-screen p-4">
        <div class="max-w-2xl mx-auto">
            <div class="bg-white rounded-lg shadow-lg p-6">
                <h1 class="text-3xl font-bold text-center mb-6">🎵 AI Music Generator</h1>
                
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
                                <option value="rock">Rock</option>
                                <option value="ballad">Ballad</option>
                                <option value="jazz">Jazz</option>
                            </select>
                        </div>
                        <div>
                            <label class="block font-semibold mb-2">Tempo (BPM):</label>
                            <input type="number" id="tempo" class="w-full p-2 border rounded" placeholder="Auto" min="60" max="200">
                        </div>
                    </div>
                    
                    <div class="flex items-center space-x-2">
                        <input type="checkbox" id="addVocals" class="w-4 h-4">
                        <label class="font-semibold">Tambahkan AI Vocal</label>
                    </div>
                    
                    <button type="submit" id="generateBtn" class="w-full bg-blue-600 text-white py-3 rounded font-bold hover:bg-blue-700">
                        🚀 Generate Music
                    </button>
                </form>
                
                <div id="status" class="mt-4 hidden">
                    <div id="statusMessage" class="p-3 rounded"></div>
                </div>
                
                <div id="results" class="mt-6 space-y-4 hidden">
                    <div class="border rounded p-4">
                        <h3 class="font-bold mb-2">🎵 Instrumental</h3>
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
                <div>SoundFont: <span id="soundfontStatus" class="font-semibold">Checking...</span></div>
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
                btn.textContent = 'Generating...';
                status.classList.remove('hidden');
                statusMessage.innerHTML = '<div class="text-blue-600">🚀 Generating music... (1-2 minutes)</div>';
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
                        statusMessage.innerHTML = '<div class="text-green-600">✅ Generation successful!</div>';
                        
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
                    btn.textContent = '🚀 Generate Music';
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
    """Check system status"""
    return jsonify({
        'vocal_ai': vocal_synth.available,
        'soundfont': SOUNDFONT_PATH and SOUNDFONT_PATH.exists()
    })

@app.route('/generate-vocals', methods=['POST'])
def generate_vocals():
    """Generate vocals from lyrics - FIXED CONTENT-TYPE"""
    try:
        # Handle both form data and JSON
        if request.content_type == 'application/json':
            data = request.get_json()
        else:
            data = request.form.to_dict()
            
        lyrics = data.get('lyrics', '').strip()
        
        if not lyrics:
            return jsonify({'error': 'Lirik diperlukan'}), 400
        
        vocal_id = generate_unique_id(lyrics)
        output_path = VOCAL_OUTPUT_DIR / f"{vocal_id}.mp3"
        
        success, message = vocal_synth.synthesize_vocals(lyrics, output_path)
        
        if success:
            return jsonify({
                'success': True,
                'filename': f'{vocal_id}.mp3',
                'vocal_url': f'/static/vocal_output/{vocal_id}.mp3',
                'message': message
            })
        else:
            return jsonify({'error': message}), 500
            
    except Exception as e:
        logger.error(f"Vocal generation error: {e}")
        return jsonify({'error': 'Internal error'}), 500

@app.route('/generate-instrumental', methods=['POST'])
def generate_instrumental():
    """Generate instrumental only - FIXED"""
    try:
        # Handle both form data and JSON
        if request.content_type == 'application/json':
            data = request.get_json()
        else:
            data = request.form.to_dict()
            
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto')
        tempo_input = data.get('tempo', 'auto')
        
        if not lyrics:
            return jsonify({'error': 'Lirik diperlukan'}), 400
        
        # Get music parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Generate files
        unique_id = generate_unique_id(lyrics)
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav"
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        
        # Create MIDI
        if not create_simple_midi(params, midi_path):
            return jsonify({'error': 'MIDI creation failed'}), 500
        
        # Convert to audio
        if not midi_to_audio(midi_path, wav_path):
            midi_path.unlink(missing_ok=True)
            return jsonify({'error': 'Audio conversion failed'}), 500
        
        # Convert to MP3
        if not wav_to_mp3(wav_path, mp3_path):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return jsonify({'error': 'MP3 conversion failed'}), 500
        
        # Cleanup
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        return jsonify({
            'success': True,
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo'],
            'progression': ' '.join(params['selected_progression'])
        })
        
    except Exception as e:
        logger.error(f"Instrumental generation error: {e}")
        return jsonify({'error': 'Generation failed'}), 500

@app.route('/generate-full-song', methods=['POST'])
def generate_full_song():
    """Generate complete song with optional vocals - FIXED"""
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
        
        # Generate instrumental - call the function directly
        instrumental_data = generate_instrumental_internal(lyrics, genre, tempo)
        if not instrumental_data.get('success'):
            return jsonify({'error': instrumental_data.get('error', 'Instrumental generation failed')}), 500
        
        result['instrumental'] = instrumental_data
        
        # Generate vocals if requested
        if add_vocals and vocal_synth.available:
            vocal_data = generate_vocals_internal(lyrics)
            
            if vocal_data.get('success'):
                result['vocals'] = vocal_data
                
                # Merge audio
                instrumental_path = AUDIO_OUTPUT_DIR / instrumental_data['filename']
                vocal_path = VOCAL_OUTPUT_DIR / vocal_data['filename']
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
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

# Internal functions to avoid route calling issues
def generate_instrumental_internal(lyrics, genre_input='auto', tempo_input='auto'):
    """Internal function for instrumental generation"""
    try:
        # Get music parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_from_lyrics(lyrics)
        params = get_music_params_from_lyrics(genre, lyrics, tempo_input)
        
        # Generate files
        unique_id = generate_unique_id(lyrics)
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav"
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        
        # Create MIDI
        if not create_simple_midi(params, midi_path):
            return {'success': False, 'error': 'MIDI creation failed'}
        
        # Convert to audio
        if not midi_to_audio(midi_path, wav_path):
            midi_path.unlink(missing_ok=True)
            return {'success': False, 'error': 'Audio conversion failed'}
        
        # Convert to MP3
        if not wav_to_mp3(wav_path, mp3_path):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return {'success': False, 'error': 'MP3 conversion failed'}
        
        # Cleanup
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        return {
            'success': True,
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo'],
            'progression': ' '.join(params['selected_progression'])
        }
        
    except Exception as e:
        logger.error(f"Instrumental generation error: {e}")
        return {'success': False, 'error': 'Generation failed'}

def generate_vocals_internal(lyrics):
    """Internal function for vocal generation"""
    try:
        if not lyrics:
            return {'success': False, 'error': 'Lirik diperlukan'}
        
        vocal_id = generate_unique_id(lyrics)
        output_path = VOCAL_OUTPUT_DIR / f"{vocal_id}.mp3"
        
        success, message = vocal_synth.synthesize_vocals(lyrics, output_path)
        
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
        logger.error(f"Vocal generation error: {e}")
        return {'success': False, 'error': 'Internal error'}

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
    """Start application"""
    logger.info("🎵 Starting AI Music Generator")
    logger.info(f"✅ SoundFont: {'Available' if SOUNDFONT_PATH else 'Not Found'}")
    logger.info(f"✅ Vocal AI: {'Available' if vocal_synth.available else 'Not Available'}")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
