import sys; sys.path.insert(0, '.')
from app import get_youtube_info
r = get_youtube_info('https://www.youtube.com/watch?v=3FZ2f5S9GGs')
print(f"Title: {r['title'][:50]}")
print(f"Formats: {len(r['formats'])}")
for f in r['formats'][:5]:
    sz = f"{f['filesize']:>12,}" if f['filesize'] else "     unknown"
    print(f"  {f['quality']:15s} {sz} bytes")
print("SUCCESS")
