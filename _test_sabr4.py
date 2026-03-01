"""Test SABR download via Stream.download() which handles SABR properly"""
from pytubefix import YouTube, Stream, extract
from pytubefix.monostate import Monostate
import tempfile, os

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

# Find smallest SABR video stream
smallest = min((s for s in streams if s.is_sabr and s.type == 'video'), key=lambda s: s.filesize)
print(f"Selected: itag={smallest.itag}, res={smallest.resolution}, size={smallest.filesize:,}B, is_sabr={smallest.is_sabr}")

# Download to temp file using download() which handles SABR via ServerAbrStream
output_dir = tempfile.gettempdir()
print(f"\nDownloading to {output_dir}...")

try:
    filepath = smallest.download(output_path=output_dir, filename='test_sabr_download.mp4')
    if filepath and os.path.exists(filepath):
        sz = os.path.getsize(filepath)
        print(f"Downloaded: {filepath}")
        print(f"Size: {sz:,} bytes (expected {smallest.filesize:,})")
        # Read first bytes
        with open(filepath, 'rb') as f:
            header = f.read(32)
        print(f"First 32 bytes: {header.hex()}")
        print("SABR DOWNLOAD WORKS!")
        os.remove(filepath)
    else:
        print("No file created")
except Exception as e:
    print(f"Download failed: {e}")
    import traceback
    traceback.print_exc()
