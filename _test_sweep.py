"""Quick sweep: which clients work RIGHT NOW?"""
from pytubefix import YouTube

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
clients = ['IOS', 'ANDROID_VR', 'ANDROID_MUSIC', 'ANDROID_CREATOR', 
           'TV', 'TV_EMBED', 'MEDIA_CONNECT', 'WEB_CREATOR', 'WEB_KIDS',
           'ANDROID_TESTSUITE', 'WEB']

for c in clients:
    try:
        yt = YouTube(url, client=c)
        title = yt.title
        count = len(yt.streams)
        # Check a stream
        s = yt.streams.first()
        has_url = bool(s and s.url) if s else False
        sabr = s.is_sabr if s else '?'
        print(f"  {c:25s}  OK  streams={count:2d}  url={'Y' if has_url else 'N'}  sabr={sabr}")
    except Exception as e:
        err = str(e).split('\n')[0][:80]
        print(f"  {c:25s}  FAIL: {err}")
