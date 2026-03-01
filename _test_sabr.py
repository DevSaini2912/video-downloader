"""Test: can we download from serverAbrStreamingUrl?"""
import urllib.request
from pytubefix import YouTube

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='WEB')
vi = yt.vid_info
sd = vi.get('streamingData', {})
sabr_url = sd.get('serverAbrStreamingUrl', '')

print(f"serverAbrStreamingUrl: {sabr_url[:150]}...")

# Also check if pytubefix has SABR support
import pytubefix.sabr as sabr_mod
import os
sabr_dir = os.path.dirname(sabr_mod.__file__)
print(f"\npytubefix SABR module files:")
for root, dirs, files in os.walk(sabr_dir):
    for f in files:
        if f.endswith('.py'):
            rel = os.path.relpath(os.path.join(root, f), sabr_dir)
            print(f"  {rel}")

# Check if YouTube class has SABR-related methods
import inspect
yt_methods = [m for m in dir(yt) if 'sabr' in m.lower() or 'abr' in m.lower() or 'server' in m.lower()]
print(f"\nYouTube SABR-related methods: {yt_methods}")

# Try to use pytubefix streams with 'WEB' - it failed with cipher error before,
# but maybe there's a SABR path
print("\nChecking if WEB client has SABR streams...")
try:
    streams = yt.streams
    print(f"  Streams: {len(streams)}")
except Exception as e:
    err_str = str(e)[:200]
    print(f"  Error: {err_str}")

# Also test: yt-dlp with player_client=ios and PO token for authentication only
print("\n--- yt-dlp with ios client ---")
import yt_dlp
ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'format': 'best[height<=720]/best',
    'extractor_args': {
        'youtube': {
            'player_client': ['ios'],
        }
    },
}
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    print(f"  Title: {info.get('title')}")
    fmts = info.get('formats', [])
    print(f"  Formats: {len(fmts)}")
    for f in fmts[:5]:
        print(f"  {f.get('format_id'):8s}  {f.get('height','?'):>6}  {f.get('ext'):5s}  url={'Y' if f.get('url') else 'N'}")
except Exception as e:
    print(f"  Failed: {e}")

# Try mweb client with yt-dlp
print("\n--- yt-dlp with mweb client ---")
ydl_opts['extractor_args']['youtube']['player_client'] = ['mweb']
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    print(f"  Title: {info.get('title')}")
    fmts = info.get('formats', [])
    print(f"  Formats: {len(fmts)}")
except Exception as e:
    print(f"  Failed: {e}")
