"""Test: bypass cipher by creating streams directly from vid_info for SABR"""
from pytubefix import YouTube, Stream, extract
from pytubefix.innertube import InnerTube
from pytubefix.monostate import Monostate

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='WEB')

# Step 1: Get stream data (this works)
sd = yt.streaming_data
print(f"streamingData keys: {list(sd.keys())}")

# Step 2: Apply descrambler (this works, sets url=serverAbrStreamingUrl for SABR)
stream_manifest = extract.apply_descrambler(sd)
print(f"\nTotal streams after descrambler: {len(stream_manifest)}")

# Count SABR vs non-SABR
sabr_count = sum(1 for s in stream_manifest if s.get('is_sabr'))
non_sabr = sum(1 for s in stream_manifest if not s.get('is_sabr'))
print(f"SABR streams: {sabr_count}, Non-SABR: {non_sabr}")

# Check if all have URLs now
with_url = sum(1 for s in stream_manifest if 'url' in s)
print(f"With URL: {with_url}")

# Step 3: SKIP apply_signature (since all are SABR, no cipher needed)
# Step 4: Apply PO token
if yt.po_token:
    extract.apply_po_token(stream_manifest, yt.vid_info, yt.po_token)
    print(f"\nPO token applied")

# Step 5: Build Stream objects
monostate = yt.stream_monostate
streams = []
for s_data in stream_manifest:
    try:
        stream = Stream(
            stream=s_data,
            monostate=monostate,
            po_token=yt.po_token,
            video_playback_ustreamer_config=yt.video_playback_ustreamer_config
        )
        streams.append(stream)
    except Exception as e:
        itag = s_data.get('itag', '?')
        print(f"  Failed to create stream itag={itag}: {e}")

print(f"\nCreated {len(streams)} Stream objects")

# Show what we got
for s in streams:
    is_video = s.type == 'video'
    if is_video:
        print(f"  {s.resolution:6s}  {s.filesize:>12,}B  sabr={s.is_sabr}  {s.mime_type[:30]}")
    else:
        print(f"  audio   {s.filesize:>12,}B  sabr={s.is_sabr}  {s.mime_type[:30]}")

# Test download of one stream to verify
print("\nTesting SABR download of 360p...")
import io
s360 = next((s for s in streams if s.resolution == '360p' and 'mp4' in s.mime_type), None)
if s360:
    print(f"  itag={s360.itag}, filesize={s360.filesize:,}, is_sabr={s360.is_sabr}")
    print(f"  URL: {s360.url[:100]}...")
    
    # Try downloading first 100KB to buffer
    buf = io.BytesIO()
    try:
        s360.stream_to_buffer(buf)
        buf.seek(0)
        data = buf.read(1024)
        print(f"  Got {buf.tell()} total bytes")
        print(f"  First 20 bytes: {data[:20].hex()}")
        print("  SABR DOWNLOAD WORKS!")
    except Exception as e:
        print(f"  stream_to_buffer failed: {e}")
        # Try SABR download
        print("  Trying SABR download directly...")
        try:
            from pytubefix.sabr.core.server_abr_stream import ServerAbrStream
            chunks = []
            state = {'total': 0}
            def collector(chunk, remaining):
                chunks.append(chunk)
                state['total'] += len(chunk)
                if state['total'] > 100000:  # Stop after 100KB
                    raise StopIteration("Enough data")
            
            sabr = ServerAbrStream(stream=s360, write_chunk=collector, monostate=monostate)
            try:
                sabr.start()
            except StopIteration:
                pass
            print(f"  Got {state['total']} bytes via SABR")
            if chunks:
                print(f"  First 20 bytes: {chunks[0][:20].hex()}")
                print("  SABR DOWNLOAD WORKS!")
        except Exception as e2:
            print(f"  SABR also failed: {e2}")
else:
    print("  No 360p mp4 stream found")
