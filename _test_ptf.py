"""Test pytubefix for downloading YouTube videos."""
from pytubefix import YouTube

vid_url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'

print('=== pytubefix test ===')
try:
    yt = YouTube(vid_url)
    print(f'  title: {yt.title}')
    print(f'  length: {yt.length}s')
    print(f'  views: {yt.views}')
    
    streams = yt.streams.filter(progressive=True)  # muxed streams
    print(f'\n  Progressive (muxed) streams: {len(streams)}')
    for s in streams:
        print(f'    {s.resolution}  {s.mime_type}  size={s.filesize_mb:.1f} MB  url={bool(s.url)}')
    
    streams_adaptive = yt.streams.filter(adaptive=True, mime_type='video/mp4')
    print(f'\n  Adaptive video streams: {len(streams_adaptive)}')
    for s in streams_adaptive[:5]:
        print(f'    {s.resolution}  {s.mime_type}  size={s.filesize_mb:.1f} MB  url={bool(s.url)}')
    
    # Try getting a direct URL
    best = yt.streams.get_highest_resolution()
    if best:
        print(f'\n  Best stream: {best.resolution}')
        print(f'  URL (first 120): {best.url[:120]}...')
except Exception as e:
    print(f'  FAIL: {e}')
    import traceback
    traceback.print_exc()
