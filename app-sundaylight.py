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

# ==================== LIGHTWEIGHT IMPORTS ====================
try:
    from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    print("⚠️  Mido not available")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("⚠️  gTTS not available")

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("⚠️  Pydub not available")

# ==================== MEMORY OPTIMIZED CONFIG ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # No file handler to save memory
)

logger = logging.getLogger(__name__)

# Initialize Flask app dengan memory optimization
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

# Auto-detect SoundFont (lightweight version)
SOUNDFONT_PATH = None
SOUNDFONT_CANDIDATES = [
    BASE_DIR / 'GeneralUser-GS-v1.471.sf2',
    BASE_DIR / 'FluidR3_GM.sf2', 
    BASE_DIR / 'TimGM6mb.sf2',  # Smallest file size
]

for candidate in SOUNDFONT_CANDIDATES:
    if candidate.exists():
        SOUNDFONT_PATH = candidate
        logger.info(f"✅ Using SoundFont: {candidate.name}")
        break

# ==================== MEMORY OPTIMIZED VOCAL SYNTHESIZER ====================

class LightweightVocalSynthesizer:
    """Lightweight vocal synthesizer untuk Termux"""
    
    def __init__(self):
        self.available = GTTS_AVAILABLE
        self.setup()
        
    def setup(self):
        """Setup TTS engine"""
        if self.available:
            logger.info("✅ gTTS available for vocal synthesis")
        else:
            logger.warning("❌ gTTS not available")
    
    def synthesize_vocals(self, lyrics, output_path):
        """Synthesize vocals dengan memory optimization"""
        try:
            if not self.available:
                return False, "Vocal AI not available"
            
            # Simple lyrics processing (no complex structure matching)
            processed_lyrics = self._preprocess_lyrics_simple(lyrics)
            if not processed_lyrics:
                return False, "No valid lyrics"
            
            return self._synthesize_gtts_simple(processed_lyrics, output_path)
            
        except Exception as e:
            logger.error(f"Vocal synthesis error: {e}")
            return False, f"Synthesis error: {str(e)}"
    
    def _preprocess_lyrics_simple(self, lyrics):
        """Simple lyrics preprocessing"""
        try:
            if not lyrics or len(lyrics.strip()) < 3:
                return None
            
            # Basic cleaning only
            cleaned = ' '.join(lyrics.split())
            cleaned = cleaned.replace('\n', '. ')
            
            # Limit length untuk memory
            return cleaned[:200]  # Shorter for mobile
            
        except Exception as e:
            logger.error(f"Lyrics preprocessing error: {e}")
            return lyrics[:150]
    
    def _synthesize_gtts_simple(self, text, output_path):
        """Simple gTTS synthesis"""
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

# Initialize Vocal AI
vocal_synth = LightweightVocalSynthesizer()

# ==================== SIMPLIFIED MUSIC CONFIGURATION ====================

# Simplified Instruments (reduced set)
INSTRUMENTS = {
    'Piano': 0, 'Electric Piano': 4, 'Guitar Clean': 27, 
    'Guitar Distortion': 30, 'Bass': 33, 'Strings': 48,
    'Sax': 66, 'Trumpet': 56, 'Flute': 73, 'Synth': 80
}

# Basic Chords (reduced set)
CHORDS = {
    'C': [60, 64, 67], 'G': [67, 71, 74], 'Am': [69, 72, 76], 
    'F': [65, 69, 72], 'Dm': [62, 65, 69], 'Em': [64, 67, 71],
    'C7': [60, 64, 67, 70], 'G7': [67, 71, 74, 77]
}

