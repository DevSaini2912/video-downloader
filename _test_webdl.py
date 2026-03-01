"""Test WEB client download - it seems to work now!"""
from pytubefix import YouTube
import tempfile, os, time

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='WEB')
print(f"Title: {yt.title[:50]}")
print(f"Streams: {len(yt.streams)}")

# Show first few
for s in yt.streams.filter(type='video', mime_type='video/mp4')[:5]:
    print(f"  {s.resolution:6s} {s.filesize:>12,}B  sabr={s.is_sabr}  prog={s.is_progressive}")

# Try downloading smallest progressive
prog = yt.streams.filter(progressive=True).first()
if prog:
    print(f"\nTest download: {prog.resolution} {prog.filesize:,}B")
    t = time.time()
    path = prog.download(output_path=tempfile.gettempdir(), filename='_web_test.mp4')
    elapsed = time.time() - t
    if path and os.path.exists(path):
        sz = os.path.getsize(path)
        print(f"Downloaded {sz:,} bytes in {elapsed:.1f}s ({sz/elapsed/1024/1024:.1f} MB/s)")
        os.remove(path)
        print("WEB DOWNLOAD WORKS!")
    else:
        print("No file")
else:
    print("No progressive streams")
