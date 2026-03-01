"""Test: parse WEB client vid_info directly for all stream URLs"""
from pytubefix import YouTube

video_id = '3FZ2f5S9GGs'
url = f'https://www.youtube.com/watch?v={video_id}'

yt = YouTube(url, client='WEB')
vi = yt.vid_info

sd = vi.get('streamingData', {})
muxed = sd.get('formats', [])
adaptive = sd.get('adaptiveFormats', [])

print(f"Muxed formats: {len(muxed)}")
for f in muxed:
    itag = f.get('itag')
    mime = f.get('mimeType', '')
    w = f.get('width', '?')
    h = f.get('height', '?')
    sz = int(f.get('contentLength', 0))
    has_url = 'url' in f
    has_sig = 'signatureCipher' in f
    print(f"  itag={itag:4d}  {w}x{h}  {sz:>12,}B  mime={mime[:30]}  url={'YES' if has_url else 'NO '}  sig={'YES' if has_sig else 'NO '}")

print(f"\nAdaptive formats: {len(adaptive)}")
for f in adaptive:
    itag = f.get('itag')
    mime = f.get('mimeType', '')
    w = f.get('width', 0)
    h = f.get('height', 0)
    sz = int(f.get('contentLength', 0))
    has_url = 'url' in f
    has_sig = 'signatureCipher' in f
    q = f.get('qualityLabel', f.get('quality', '?'))
    abr = f.get('averageBitrate', 0)
    
    if h:
        label = f"{h}p"
    else:
        label = f"audio {abr//1000}kbps"
    print(f"  itag={itag:4d}  {label:12s}  {sz:>12,}B  url={'YES' if has_url else 'NO '}  sig={'YES' if has_sig else 'NO '}  {mime[:40]}")

# Test if a URL actually works
print("\nTesting first URL...")
import urllib.request
sample = next((f for f in muxed + adaptive if 'url' in f), None)
if sample:
    req = urllib.request.Request(sample['url'], method='HEAD', headers={
        'User-Agent': 'Mozilla/5.0'
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        print(f"  Status: {resp.status}")
        print(f"  Content-Type: {resp.headers.get('Content-Type')}")
        print(f"  Content-Length: {resp.headers.get('Content-Length')}")
        print("  URL WORKS!")
    except Exception as e:
        print(f"  Failed: {e}")
else:
    print("  No URLs found!")