# Simplified Genre Parameters
GENRE_PARAMS = {
    'pop': {
        'tempo': 120, 'key': 'C', 
        'instruments': {'melody': 'Electric Piano', 'rhythm': 'Guitar Clean', 'bass': 'Bass'},
        'chord_progressions': [['C', 'G', 'Am', 'F'], ['Am', 'F', 'C', 'G']],
        'mood': 'happy'
    },
    'rock': {
        'tempo': 130, 'key': 'E',
        'instruments': {'melody': 'Guitar Distortion', 'rhythm': 'Guitar Distortion', 'bass': 'Bass'},
        'chord_progressions': [['Em', 'C', 'G', 'D'], ['E', 'D', 'A', 'E']],
        'mood': 'energetic'
    },
    'ballad': {
        'tempo': 70, 'key': 'C',
        'instruments': {'melody': 'Piano', 'rhythm': 'Strings', 'bass': 'Bass'},
        'chord_progressions': [['C', 'G', 'Am', 'F'], ['F', 'C', 'Dm', 'G']],
        'mood': 'emotional'
    },
    'jazz': {
        'tempo': 110, 'key': 'C', 
        'instruments': {'melody': 'Sax', 'rhythm': 'Piano', 'bass': 'Bass'},
        'chord_progressions': [['C7', 'F7', 'G7'], ['Am', 'Dm', 'G7']],
        'mood': 'relaxed'
    }
}

# ==================== MEMORY OPTIMIZED FUNCTIONS ====================

def generate_unique_id(text):
    """Generate unique ID"""
    return f"{hashlib.md5(text.encode()).hexdigest()[:8]}_{int(time.time())}"

def detect_genre_simple(lyrics):
    """Simple genre detection"""
    if not lyrics:
        return 'pop'
    
    lyrics_lower = lyrics.lower()
    
    if any(word in lyrics_lower for word in ['rock', 'guitar', 'energy']):
        return 'rock'
    elif any(word in lyrics_lower for word in ['jazz', 'sax', 'blue']):
        return 'jazz'
    elif any(word in lyrics_lower for word in ['sad', 'heartbreak', 'tears']):
        return 'ballad'
    else:
        return 'pop'

def get_music_params_simple(genre, lyrics, tempo_input='auto'):
    """Get simple music parameters"""
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
    
    # Simple chord progression
    progressions = params['chord_progressions']
    params['chord_progression'] = random.choice(progressions)
    
    logger.info(f"Simple music params: {genre}, tempo={params['tempo']}")
    return params

def create_simple_midi(params, output_path):
    """Create simple MIDI file untuk mobile"""
    try:
        if not MIDO_AVAILABLE:
            return False
            
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Set tempo
        tempo = bpm2tempo(params['tempo'])
        track.append(MetaMessage('set_tempo', tempo=tempo))
        
        # Set instruments
        melody_program = INSTRUMENTS.get(params['instruments']['melody'], 0)
        track.append(Message('program_change', program=melody_program))
        
        # Simple structure: Intro (4) + Verse (16) + Chorus (16) + Outro (4) = 40 beats (~2 minutes)
        chords = params['chord_progression']
        
        # Intro - simpler
        for i in range(4):
            if chords:
                note = chords[i % len(chords)][0] if i < len(chords) else chords[0][0]
                track.append(Message('note_on', note=note, velocity=70, time=0))
                track.append(Message('note_off', note=note, velocity=0, time=480))
        
        # Verse & Chorus
        for section in range(2):  # Verse and Chorus
            for i in range(16):
                chord_idx = i % len(chords)
                if chords and chord_idx < len(chords):
                    chord = chords[chord_idx]
                    for j, note in enumerate(chord[:2]):  # Only first 2 notes
                        track.append(Message('note_on', note=note, velocity=80, time=0))
                        track.append(Message('note_off', note=note, velocity=0, time=240))
        
        # Outro - fade out
        for i in range(4):
            if chords:
                note = chords[-1][0]  # Last chord root
                velocity = 70 - (i * 15)  # Fade out
                track.append(Message('note_on', note=note, velocity=max(40, velocity), time=0))
                track.append(Message('note_off', note=note, velocity=0, time=480))
        
        mid.save(output_path)
        logger.info(f"Simple MIDI created: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Simple MIDI creation error: {e}")
        return False

