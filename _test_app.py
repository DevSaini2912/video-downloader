import json, sys
sys.path.insert(0, '.')
from app import get_youtube_info

r = get_youtube_info('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
print(json.dumps({k:v for k,v in r.items() if k != 'formats'}, indent=2))
print(f"\nFormats: {len(r['formats'])}")
for f in r['formats']:
    sz = f'{f["filesize"]:>12,}' if f['filesize'] else '     unknown'
    print(f"  {f['quality']:20s} {sz} bytes  itag={f['itag']}  type={f.get('stream_type','')}")
