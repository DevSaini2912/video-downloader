from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp
import os
import uuid
import re
import urllib.parse
import urllib.request
import shutil
import tempfile

# Find ffmpeg — prefer system install, fall back to static_ffmpeg pip package
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
        print("  ffmpeg not found! Install ffmpeg or pip install static-ffmpeg")
        FFMPEG_BIN = 'ffmpeg'
        FFPROBE_BIN = 'ffprobe'
        FFMPEG_DIR = ''

app = Flask(__name__, static_folder='static', template_folder='templates')

# Use /tmp for serverless (Vercel), works locally too
DOWNLOAD_DIR = tempfile.gettempdir()

# YouTube anti-bot config
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
if os.path.exists(COOKIE_FILE):
    COOKIE_OPTS = {'cookiefile': COOKIE_FILE}
    print("  Using cookies from cookies.txt")
else:
    COOKIE_OPTS = {}
    print("  No cookies.txt — using yt-dlp default extraction")

# Extra yt-dlp options to avoid bot detection on YouTube
YT_EXTRA_OPTS = {
    'extractor_args': {'youtube': {'player_client': ['tv_embedded', 'mediaconnect', 'android']}},
}


def detect_platform(url):
    """Detect which platform a URL belongs to."""
    if re.match(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+', url):
        return 'youtube'
    if re.match(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+', url):
        return 'instagram'
    return None


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
            **COOKIE_OPTS,
            **(YT_EXTRA_OPTS if platform == 'youtube' else {}),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        seen_qualities = set()

        if platform == 'instagram':
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
        else:
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

        if platform == 'instagram' and result['thumbnail']:
            result['thumbnail'] = '/api/thumb?url=' + urllib.parse.quote(result['thumbnail'], safe='')

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Failed to fetch video info: {str(e)}'}), 500


@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video and stream it back (serverless-compatible, no background threads)."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', '720p')
    format_id = data.get('format_id', '')

    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400

    platform = data.get('platform', detect_platform(url) or 'youtube')

    file_id = f"dl_{uuid.uuid4().hex[:10]}"
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
                **COOKIE_OPTS,
                **(YT_EXTRA_OPTS if platform == 'youtube' else {}),
            }
        elif platform == 'instagram':
            fmt = 'bestvideo+bestaudio/best'
            ydl_opts = {
                'format': fmt,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'ffmpeg_location': FFMPEG_DIR,
                'quiet': True,
                'no_warnings': True,
                **COOKIE_OPTS,
            }
        else:
            height = quality.replace('p', '')
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
                **COOKIE_OPTS,
                **YT_EXTRA_OPTS,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')

        # Find the final output file — pick the largest
        candidates = []
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                full_path = os.path.join(DOWNLOAD_DIR, f)
                candidates.append((f, os.path.getsize(full_path), full_path))

        if not candidates:
            return jsonify({'error': 'Download failed — file not found'}), 500

        candidates.sort(key=lambda x: x[1], reverse=True)
        downloaded_file = candidates[0][2]

        # Clean up intermediate files
        for f, size, fpath in candidates:
            if fpath != downloaded_file:
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        safe_title = re.sub(r'[^\w\s\-]', '', title)[:80].strip()
        ext = os.path.splitext(downloaded_file)[1]
        download_name = f"{safe_title}{ext}"

        response = send_file(
            downloaded_file,
            as_attachment=True,
            download_name=download_name,
        )

        @response.call_on_close
        def cleanup():
            try:
                os.remove(downloaded_file)
            except Exception:
                pass

        return response

    except Exception as e:
        # Clean up any partial files
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except Exception:
                    pass
        return jsonify({'error': f'Download failed: {str(e)}'}), 500


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
            img_data = resp.read()
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
        return Response(img_data, mimetype=content_type,
                        headers={'Cache-Control': 'public, max-age=3600'})
    except Exception:
        return '', 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  Video Downloader running at http://localhost:{port}\n")
    print("  Supported: YouTube, Instagram\n")
    app.run(debug=True, host='0.0.0.0', port=port)
