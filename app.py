"""
Video Downloader — Flask backend
YouTube: pytubefix (extracts direct CDN URLs, works from datacenter IPs)
Instagram: yt-dlp
"""
from flask import Flask, request, jsonify, render_template, Response
import os
import re
import json
import urllib.parse
import urllib.request
import urllib.error
import shutil
import tempfile

# ── ffmpeg (needed for Instagram + YouTube audio conversion) ────────
FFMPEG_BIN = shutil.which('ffmpeg')
FFPROBE_BIN = shutil.which('ffprobe')

if FFMPEG_BIN:
    FFMPEG_DIR = os.path.dirname(FFMPEG_BIN)
    print(f"  ffmpeg (system): {FFMPEG_BIN}")
else:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        FFMPEG_BIN, FFPROBE_BIN = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        FFMPEG_DIR = os.path.dirname(FFMPEG_BIN)
        print(f"  ffmpeg (bundled): {FFMPEG_BIN}")
    except Exception:
        FFMPEG_BIN = 'ffmpeg'
        FFPROBE_BIN = 'ffprobe'
        FFMPEG_DIR = ''
        print("  ffmpeg not found!")

app = Flask(__name__, static_folder='static', template_folder='templates')
DOWNLOAD_DIR = tempfile.gettempdir()

# ── Instagram cookies (optional) ────────────────────────────────────
_IG_COOKIE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
_IG_COOKIE_TMP = os.path.join(tempfile.gettempdir(), 'cookies.txt')
if os.path.exists(_IG_COOKIE_SRC) and os.path.getsize(_IG_COOKIE_SRC) > 44:
    shutil.copy2(_IG_COOKIE_SRC, _IG_COOKIE_TMP)
    IG_COOKIE_OPTS = {'cookiefile': _IG_COOKIE_TMP}
else:
    IG_COOKIE_OPTS = {}


