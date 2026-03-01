from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp
import os
import uuid
import threading
import time
import re
import json
import subprocess
import urllib.parse
import urllib.request
import shutil

# Find ffmpeg — prefer system install, fall back to static_ffmpeg pip package
FFMPEG_BIN = shutil.which('ffmpeg')
FFPROBE_BIN = shutil.which('ffprobe')

if FFMPEG_BIN:
    FFMPEG_DIR = os.path.dirname(FFMPEG_BIN)
    print(f"  ✅ ffmpeg (system): {FFMPEG_BIN}")
else:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        FFMPEG_BIN, FFPROBE_BIN = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        FFMPEG_DIR = os.path.dirname(FFMPEG_BIN)
        print(f"  ✅ ffmpeg (bundled): {FFMPEG_BIN}")
    except Exception:
        print("  ❌ ffmpeg not found! Install ffmpeg or pip install static-ffmpeg")
        FFMPEG_BIN = 'ffmpeg'
        FFPROBE_BIN = 'ffprobe'
        FFMPEG_DIR = ''

app = Flask(__name__, static_folder='static', template_folder='templates')

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Track download progress per task_id
download_progress = {}


def detect_platform(url):
    """Detect which platform a URL belongs to."""
    if re.match(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+', url):
        return 'youtube'
    if re.match(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+', url):
        return 'instagram'
    return None


def clean_old_files():
    """Delete files older than 10 minutes from the downloads folder."""
    while True:
        time.sleep(300)
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 600:
                try:
                    os.remove(filepath)
                except Exception:
                    pass


cleanup_thread = threading.Thread(target=clean_old_files, daemon=True)
cleanup_thread.start()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Fetch video info and available formats."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    platform = detect_platform(url)
    if not platform:
        return jsonify({'error': 'Unsupported URL — paste a YouTube or Instagram link'}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': FFMPEG_DIR,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        seen_qualities = set()

        if platform == 'instagram':
            # Instagram: collect available video formats
            for f in info.get('formats', []):
                height = f.get('height')
                vcodec = f.get('vcodec', 'none')
                if height and vcodec != 'none' and height >= 144:
                    quality_key = f"{height}p"
                    if quality_key not in seen_qualities:
                        seen_qualities.add(quality_key)
                        filesize = f.get('filesize') or f.get('filesize_approx') or 0
                        formats.append({
                            'quality': quality_key,
                            'height': height,
                            'ext': 'mp4',
                            'filesize': filesize,
                            'format_id': quality_key,
                            'has_audio': True,
                        })

            formats.sort(key=lambda x: x['height'], reverse=True)

            # If no individual qualities found, offer a simple "Best" option
            if not formats:
                formats.append({
                    'quality': 'Best Quality',
                    'height': 9999,
                    'ext': 'mp4',
                    'filesize': 0,
                    'format_id': 'insta_best',
                    'has_audio': True,
                })

            # Add audio-only option
            formats.append({
                'quality': 'Audio Only (MP3)',
                'height': 0,
                'ext': 'mp3',
                'filesize': 0,
                'format_id': 'audio',
                'has_audio': True,
            })
        else:
            # YouTube: collect video stream qualities
            for f in info.get('formats', []):
                height = f.get('height')
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')

                if height and vcodec != 'none' and height >= 144:
                    quality_key = f"{height}p"
                    if quality_key not in seen_qualities:
                        seen_qualities.add(quality_key)
                        filesize = f.get('filesize') or f.get('filesize_approx') or 0
                        formats.append({
                            'quality': quality_key,
                            'height': height,
                            'ext': f.get('ext', ''),
                            'filesize': filesize,
                            'format_id': f.get('format_id', ''),
                            'has_audio': acodec != 'none',
                        })

            formats.sort(key=lambda x: x['height'], reverse=True)

            formats.append({
                'quality': 'Audio Only (MP3)',
                'height': 0,
                'ext': 'mp3',
                'filesize': 0,
                'format_id': 'audio',
                'has_audio': True,
            })

        result = {
            'title': info.get('title', 'Unknown'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'channel': info.get('channel', info.get('uploader', 'Unknown')),
            'view_count': info.get('view_count', 0) or 0,
            'like_count': info.get('like_count', 0) or 0,
            'formats': formats,
            'url': url,
            'platform': platform,
        }

        # Proxy thumbnail for Instagram (they block direct hotlinking)
        if platform == 'instagram' and result['thumbnail']:
            result['thumbnail'] = '/api/thumb?url=' + urllib.parse.quote(result['thumbnail'], safe='')

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Failed to fetch video info: {str(e)}'}), 500


@app.route('/api/start_download', methods=['POST'])
def start_download():
    """Start a download in background, return task_id for progress tracking."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', '720p')
    format_id = data.get('format_id', '')

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    platform = data.get('platform', detect_platform(url) or 'youtube')

    task_id = str(uuid.uuid4())[:12]
    download_progress[task_id] = {
        'status': 'starting',
        'percent': 0,
        'speed': '',
        'eta': '',
        'phase': 'Preparing download...',
        'filename': None,
        'error': None,
    }

    thread = threading.Thread(
        target=_do_download,
        args=(task_id, url, quality, format_id, platform),
        daemon=True,
    )
    thread.start()

    return jsonify({'task_id': task_id})


def _strip_ansi(text):
    """Remove ANSI escape codes from yt-dlp output strings."""
    if not text:
        return ''
    return re.sub(r'\x1b\[[0-9;]*m', '', str(text)).strip()


def _format_speed(bytes_per_sec):
    """Format bytes/sec into a human readable string."""
    if not bytes_per_sec:
        return ''
    if bytes_per_sec >= 1_048_576:
        return f"{bytes_per_sec / 1_048_576:.1f} MB/s"
    if bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.0f} KB/s"
    return f"{bytes_per_sec:.0f} B/s"


def _format_eta(seconds):
    """Format ETA seconds into mm:ss."""
    if not seconds:
        return ''
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _do_download(task_id, url, quality, format_id, platform='youtube'):
    """Background download worker with progress tracking."""
    try:
        file_id = task_id
        output_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')

        is_single_stream = False  # assume merging may be needed

        # Track which download phase we are in
        phase_info = {'phase_num': 0}  # 0=first stream, 1=second stream

        def progress_hook(d):
            if d['status'] == 'downloading':
                # Use raw numeric values (no ANSI codes)
                downloaded = d.get('downloaded_bytes', 0) or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                speed = d.get('speed') or 0  # bytes/sec (raw number)
                eta = d.get('eta') or 0      # seconds (raw number)

                if total > 0:
                    pct = (downloaded / total) * 100
                else:
                    pct = 0

                if is_single_stream:
                    # Instagram: single combined stream, scale 0-90%
                    scaled_pct = pct * 0.90
                    phase_text = 'Downloading video...'
                else:
                    # YouTube: two streams — video 0-60%, audio 60-85%
                    if phase_info['phase_num'] == 0:
                        scaled_pct = pct * 0.60
                        phase_text = 'Downloading video...'
                    else:
                        scaled_pct = 60 + (pct * 0.25)
                        phase_text = 'Downloading audio...'

                download_progress[task_id].update({
                    'status': 'downloading',
                    'percent': round(min(scaled_pct, 92), 1),
                    'speed': _format_speed(speed),
                    'eta': _format_eta(eta),
                    'phase': phase_text,
                })

            elif d['status'] == 'finished':
                phase_info['phase_num'] += 1
                if is_single_stream:
                    done_pct = 92
                else:
                    done_pct = 60 if phase_info['phase_num'] == 1 else 85
                download_progress[task_id].update({
                    'status': 'downloading',
                    'percent': done_pct,
                    'phase': 'Processing...',
                    'speed': '',
                    'eta': '',
                })

        if format_id == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'ffmpeg_location': FFMPEG_DIR,
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
            }
        elif platform == 'instagram':
            # Instagram: use bestvideo+bestaudio to ensure audio is included
            # Many Instagram formats are video-only; merging guarantees audio
            fmt = 'bestvideo+bestaudio/best'
            ydl_opts = {
                'format': fmt,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_DIR,
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
            }
        else:
            height = quality.replace('p', '')
            # Prefer m4a (AAC) audio — plays everywhere, no re-encoding needed
            # Fallback to any audio if m4a not available
            fmt = (
                f'bestvideo[height<={height}]+bestaudio[ext=m4a]'
                f'/bestvideo[height<={height}]+bestaudio'
                f'/best[height<={height}]/best'
            )
            ydl_opts = {
                'format': fmt,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_DIR,
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
            }

        download_progress[task_id]['phase'] = 'Starting download...'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')

        download_progress[task_id].update({
            'percent': 88,
            'phase': 'Merging streams...',
            'speed': '',
            'eta': '',
        })

        # Find the final output file — pick the largest (merged is always biggest)
        downloaded_file = None
        candidates = []
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                full_path = os.path.join(DOWNLOAD_DIR, f)
                candidates.append((f, os.path.getsize(full_path), full_path))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            downloaded_file = candidates[0][2]

        if not downloaded_file or not os.path.exists(downloaded_file):
            download_progress[task_id].update({
                'status': 'error',
                'error': 'Download failed — file not found',
            })
            return

        # Clean up any leftover intermediate files
        for f, size, fpath in candidates:
            if fpath != downloaded_file:
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        safe_title = re.sub(r'[^\w\s\-]', '', title)[:80].strip()
        ext = os.path.splitext(downloaded_file)[1]
        download_name = f"{safe_title}{ext}"

        download_progress[task_id].update({
            'status': 'done',
            'percent': 100,
            'phase': 'Ready!',
            'filename': os.path.basename(downloaded_file),
            'download_name': download_name,
        })

    except Exception as e:
        download_progress[task_id].update({
            'status': 'error',
            'error': str(e),
        })


@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    """SSE endpoint — streams real-time progress updates."""
    def generate():
        while True:
            prog = download_progress.get(task_id, {})
            data = json.dumps(prog)
            yield f"data: {data}\n\n"

            if prog.get('status') in ('done', 'error'):
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/file/<task_id>')
def serve_file(task_id):
    """Serve the downloaded file."""
    prog = download_progress.get(task_id)
    if not prog or prog.get('status') != 'done':
        return jsonify({'error': 'File not ready'}), 404

    filename = prog.get('filename')
    download_name = prog.get('download_name', filename)
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    return send_file(filepath, as_attachment=True, download_name=download_name)


@app.route('/api/thumb')
def proxy_thumbnail():
    """Proxy external thumbnails to avoid hotlink blocks (Instagram etc)."""
    img_url = request.args.get('url', '')
    if not img_url:
        return '', 404
    try:
        req = urllib.request.Request(img_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
        return Response(data, mimetype=content_type,
                        headers={'Cache-Control': 'public, max-age=3600'})
    except Exception:
        return '', 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  🚀 Video Downloader running at http://localhost:{port}\n")
    print("  Supported: YouTube, Instagram\n")
    app.run(debug=True, host='0.0.0.0', port=port)