def midi_to_audio_simple(midi_path, output_wav_path):
    """Convert MIDI to WAV dengan memory optimization"""
    if not SOUNDFONT_PATH or not SOUNDFONT_PATH.exists():
        logger.error("SoundFont not available")
        return False
    
    try:
        # Simple FluidSynth command untuk mobile
        cmd = [
            'fluidsynth', '-F', str(output_wav_path),
            '-O', 's16',  # 16-bit output
            '-r', '22050',  # Lower sample rate
            '-g', '0.8',    # Lower gain
            '-ni', str(SOUNDFONT_PATH), str(midi_path)
        ]
        
        # Timeout shorter untuk mobile
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and output_wav_path.exists():
            logger.info(f"WAV generated: {output_wav_path}")
            return True
        else:
            logger.error(f"FluidSynth failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FluidSynth timeout (30s)")
        return False
    except Exception as e:
        logger.error(f"MIDI to audio error: {e}")
        return False

def wav_to_mp3_simple(wav_path, mp3_path):
    """Convert WAV to MP3 dengan memory optimization"""
    try:
        if not PYDUB_AVAILABLE:
            # Fallback: use ffmpeg directly
            cmd = ['ffmpeg', '-i', str(wav_path), '-b:a', '128k', str(mp3_path), '-y']
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            return result.returncode == 0
        
        audio = AudioSegment.from_wav(wav_path)
        # Simple processing only
        audio = normalize(audio, headroom=3.0)
        audio.export(mp3_path, format="mp3", bitrate="128k")  # Lower bitrate
        
        logger.info(f"MP3 created: {mp3_path}")
        return True
    except Exception as e:
        logger.error(f"WAV to MP3 error: {e}")
        return False

def merge_audio_simple(instrumental_path, vocal_path, output_path):
    """Simple audio merging"""
    try:
        if not PYDUB_AVAILABLE:
            return False, "Pydub not available"
            
        instrumental = AudioSegment.from_mp3(instrumental_path)
        vocals = AudioSegment.from_mp3(vocal_path)
        
        # Simple volume adjustment
        vocals = vocals - 4  # Reduce vocal volume
        
        # Ensure vocals fit
        if len(vocals) > len(instrumental):
            vocals = vocals[:len(instrumental)]
        
        # Simple mix
        mixed = instrumental.overlay(vocals)
        mixed.export(output_path, format="mp3", bitrate="128k")
        
        logger.info(f"Merged audio created: {output_path}")
        return True, "Merge successful"
        
    except Exception as e:
        logger.error(f"Audio merging error: {e}")
        return False, f"Merge error: {str(e)}"

# ==================== MEMORY MANAGEMENT ====================

def cleanup_old_files(max_files=5):
    """Cleanup old files to prevent storage overflow"""
    try:
        for directory in [AUDIO_OUTPUT_DIR, VOCAL_OUTPUT_DIR, MERGED_OUTPUT_DIR]:
            files = list(directory.glob("*.mp3")) + list(directory.glob("*.wav")) + list(directory.glob("*.mid"))
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Keep only latest files
            for old_file in files[max_files:]:
                try:
                    old_file.unlink()
                    logger.info(f"Cleaned up: {old_file.name}")
                except:
                    pass
                    
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def memory_guard():
    """Check memory usage and prevent overflow"""
    try:
        import psutil
        process = psutil.Process()
        memory_percent = process.memory_percent()
        
        if memory_percent > 70:  # If using more than 70% memory
            logger.warning(f"High memory usage: {memory_percent:.1f}%")
            cleanup_old_files(3)  # Aggressive cleanup
            return False
        return True
    except ImportError:
        return True  # psutil not available, continue anyway

# ==================== LIGHTWEIGHT FLASK ROUTES ====================