# =====================================================================
#  Helpers
# =====================================================================
def detect_platform(url):
    if re.match(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+', url):
        return 'youtube'
    if re.match(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+', url):
        return 'instagram'
    return None


def _http_get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# =====================================================================
#  YouTube — via pytubefix (works from datacenter IPs)
# =====================================================================

# Clients to try — IOS gives direct URLs for all formats;
# WEB uses PO token (auto-generated via Node.js) and works from datacenter IPs
_YT_CLIENTS = ['IOS', 'WEB', 'ANDROID_VR']


def _make_yt(url):
    """Create a pytubefix YouTube object, trying multiple clients."""
    from pytubefix import YouTube
    last_err = None
    for client in _YT_CLIENTS:
        try:
            yt = YouTube(url, client=client)
            # Force metadata + stream fetch to catch errors early
            _ = yt.title
            _ = yt.streams
            return yt
        except Exception as e:
            last_err = e
            continue
    raise last_err or Exception('All YouTube clients failed')


def get_youtube_info(url):
    """Get YouTube video info + available streams via pytubefix."""
    yt = _make_yt(url)
    title = yt.title
    channel = yt.author
    duration = yt.length  # seconds
    views = yt.views
    thumbnail = yt.thumbnail_url

    # Get like count from RYD API
    like_count = 0
    try:
        vid_id = yt.video_id
        ryd = _http_get_json(
            f'https://returnyoutubedislikeapi.com/votes?videoId={vid_id}'
        )
        like_count = ryd.get('likes', 0) or 0
    except Exception:
        pass

    # Build format list from available streams
    formats = []
    seen = set()

    # Progressive (muxed) streams — video + audio in one file
    for s in yt.streams.filter(progressive=True).order_by('resolution').desc():
        h = s.resolution  # e.g., '720p'
        if h and h not in seen:
            seen.add(h)
            height = int(h.replace('p', ''))
            formats.append({
                'quality': h,
                'height': height,
                'ext': 'mp4',
                'filesize': s.filesize or 0,
                'format_id': f'prog_{s.itag}',
                'itag': s.itag,
                'has_audio': True,
                'stream_type': 'progressive',
            })

    # Adaptive (video-only) mp4 streams — higher quality
    for s in yt.streams.filter(adaptive=True, mime_type='video/mp4').order_by('resolution').desc():
        h = s.resolution
        if h and h not in seen:
            seen.add(h)
            height = int(h.replace('p', ''))
            # Get best audio stream size for total estimate
            best_audio = yt.streams.filter(only_audio=True, mime_type='audio/mp4').order_by('abr').desc().first()
            audio_size = best_audio.filesize if best_audio else 0
            formats.append({
                'quality': h,
                'height': height,
                'ext': 'mp4',
                'filesize': (s.filesize or 0) + audio_size,
                'format_id': f'adapt_{s.itag}',
                'itag': s.itag,
                'has_audio': False,
                'stream_type': 'adaptive',
            })

    formats.sort(key=lambda x: x['height'], reverse=True)

    # Audio only
    best_audio = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
    if best_audio:
        formats.append({
            'quality': 'Audio Only (MP3)',
            'height': 0,
            'ext': 'mp3',
            'filesize': best_audio.filesize or 0,
            'format_id': f'audio_{best_audio.itag}',
            'itag': best_audio.itag,
            'has_audio': True,
            'stream_type': 'audio',
        })

    return {
        'title': title,
        'thumbnail': thumbnail,
        'duration': duration,
        'channel': channel,
        'view_count': views or 0,
        'like_count': like_count,
        'formats': formats,
        'url': url,
        'platform': 'youtube',
    }


def stream_youtube_download(url, itag, stream_type):
    """Get a pytubefix stream and proxy its CDN URL to the user."""
    yt = _make_yt(url)
    stream = yt.streams.get_by_itag(int(itag))
    if not stream:
        raise Exception('Stream not found for the selected quality')

    title = re.sub(r'[^\w\s\-]', '', yt.title)[:80].strip()
    cdn_url = stream.url
    filesize = stream.filesize

    # Determine extension
    if stream_type == 'audio':
        ext = 'mp3'  # Will be converted
        fname = f'{title}.mp3'
    else:
        ext = 'mp4'
        fname = f'{title}.mp4'

    return cdn_url, fname, filesize, stream.mime_type


# =====================================================================
#  Routes
# =====================================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def get_video_info():
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    platform = detect_platform(url)
    if not platform:
        return jsonify({'error': 'Unsupported URL — paste a YouTube or Instagram link'}), 400

    try:
        if platform == 'youtube':
            result = get_youtube_info(url)
            return jsonify(result)
        else:
            # Instagram — yt-dlp
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ffmpeg_location': FFMPEG_DIR,
                **IG_COOKIE_OPTS,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = []
            seen_q = set()
            for f in info.get('formats', []):
                h = f.get('height')
                if h and f.get('vcodec', 'none') != 'none' and h >= 144:
                    key = f'{h}p'
                    if key not in seen_q:
                        seen_q.add(key)
                        formats.append({
                            'quality': key,
                            'height': h,
                            'ext': 'mp4',
                            'filesize': f.get('filesize') or f.get('filesize_approx') or 0,
                            'format_id': key,
                            'has_audio': True,
                        })
            formats.sort(key=lambda x: x['height'], reverse=True)
            if not formats:
                formats.append({
                    'quality': 'Best Quality',
                    'height': 9999,
                    'ext': 'mp4',
                    'filesize': 0,
                    'format_id': 'insta_best',
                    'has_audio': True,
                })
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
                'platform': 'instagram',
            }
            if result['thumbnail']:
                result['thumbnail'] = '/api/thumb?url=' + urllib.parse.quote(result['thumbnail'], safe='')
            return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Failed to fetch video info: {str(e)}'}), 500


@app.route('/api/debug')
def debug_info():
    """Diagnostic endpoint — check Node.js, pytubefix, and client status."""
    import subprocess, traceback
    results = {}

    # Check Node.js from nodejs-wheel-binaries
    try:
        from pytubefix.botGuard.bot_guard import NODE_PATH, VM_PATH
        results['node_path'] = NODE_PATH
        results['node_exists'] = os.path.exists(NODE_PATH)
        results['vm_path'] = VM_PATH
        results['vm_exists'] = os.path.exists(VM_PATH)
        try:
            out = subprocess.check_output([NODE_PATH, '--version'], stderr=subprocess.PIPE, timeout=5)
            results['node_version'] = out.decode().strip()
        except Exception as e:
            results['node_error'] = str(e)
    except Exception as e:
        results['node_import_error'] = str(e)

    # Test PO token generation
    try:
        from pytubefix.botGuard.bot_guard import generate_po_token
        pot = generate_po_token('dQw4w9WgXcQ')
        results['po_token'] = pot[:40] + '...' if pot else None
    except Exception as e:
        results['po_token_error'] = str(e)

    # Test multiple clients with a non-Rick-Astley video
    from pytubefix import YouTube
    test_url = 'https://www.youtube.com/watch?v=kJQP7kiw5Fk'  # Despacito
    clients_to_test = ['WEB', 'WEB_EMBED', 'WEB_CREATOR', 'WEB_SAFARI',
                       'TV_EMBED', 'MEDIA_CONNECT', 'IOS', 'ANDROID', 'ANDROID_VR']
    for client in clients_to_test:
        try:
            yt = YouTube(test_url, client=client)
            title = yt.title
            n_streams = len(yt.streams)
            results[f'c_{client}'] = f'OK: {n_streams}s'
        except Exception as e:
            results[f'c_{client}'] = f'FAIL: {str(e)[:60]}'

    return jsonify(results)


@app.route('/api/download', methods=['POST'])
def download_video():
    """Stream YouTube video from CDN through server, or download Instagram via yt-dlp."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', '720p')
    format_id = data.get('format_id', '')
    platform = data.get('platform', detect_platform(url) or 'youtube')

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    try:
        if platform == 'youtube':
            return _download_youtube(url, format_id)
        else:
            return _download_instagram(url, quality, format_id)
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500


def _download_youtube(url, format_id):
    """Download YouTube video and stream to user's browser.
    
    For non-SABR streams: proxy the direct CDN URL.
    For SABR streams: use pytubefix's SABR downloader to a temp file, then send.
    """
    import uuid

    # Parse format_id to get itag and stream type
    # format_id is like 'prog_22', 'adapt_137', 'audio_140'
    parts = format_id.split('_', 1)
    if len(parts) != 2:
        return jsonify({'error': 'Invalid format selection'}), 400

    stream_type, itag_str = parts[0], parts[1]

    yt = _make_yt(url)
    stream = yt.streams.get_by_itag(int(itag_str))
    if not stream:
        return jsonify({'error': 'Stream not available'}), 404

    title = re.sub(r'[^\w\s\-]', '', yt.title)[:80].strip()
    filesize = stream.filesize
    mime = stream.mime_type or 'video/mp4'

    if stream_type == 'audio':
        fname = f'{title}.m4a'
        mime = stream.mime_type or 'audio/mp4'
    else:
        fname = f'{title}.mp4'

    if not stream.is_sabr:
        # Direct CDN URL — proxy it to the user
        cdn_url = stream.url

        def generate():
            req = urllib.request.Request(cdn_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                while True:
                    chunk = resp.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    yield chunk

        headers = {
            'Content-Type': mime,
            'Content-Disposition': f'attachment; filename="{fname}"',
            'Cache-Control': 'no-cache',
        }
        if filesize:
            headers['Content-Length'] = str(filesize)

        return Response(generate(), headers=headers)
    else:
        # SABR stream — download to temp file via pytubefix, then send
        tmp_name = f'dl_{uuid.uuid4().hex[:10]}.mp4'
        tmp_path = os.path.join(DOWNLOAD_DIR, tmp_name)
        stream.download(output_path=DOWNLOAD_DIR, filename=tmp_name)

        if not os.path.exists(tmp_path):
            return jsonify({'error': 'SABR download failed — file not created'}), 500

        from flask import send_file
        response = send_file(tmp_path, as_attachment=True, download_name=fname, mimetype=mime)

        @response.call_on_close
        def cleanup():
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        return response


def _download_instagram(url, quality, format_id):
    """Download Instagram video via yt-dlp and stream back."""
    import yt_dlp
    import uuid

    file_id = f'dl_{uuid.uuid4().hex[:10]}'
    output_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')

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
            'quiet': True,
            'no_warnings': True,
            **IG_COOKIE_OPTS,
        }
    else:
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'ffmpeg_location': FFMPEG_DIR,
            'quiet': True,
            'no_warnings': True,
            **IG_COOKIE_OPTS,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'video')

    # Find the output file
    candidates = []
    for f in os.listdir(DOWNLOAD_DIR):
        if f.startswith(file_id):
            fp = os.path.join(DOWNLOAD_DIR, f)
            candidates.append((f, os.path.getsize(fp), fp))

    if not candidates:
        return jsonify({'error': 'Download failed — file not found'}), 500

    candidates.sort(key=lambda x: x[1], reverse=True)
    downloaded = candidates[0][2]

    for _, _, fp in candidates:
        if fp != downloaded:
            try:
                os.remove(fp)
            except Exception:
                pass

    safe_title = re.sub(r'[^\w\s\-]', '', title)[:80].strip()
    ext = os.path.splitext(downloaded)[1]

    from flask import send_file
    response = send_file(downloaded, as_attachment=True, download_name=f'{safe_title}{ext}')

    @response.call_on_close
    def cleanup():
        try:
            os.remove(downloaded)
        except Exception:
            pass

    return response


@app.route('/api/thumb')
def proxy_thumbnail():
    img_url = request.args.get('url', '')
    if not img_url:
        return '', 404
    try:
        req = urllib.request.Request(img_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            img_data = resp.read()
            ct = resp.headers.get('Content-Type', 'image/jpeg')
        return Response(img_data, mimetype=ct, headers={'Cache-Control': 'public, max-age=3600'})
    except Exception:
        return '', 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  Video Downloader running at http://localhost:{port}\n")
    print("  Supported: YouTube, Instagram\n")
    app.run(debug=True, host='0.0.0.0', port=port)
