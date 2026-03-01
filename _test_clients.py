"""Test which pytubefix clients work for this video"""
from pytubefix import YouTube
import traceback

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'

# Clients that don't require PO tokens
clients = ['IOS', 'ANDROID_VR', 'ANDROID_MUSIC', 'ANDROID_CREATOR', 
           'TV_EMBED', 'MEDIA_CONNECT', 'WEB_CREATOR', 'WEB_KIDS',
           'ANDROID_TESTSUITE', 'ANDROID_PRODUCER', 'TV']

for c in clients:
    try:
        yt = YouTube(url, client=c)
        title = yt.title
        streams = yt.streams
        count = len(streams)
        # Check if any stream has a URL
        s = streams.first()
        has_url = bool(s and s.url) if s else False
        print(f"  {c:25s}  streams={count:2d}  url={'YES' if has_url else 'NO '}  title={title[:40]}")
    except Exception as e:
        err = str(e)[:80]
        print(f"  {c:25s}  FAILED: {err}")
