"""Quick test: download first 1KB via the proxy approach used in app.py"""
import sys, urllib.request
sys.path.insert(0, '.')

from pytubefix import YouTube

yt = YouTube('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
# Test progressive stream (360p, itag 18)
stream = yt.streams.get_by_itag(18)
print(f"Stream: {stream.resolution} {stream.mime_type} {stream.filesize:,} bytes")
print(f"CDN URL: {stream.url[:120]}...")

# Simulate proxy download (just first 1KB)
req = urllib.request.Request(stream.url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = resp.read(1024)
    print(f"\nProxy download test: got {len(data)} bytes")
    print(f"Status: {resp.status}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print(f"Content-Length: {resp.headers.get('Content-Length')}")
    print("SUCCESS - proxy streaming works!")
