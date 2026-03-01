"""Test SABR download with an actual SABR stream"""
from pytubefix import YouTube, Stream, extract
from pytubefix.monostate import Monostate
from pytubefix.sabr.core.server_abr_stream import ServerAbrStream
import io

url = 'https://www.youtube.com/watch?v=3FZ2f5S9GGs'
yt = YouTube(url, client='WEB')

# Build streams bypassing cipher
sd = yt.streaming_data
stream_manifest = extract.apply_descrambler(sd)
if yt.po_token:
    extract.apply_po_token(stream_manifest, yt.vid_info, yt.po_token)

monostate = yt.stream_monostate
monostate.title = yt.title
monostate.duration = yt.length

streams = []
for s_data in stream_manifest:
    try:
        streams.append(Stream(
            stream=s_data, monostate=monostate,
            po_token=yt.po_token,
            video_playback_ustreamer_config=yt.video_playback_ustreamer_config
        ))
    except:
        pass

# Find a SABR stream (adaptive 720p mp4)
s720 = next((s for s in streams if s.is_sabr and s.resolution == '720p' and 'mp4' in s.mime_type), None)
if not s720:
    print("No SABR 720p mp4 found, trying any SABR stream")
    s720 = next((s for s in streams if s.is_sabr), None)

print(f"Selected: itag={s720.itag}, res={s720.resolution}, size={s720.filesize:,}B, is_sabr={s720.is_sabr}")

# Download via stream_to_buffer (pytubefix handles SABR internally)
print("\nDownloading first 200KB via SABR...")
buf = io.BytesIO()

# Monkey-patch to stop after 200KB
collected = {'bytes': 0, 'chunks': 0}
original_on_progress = s720.on_progress

def limited_progress(chunk, fh, remaining):
    collected['bytes'] += len(chunk)
    collected['chunks'] += 1
    fh.write(chunk)
    if collected['bytes'] >= 200000:
        raise StopIteration("Enough")
    original_on_progress(chunk, fh, remaining)

s720.on_progress = limited_progress

try:
    s720.stream_to_buffer(buf)
except StopIteration:
    pass

buf.seek(0)
data = buf.read()
print(f"Got {len(data)} bytes in {collected['chunks']} chunks")
if len(data) > 0:
    print(f"First 20 bytes: {data[:20].hex()}")
    print("SABR DOWNLOAD WORKS!")
else:
    print("No data received")
