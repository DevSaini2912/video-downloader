from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp
import os
import uuid
import re
import json
import urllib.parse
import urllib.request
import urllib.error
import shutil
import tempfile

# ---- ffmpeg (needed for Instagram audio extraction) ----
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
        print("  ffmpeg not found!")
        FFMPEG_BIN = 'ffmpeg'
        FFPROBE_BIN = 'ffprobe'
        FFMPEG_DIR = ''

app = Flask(__name__, static_folder='static', template_folder='templates')
DOWNLOAD_DIR = tempfile.gettempdir()

# =====================================================================
#  YouTube — uses external APIs so Vercel's IP is never sent to YouTube
# =====================================================================
COBALT_API = 'https://api.cobalt.tools'

INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://vid.puffyan.us',
    'https://invidious.nerdvpn.de',
    'https://invidious.privacyredirect.com',
]

YT_QUALITY_PRESETS = [
    {'id': '2160', 'quality': '4K',    'height': 2160},
    {'id': '1440', 'quality': '1440p', 'height': 1440},
    {'id': '1080', 'quality': '1080p', 'height': 1080},
    {'id': '720',  'quality': '720p',  'height': 720},
    {'id': '480',  'quality': '480p',  'height': 480},
    {'id': '360',  'quality': '360p',  'height': 360},
]

# =====================================================================
#  Instagram — still uses yt-dlp (Instagram doesn't flag datacenter IPs)
# =====================================================================
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


