"""Test the exact video that was failing with bot detection"""
import urllib.request, json

url = 'https://downloder-five.vercel.app/api/info'
data = json.dumps({'url': 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'}).encode()
headers = {'Content-Type': 'application/json'}

req = urllib.request.Request(url, data=data, headers=headers)
try:
    resp = urllib.request.urlopen(req, timeout=60)
    d = json.loads(resp.read())
    print(f"Title: {d['title']}")
    print(f"Duration: {d['duration']}s")
    print(f"Views: {d['view_count']:,}")
    print(f"\nFormats: {len(d['formats'])}")
    for f in d['formats']:
        sz = f"{f['filesize']:>12,}" if f['filesize'] else "     unknown"
        print(f"  {f['quality']:20s} {sz} bytes")
    print("\n SUCCESS - bot detection bypassed!")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:500]}")
except Exception as e:
    print(f"Error: {e}")
