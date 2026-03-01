"""Quick test: can IOS client still download normally?"""
from pytubefix import YouTube
import tempfile, os, time

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='IOS')

# Get smallest stream
streams = yt.streams.filter(progressive=True)
s = streams.first()
print(f"Stream: {s.resolution} {s.mime_type} {s.filesize:,}B is_sabr={s.is_sabr}")
print(f"URL starts with: {s.url[:120]}...")

# Try download
output = tempfile.gettempdir()
try:
    t = time.time()
    path = s.download(output_path=output, filename='_ios_test.mp4')
    elapsed = time.time() - t
    if path and os.path.exists(path):
        sz = os.path.getsize(path)
        print(f"\nDownloaded {sz:,} bytes in {elapsed:.1f}s")
        print(f"Speed: {sz/elapsed/1024/1024:.1f} MB/s")
        print("IOS DOWNLOAD WORKS!")
        os.remove(path)
    else:
        print("No file")
except Exception as e:
    print(f"Failed: {e}")
