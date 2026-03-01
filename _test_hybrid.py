"""Test: generate PO token via pytubefix botGuard, then use with yt-dlp"""
import json

# 1. Generate PO token via pytubefix's botGuard (uses Node.js)
from pytubefix.botGuard.bot_guard import generate_po_token
from pytubefix import YouTube

video_id = '3FZ2f5S9GGs'

print("1. Generating PO token via botGuard...")
try:
    po_token = generate_po_token(video_id)
    print(f"   PO token: {po_token[:40]}..." if po_token else "   PO token: None")
except Exception as e:
    print(f"   Failed: {e}")
    po_token = None

# 2. Get visitor data
print("\n2. Getting visitor data...")
try:
    yt = YouTube(f'https://www.youtube.com/watch?v={video_id}', client='IOS')
    vd = yt.visitor_data
    print(f"   Visitor data: {vd[:40]}..." if vd else "   Visitor data: None")
except Exception as e:
    print(f"   Failed: {e}")
    vd = None

# 3. Try yt-dlp with PO token
if po_token and vd:
    print("\n3. Testing yt-dlp with PO token...")
    import yt_dlp
    
    po_arg = f'web+{vd}/{po_token}'
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web'],
                'po_token': [po_arg],
            }
        },
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
        print(f"   Title: {info.get('title', 'N/A')}")
        print(f"   Formats: {len(info.get('formats', []))}")
        for f in info.get('formats', [])[:3]:
            h = f.get('height', '?')
            sz = f.get('filesize', 0) or 0
            print(f"   {h}p  {sz:>12,} bytes  {f.get('ext')}")
        print("   SUCCESS!")
    except Exception as e:
        print(f"   yt-dlp failed: {e}")
else:
    print("\n3. Skipped (no PO token or visitor data)")

# 4. Also try: pytubefix WEB client raw vid_info (bypass cipher)
print("\n4. Testing pytubefix WEB raw vid_info...")
try:
    yt2 = YouTube(f'https://www.youtube.com/watch?v={video_id}', client='WEB')
    # Access vid_info directly (before fmt_streams parses streams)
    vi = yt2.vid_info
    status = vi.get('playabilityStatus', {}).get('status', 'unknown')
    print(f"   Playability status: {status}")
    
    sd = vi.get('streamingData', {})
    fmts = sd.get('formats', []) + sd.get('adaptiveFormats', [])
    print(f"   Total formats in raw response: {len(fmts)}")
    
    # Check if URLs are already present (no cipher needed)
    urls_present = sum(1 for f in fmts if 'url' in f)
    cipher_present = sum(1 for f in fmts if 'signatureCipher' in f)
    print(f"   With direct URL: {urls_present}")
    print(f"   With signatureCipher: {cipher_present}")
    
    if urls_present > 0:
        f = next(f for f in fmts if 'url' in f)
        print(f"   Sample URL starts with: {f['url'][:80]}...")
        print("   SUCCESS - URLs already decrypted!")
    elif cipher_present > 0:
        print("   URLs are encrypted (need cipher)")
except Exception as e:
    print(f"   Failed: {e}")