@app.route('/')
def index():
    """Lightweight main interface"""
    html_template = '''
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lightweight Music Generator</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input, select, textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 5px; }
            button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
            button:disabled { background: #6c757d; }
            .status { padding: 10px; border-radius: 5px; margin: 10px 0; }
            .success { background: #d4edda; color: #155724; }
            .error { background: #f8d7da; color: #721c24; }
            .info { background: #d1ecf1; color: #0c5460; }
            .hidden { display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🎵 Lightweight Music Generator</h2>
            <p>Optimized for Termux/Mobile</p>
            
            <form id="musicForm">
                <div class="form-group">
                    <label>Lirik Lagu:</label>
                    <textarea id="lyrics" rows="3" placeholder="Masukkan lirik..."></textarea>
                </div>
                
                <div class="form-group">
                    <label>Genre:</label>
                    <select id="genre">
                        <option value="auto">Auto Detect</option>
                        <option value="pop">Pop</option>
                        <option value="rock">Rock</option>
                        <option value="ballad">Ballad</option>
                        <option value="jazz">Jazz</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>Tempo (BPM):</label>
                    <input type="number" id="tempo" placeholder="Auto" min="60" max="160">
                </div>
                
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="addVocals" checked>
                        Tambahkan AI Vocal
                    </label>
                </div>
                
                <button type="submit" id="generateBtn">🚀 Generate Music (1-2 menit)</button>
            </form>
            
            <div id="status" class="status hidden"></div>
            
            <div id="results" class="hidden">
                <div class="form-group">
                    <h3>🎵 Hasil:</h3>
                    <audio id="instrumentalAudio" controls style="width: 100%; margin: 10px 0;"></audio>
                    <button onclick="downloadAudio('instrumental')">💾 Download Instrumental</button>
                </div>
                
                <div id="vocalResult" class="hidden">
                    <audio id="vocalAudio" controls style="width: 100%; margin: 10px 0;"></audio>
                    <button onclick="downloadAudio('vocal')">💾 Download Vocals</button>
                </div>
                
                <div id="mergedResult" class="hidden">
                    <audio id="mergedAudio" controls style="width: 100%; margin: 10px 0;"></audio>
                    <button onclick="downloadAudio('merged')">💾 Download Full Song</button>
                </div>
            </div>
            
            <div style="margin-top: 20px; font-size: 12px; color: #666; text-align: center;">
                <div>Vocal AI: <span id="vocalStatus">Checking...</span></div>
                <div>MIDI: <span id="midiStatus">Checking...</span></div>
                <div>Audio: <span id="audioStatus">Checking...</span></div>
            </div>
        </div>

        <script>
            // Check system status
            function checkStatus() {
                fetch('/system-status').then(r => r.json()).then(data => {
                    document.getElementById('vocalStatus').textContent = data.vocal_ai ? '✅' : '❌';
                    document.getElementById('midiStatus').textContent = data.midi ? '✅' : '❌';
                    document.getElementById('audioStatus').textContent = data.audio ? '✅' : '❌';
                });
            }
            checkStatus();

            document.getElementById('musicForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const lyrics = document.getElementById('lyrics').value.trim();
                if (!lyrics) {
                    alert('Masukkan lirik terlebih dahulu!');
                    return;
                }

                const btn = document.getElementById('generateBtn');
                const status = document.getElementById('status');
                const results = document.getElementById('results');

                btn.disabled = true;
                btn.textContent = 'Generating...';
                status.className = 'status info';
                status.textContent = '🚀 Generating music... (1-2 minutes)';
                status.classList.remove('hidden');
                results.classList.add('hidden');

                try {
                    const formData = new FormData();
                    formData.append('lyrics', lyrics);
                    formData.append('genre', document.getElementById('genre').value);
                    formData.append('tempo', document.getElementById('tempo').value || 'auto');
                    formData.append('add_vocals', document.getElementById('addVocals').checked);

                    const response = await fetch('/generate-music', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (data.success) {
                        status.className = 'status success';
                        status.textContent = '✅ Generation successful!';
                        
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
                        status.className = 'status error';
                        status.textContent = '❌ ' + (data.error || 'Generation failed');
                    }

                } catch (error) {
                    status.className = 'status error';
                    status.textContent = '❌ Network error';
                } finally {
                    btn.disabled = false;
                    btn.textContent = '🚀 Generate Music (1-2 menit)';
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
    """Check lightweight system status"""
    return jsonify({
        'vocal_ai': vocal_synth.available,
        'midi': MIDO_AVAILABLE,
        'audio': PYDUB_AVAILABLE,
        'soundfont': SOUNDFONT_PATH and SOUNDFONT_PATH.exists()
    })

@app.route('/generate-music', methods=['POST'])
def generate_music():
    """Lightweight music generation endpoint"""
    try:
        # Memory guard
        if not memory_guard():
            return jsonify({'error': 'Memory usage too high, please try again'}), 500
        
        data = request.form.to_dict()
        lyrics = data.get('lyrics', '').strip()
        genre_input = data.get('genre', 'auto')
        tempo_input = data.get('tempo', 'auto')
        add_vocals = data.get('add_vocals', 'false').lower() == 'true'
        
        if not lyrics:
            return jsonify({'error': 'Lirik diperlukan'}), 400
        
        # Generate unique ID
        unique_id = generate_unique_id(lyrics)
        
        result = {
            'success': True,
            'instrumental': None,
            'vocals': None, 
            'merged': None
        }
        
        # Step 1: Generate instrumental
        logger.info("Step 1: Generating instrumental...")
        
        # Get music parameters
        genre = genre_input if genre_input != 'auto' else detect_genre_simple(lyrics)
        params = get_music_params_simple(genre, lyrics, tempo_input)
        
        # Create MIDI
        midi_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mid"
        if not create_simple_midi(params, midi_path):
            return jsonify({'error': 'MIDI creation failed'}), 500
        
        # Convert to audio
        wav_path = AUDIO_OUTPUT_DIR / f"{unique_id}.wav"
        if not midi_to_audio_simple(midi_path, wav_path):
            midi_path.unlink(missing_ok=True)
            return jsonify({'error': 'Audio conversion failed'}), 500
        
        # Convert to MP3
        mp3_path = AUDIO_OUTPUT_DIR / f"{unique_id}.mp3"
        if not wav_to_mp3_simple(wav_path, mp3_path):
            for path in [midi_path, wav_path]:
                path.unlink(missing_ok=True)
            return jsonify({'error': 'MP3 conversion failed'}), 500
        
        # Cleanup temporary files
        for path in [midi_path, wav_path]:
            path.unlink(missing_ok=True)
        
        result['instrumental'] = {
            'filename': f'{unique_id}.mp3',
            'genre': genre,
            'tempo': params['tempo']
        }
        
        # Step 2: Generate vocals if requested
        if add_vocals and vocal_synth.available:
            logger.info("Step 2: Generating vocals...")
            
            vocal_path = VOCAL_OUTPUT_DIR / f"{unique_id}.mp3"
            success, message = vocal_synth.synthesize_vocals(lyrics, vocal_path)
            
            if success:
                result['vocals'] = {
                    'filename': f'{unique_id}.mp3',
                    'message': message
                }
                
                # Step 3: Merge audio
                logger.info("Step 3: Merging audio...")
                
                merged_id = generate_unique_id(lyrics + "_merged")
                merged_path = MERGED_OUTPUT_DIR / f"{merged_id}.mp3"
                
                success, message = merge_audio_simple(mp3_path, vocal_path, merged_path)
                if success:
                    result['merged'] = {
                        'filename': f'{merged_id}.mp3',
                        'message': message
                    }
        
        # Final cleanup
        cleanup_old_files(5)
        
        logger.info("✅ Music generation completed successfully")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Music generation error: {e}")
        # Emergency cleanup on error
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
    """Start lightweight application"""
    logger.info("🎵 Starting Lightweight Music Generator for Termux")
    logger.info(f"✅ MIDI: {'Available' if MIDO_AVAILABLE else 'Not Available'}")
    logger.info(f"✅ Vocal AI: {'Available' if vocal_synth.available else 'Not Available'}")
    logger.info(f"✅ Audio Processing: {'Available' if PYDUB_AVAILABLE else 'Not Available'}")
    logger.info(f"✅ SoundFont: {'Available' if SOUNDFONT_PATH else 'Not Found'}")
    
    # Pre-cleanup
    cleanup_old_files(3)
    
    # Run with memory optimization
    app.run(
        host='0.0.0.0', 
        port=5000, 
        debug=False,
        threaded=True,
        processes=1  # Single process untuk mobile
    )

if __name__ == '__main__':
    main()