def extract_video_id(url):
    for pattern in [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _http_get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def get_youtube_metadata(video_id):
    """Fetch YouTube metadata + format sizes from Invidious, falling back to oEmbed."""
    # --- Invidious (rich metadata + adaptive formats for file sizes) ---
    for instance in INVIDIOUS_INSTANCES:
        try:
            data = _http_get_json(
                f'{instance}/api/v1/videos/{video_id}'
                '?fields=title,author,lengthSeconds,videoThumbnails,viewCount,likeCount,subCountText,adaptiveFormats'
            )
            thumbs = data.get('videoThumbnails', [])
            thumb = ''
            for t in thumbs:
                if t.get('quality') in ('maxresdefault', 'sddefault', 'high'):
                    thumb = t.get('url', '')
                    break
            if not thumb and thumbs:
                thumb = thumbs[0].get('url', '')
            if thumb and thumb.startswith('/'):
                thumb = f'{instance}{thumb}'

            # Build file size map from adaptive formats: height → best size
            size_map = {}  # height → filesize in bytes
            audio_size = 0
            for af in data.get('adaptiveFormats', []):
                af_type = af.get('type', '')
                af_size = af.get('clen') or af.get('contentLength') or 0
                try:
                    af_size = int(af_size)
                except (ValueError, TypeError):
                    af_size = 0
                # Video track
                h = af.get('resolution', '').replace('p', '')
                if h and h.isdigit() and 'video' in af_type:
                    h = int(h)
                    if h not in size_map or af_size > size_map[h]:
                        size_map[h] = af_size
                # Audio track (biggest = best quality)
                if 'audio' in af_type and af_size > audio_size:
                    audio_size = af_size

            return {
                'title': data.get('title', 'Unknown'),
                'channel': data.get('author', 'Unknown'),
                'duration': data.get('lengthSeconds', 0),
                'thumbnail': thumb,
                'view_count': data.get('viewCount', 0) or 0,
                'like_count': data.get('likeCount', 0) or 0,
                '_size_map': size_map,
                '_audio_size': audio_size,
            }
        except Exception:
            continue

    # --- oEmbed fallback (very reliable, less detail) ---
    try:
        data = _http_get_json(
            f'https://www.youtube.com/oembed?url=https://youtube.com/watch?v={video_id}&format=json'
        )
        return {
            'title': data.get('title', 'Unknown'),
            'channel': data.get('author_name', 'Unknown'),
            'duration': 0,
            'thumbnail': f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
            'view_count': 0,
            'like_count': 0,
            '_size_map': {},
            '_audio_size': 0,
        }
    except Exception:
        pass

    # --- Last resort ---
    return None


def cobalt_get_url(video_url, quality='1080', audio_only=False):
    """Call cobalt.tools API → returns (download_url, filename)."""
    body = {
        'url': video_url,
        'videoQuality': str(quality),
        'filenameStyle': 'pretty',
    }
    if audio_only:
        body['downloadMode'] = 'audio'
        body['audioFormat'] = 'mp3'

    payload = json.dumps(body).encode()
    req = urllib.request.Request(f'{COBALT_API}/', data=payload, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0',
    })

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode())
            code = err_body.get('error', {}).get('code', f'HTTP {e.code}')
        except Exception:
            code = f'HTTP {e.code}'
        raise Exception(f'Download service error: {code}')

    status = data.get('status')
    if status in ('redirect', 'tunnel', 'stream'):
        return data['url'], data.get('filename', 'video.mp4')
    if status == 'picker':
        picker = data.get('picker', [])
        if picker:
            return picker[0]['url'], 'video.mp4'

    error = data.get('error', {})
    raise Exception(error.get('code', 'Download service returned an unexpected response'))


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
        # ---- YouTube — metadata from Invidious/oEmbed ----
        if platform == 'youtube':
            vid = extract_video_id(url)
            if not vid:
                return jsonify({'error': 'Could not parse YouTube video ID from URL'}), 400

            meta = get_youtube_metadata(vid)
            if not meta:
                return jsonify({'error': 'Could not fetch video info — please try again'}), 500

            size_map = meta.pop('_size_map', {})
            audio_size = meta.pop('_audio_size', 0)

            # Build formats with real file sizes (video + best audio)
            formats = []
            for q in YT_QUALITY_PRESETS:
                v_size = size_map.get(q['height'], 0)
                # Estimated total = video track + audio track
                total = (v_size + audio_size) if v_size else 0
                formats.append({
                    'quality': q['quality'],
                    'height': q['height'],
                    'ext': 'mp4',
                    'filesize': total,
                    'format_id': q['id'],
                    'has_audio': True,
                })

            formats.append({
                'quality': 'Audio Only (MP3)',
                'height': 0,
                'ext': 'mp3',
                'filesize': audio_size,
                'format_id': 'audio',
                'has_audio': True,
            })

            return jsonify({**meta, 'formats': formats, 'url': url, 'platform': 'youtube'})

        # ---- Instagram — yt-dlp ----
        else:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ffmpeg_location': FFMPEG_DIR,
                **IG_COOKIE_OPTS,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            formats = []
            seen = set()
            for f in info.get('formats', []):
                h = f.get('height')
                if h and f.get('vcodec', 'none') != 'none' and h >= 144:
                    key = f'{h}p'
                    if key not in seen:
                        seen.add(key)
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


@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', '720p')
    format_id = data.get('format_id', '')
    platform = data.get('platform', detect_platform(url) or 'youtube')

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    # ---- YouTube — via cobalt (returns a redirect URL, no server-side download) ----
    if platform == 'youtube':
        try:
            is_audio = (format_id == 'audio')
            q = format_id if not is_audio else '320'
            download_url, filename = cobalt_get_url(url, q, is_audio)
            return jsonify({'download_url': download_url, 'filename': filename})
        except Exception as e:
            return jsonify({'error': f'Download failed: {str(e)}'}), 500

    # ---- Instagram — yt-dlp downloads on server, streams file back ----
    file_id = f'dl_{uuid.uuid4().hex[:10]}'
    output_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')

    try:
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
        response = send_file(downloaded, as_attachment=True, download_name=f'{safe_title}{ext}')

        @response.call_on_close
        def cleanup():
            try:
                os.remove(downloaded)
            except Exception:
                pass

        return response

    except Exception as e:
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except Exception:
                    pass
        return jsonify({'error': f'Download failed: {str(e)}'}), 500


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
