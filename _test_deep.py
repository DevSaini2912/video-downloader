"""Check what keys adaptive formats have (they don't have url or signatureCipher)"""
from pytubefix import YouTube

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='WEB')
vi = yt.vid_info
sd = vi.get('streamingData', {})

# Check serverAbrStreamingUrl
if 'serverAbrStreamingUrl' in sd:
    sabr = sd['serverAbrStreamingUrl']
    print(f"serverAbrStreamingUrl: {sabr[:120]}...")
else:
    print("No serverAbrStreamingUrl")

# Check keys in adaptive formats
adaptive = sd.get('adaptiveFormats', [])
if adaptive:
    f0 = adaptive[0]
    print(f"\nFirst adaptive format keys: {sorted(f0.keys())}")
    # Check for any URL-like key
    for k in f0.keys():
        v = str(f0[k])
        if 'http' in v.lower() or 'url' in k.lower():
            print(f"  {k}: {v[:120]}")

# Also try yt-dlp with PO token and list-formats
print("\n--- yt-dlp with PO token (list formats) ---")
from pytubefix.botGuard.bot_guard import generate_po_token

po_token = generate_po_token('3FZ2f5S9GGs')
vd = yt.visitor_data

import yt_dlp
po_arg = f'web+{vd}/{po_token}'
ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'format': 'best',
    'extractor_args': {
        'youtube': {
            'player_client': ['web'],
            'po_token': [po_arg],
        }
    },
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f'https://www.youtube.com/watch?v=3FZ2f5S9GGs', download=False)
    print(f"Title: {info.get('title')}")
    print(f"Formats: {len(info.get('formats', []))}")
    for f in info.get('formats', []):
        h = f.get('height', '')
        ext = f.get('ext', '?')
        sz = f.get('filesize') or f.get('filesize_approx') or 0
        fmt_id = f.get('format_id', '?')
        has_url = bool(f.get('url'))
        print(f"  {fmt_id:8s}  {h or 'audio':>6}  {ext:5s}  {sz:>12,}B  url={'Y' if has_url else 'N'}")
except Exception as e:
    print(f"Failed: {e}")
    
    # Try with different format
    print("\nRetrying with format='bestvideo+bestaudio/best'...")
    ydl_opts['format'] = 'bestvideo+bestaudio/best'
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v=3FZ2f5S9GGs', download=False)
        print(f"Title: {info.get('title')}")
        print(f"Formats: {len(info.get('formats', []))}")
    except Exception as e2:
        print(f"Also failed: {e2}")
