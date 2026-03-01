"""
Video Downloader — Flask backend
YouTube: yt-dlp (local) with oEmbed + RYD API fallback for metadata
Instagram: yt-dlp
"""
from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp
import os
import uuid
import re
import json
import math
import urllib.parse
import urllib.request
import urllib.error
import shutil
import tempfile

# ── ffmpeg ──────────────────────────────────────────────────────────
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

# ── yt-dlp options for YouTube ──────────────────────────────────────
YT_DLP_OPTS = {
    'extractor_args': {
        'youtube': {'player_client': ['tv_embedded', 'mediaconnect', 'android']},
    },
}

# ── Quality presets (with estimated bitrates in MB/min for size estimation) ──
QUALITY_PRESETS = [
    {'id': '2160', 'quality': '4K',    'height': 2160, 'mbpm': 25.0},
    {'id': '1440', 'quality': '1440p', 'height': 1440, 'mbpm': 12.0},
    {'id': '1080', 'quality': '1080p', 'height': 1080, 'mbpm': 5.5},
    {'id': '720',  'quality': '720p',  'height': 720,  'mbpm': 2.8},
    {'id': '480',  'quality': '480p',  'height': 480,  'mbpm': 1.2},
    {'id': '360',  'quality': '360p',  'height': 360,  'mbpm': 0.6},
]


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
    for pat in [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _http_get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _estimate_filesize(duration_sec, mbpm):
    """Estimate file size in bytes from duration and MB/min rate."""
    if not duration_sec:
        return 0
    minutes = duration_sec / 60.0
    return int(mbpm * minutes * 1024 * 1024)


# ── YouTube metadata: try yt-dlp first, fall back to oEmbed + RYD ──
def get_youtube_info_ytdlp(url):
    """Use yt-dlp to get full metadata + real format sizes. Works locally."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': FFMPEG_DIR,
        **YT_DLP_OPTS,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Build format list with real sizes
    formats = []
    seen = set()
    for f in info.get('formats', []):
        h = f.get('height')
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        if h and vcodec != 'none' and h >= 144:
            key = f'{h}p'
            if key not in seen:
                seen.add(key)
                formats.append({
                    'quality': key,
                    'height': h,
                    'ext': 'mp4',
                    'filesize': f.get('filesize') or f.get('filesize_approx') or 0,
                    'format_id': f.get('format_id', key),
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

    return {
        'title': info.get('title', 'Unknown'),
        'thumbnail': info.get('thumbnail', ''),
        'duration': info.get('duration', 0),
        'channel': info.get('channel', info.get('uploader', 'Unknown')),
        'view_count': info.get('view_count', 0) or 0,
        'like_count': info.get('like_count', 0) or 0,
        'formats': formats,
        'url': url,
        'platform': 'youtube',
        '_source': 'ytdlp',
    }


def _scrape_youtube_page(video_id):
    """Fetch YouTube watch page HTML and extract ytInitialPlayerResponse.
    Works from datacenter IPs — YouTube serves the page, it only blocks streams."""
    watch_url = f'https://www.youtube.com/watch?v={video_id}'
    req = urllib.request.Request(watch_url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode('utf-8', errors='replace')

    # Extract ytInitialPlayerResponse JSON
    m = re.search(r'var\s+ytInitialPlayerResponse\s*=\s*(\{.+?\});', html)
    if not m:
        m = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\});', html)
    if not m:
        return None
    return json.loads(m.group(1))


def get_youtube_info_fallback(video_id, url):
    """Scrape YouTube watch page for full metadata + real file sizes.
    Falls back to oEmbed + RYD if scraping fails."""
    title = 'Unknown'
    channel = 'Unknown'
    thumbnail = f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
    duration = 0
    view_count = 0
    like_count = 0
    real_sizes = {}   # height → filesize in bytes (video track only)
    best_audio_size = 0

    # ── Strategy A: Scrape YouTube watch page (best data) ──
    try:
        player = _scrape_youtube_page(video_id)
        if player:
            vd = player.get('videoDetails', {})
            title = vd.get('title', title)
            channel = vd.get('author', channel)
            duration = int(vd.get('lengthSeconds', 0) or 0)
            view_count = int(vd.get('viewCount', 0) or 0)

            thumbs = vd.get('thumbnail', {}).get('thumbnails', [])
            if thumbs:
                thumbnail = thumbs[-1].get('url', thumbnail)

            # Extract real file sizes from adaptiveFormats
            for af in player.get('streamingData', {}).get('adaptiveFormats', []):
                cl = af.get('contentLength')
                if not cl:
                    continue
                cl = int(cl)
                mime = af.get('mimeType', '')
                ql = af.get('qualityLabel', '')

                if 'video' in mime:
                    h = af.get('height', 0)
                    if h and (h not in real_sizes or cl > real_sizes[h]):
                        real_sizes[h] = cl
                elif 'audio' in mime:
                    if cl > best_audio_size:
                        best_audio_size = cl
    except Exception:
        pass

    # ── Strategy B: oEmbed for title/channel (if scraping failed) ──
    if title == 'Unknown':
        try:
            oembed = _http_get_json(
                f'https://www.youtube.com/oembed?url=https://youtube.com/watch?v={video_id}&format=json'
            )
            title = oembed.get('title', title)
            channel = oembed.get('author_name', channel)
        except Exception:
            pass

    # ── Strategy C: RYD API for views + likes (supplement or fallback) ──
    try:
        ryd = _http_get_json(
            f'https://returnyoutubedislikeapi.com/votes?videoId={video_id}'
        )
        if not view_count:
            view_count = ryd.get('viewCount', 0) or 0
        like_count = ryd.get('likes', 0) or 0
    except Exception:
        pass

    # Build format list with real sizes (scraped) or estimated sizes
    formats = []
    for q in QUALITY_PRESETS:
        h = q['height']
        if h in real_sizes:
            # Real size = video track + audio track
            fsize = real_sizes[h] + best_audio_size
        elif duration:
            fsize = _estimate_filesize(duration, q['mbpm'])
        else:
            fsize = 0
        formats.append({
            'quality': q['quality'],
            'height': h,
            'ext': 'mp4',
            'filesize': fsize,
            'format_id': q['id'],
            'has_audio': True,
        })
    formats.append({
        'quality': 'Audio Only (MP3)',
        'height': 0,
        'ext': 'mp3',
        'filesize': best_audio_size or (_estimate_filesize(duration, 0.25) if duration else 0),
        'format_id': 'audio',
        'has_audio': True,
    })

    return {
        'title': title,
        'thumbnail': thumbnail,
        'duration': duration,
        'channel': channel,
        'view_count': view_count,
        'like_count': like_count,
        'formats': formats,
        'url': url,
        'platform': 'youtube',
        '_source': 'fallback',
    }


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
            vid = extract_video_id(url)
            if not vid:
                return jsonify({'error': 'Could not parse YouTube video ID from URL'}), 400

            # Strategy 1: yt-dlp (full data — works locally / clean IPs)
            try:
                result = get_youtube_info_ytdlp(url)
                return jsonify(result)
            except Exception:
                pass

            # Strategy 2: oEmbed + RYD fallback (works everywhere)
            result = get_youtube_info_fallback(vid, url)
            if result['title'] == 'Unknown':
                return jsonify({'error': 'Could not fetch video info — please check the URL'}), 500
            return jsonify(result)

        else:
            # Instagram — yt-dlp
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
    """Download via yt-dlp and stream file back."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', '720p')
    format_id = data.get('format_id', '')
    platform = data.get('platform', detect_platform(url) or 'youtube')

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

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
                **(IG_COOKIE_OPTS if platform == 'instagram' else {}),
                **(YT_DLP_OPTS if platform == 'youtube' else {}),
            }
        elif platform == 'instagram':
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_DIR,
                'quiet': True,
                'no_warnings': True,
                **IG_COOKIE_OPTS,
            }
        else:
            # YouTube video — map quality or use format_id
            height = quality.replace('p', '').replace('K', '').replace('4', '2160')
            if height == '4':
                height = '2160'
            elif not height.isdigit():
                height = '720'
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
                'quiet': True,
                'no_warnings': True,
                **YT_DLP_OPTS,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')

        # Find the final output file
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
        # Clean up partial files
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except Exception:
                    pass

        err_msg = str(e)
        if 'Sign in to confirm' in err_msg or 'bot' in err_msg.lower():
            return jsonify({
                'error': 'YouTube is blocking this server\'s IP. '
                         'Try running the app locally with "python app.py" for full functionality.'
            }), 503
        return jsonify({'error': f'Download failed: {err_msg}'}), 500


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
