"""
Video Downloader — Self-hosted startup script
Starts Flask on localhost:5000 and opens a Cloudflare Quick Tunnel
so the site is accessible from anywhere via a public URL.

Requirements:
  pip install flask pytubefix yt-dlp nodejs-wheel-binaries
  Download cloudflared: https://github.com/cloudflare/cloudflared/releases/latest

Usage:
  python start.py                     # start server + tunnel
  python start.py --no-tunnel         # start server only (localhost)
  python start.py --port 8080         # custom port
"""
import subprocess
import sys
import os
import time
import signal
import shutil
import re

PORT = 5000
TUNNEL = True

# Parse CLI args
args = sys.argv[1:]
if '--no-tunnel' in args:
    TUNNEL = False
    args.remove('--no-tunnel')
if '--port' in args:
    idx = args.index('--port')
    PORT = int(args[idx + 1])

def find_cloudflared():
    """Find cloudflared binary."""
    # Check PATH
    cf = shutil.which('cloudflared')
    if cf:
        return cf
    # Check local directory
    local = os.path.join(os.path.dirname(__file__), 'cloudflared.exe')
    if os.path.exists(local):
        return local
    # Check common install locations (Windows)
    for p in [
        os.path.expandvars(r'%ProgramFiles%\cloudflared\cloudflared.exe'),
        os.path.expandvars(r'%ProgramFiles(x86)%\cloudflared\cloudflared.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\cloudflared\cloudflared.exe'),
    ]:
        if os.path.exists(p):
            return p
    return None


def main():
    print("\n" + "=" * 60)
    print("   Video Downloader — Self-Hosted")
    print("=" * 60)

    # Start Flask server
    print(f"\n  Starting Flask server on port {PORT}...")
    flask_env = os.environ.copy()
    flask_env['PORT'] = str(PORT)
    flask_proc = subprocess.Popen(
        [sys.executable, 'app.py'],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=flask_env,
    )

    # Wait for Flask to start
    time.sleep(2)
    print(f"  Local server: http://localhost:{PORT}")

    tunnel_proc = None

    if TUNNEL:
        cf_path = find_cloudflared()
        if not cf_path:
            print("\n  cloudflared not found!")
            print("  Download it from: https://github.com/cloudflare/cloudflared/releases/latest")
            print(f"  Place cloudflared.exe in: {os.path.dirname(os.path.abspath(__file__))}")
            print(f"\n  Server is running locally at http://localhost:{PORT}")
            print("  You can also use: python start.py --no-tunnel")
        else:
            print(f"\n  Starting Cloudflare Tunnel ({cf_path})...")
            tunnel_proc = subprocess.Popen(
                [cf_path, 'tunnel', '--url', f'http://localhost:{PORT}'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Read tunnel output to find the public URL
            public_url = None
            start_time = time.time()
            while time.time() - start_time < 30:
                line = tunnel_proc.stdout.readline()
                if not line:
                    break
                # Look for the .trycloudflare.com URL
                match = re.search(r'(https://[\w-]+\.trycloudflare\.com)', line)
                if match:
                    public_url = match.group(1)
                    break

            if public_url:
                print(f"\n  Public URL: {public_url}")
                print(f"  Share this link with anyone to access your downloader!")
            else:
                print("\n  Tunnel started but couldn't detect public URL.")
                print("  Check the terminal output for the .trycloudflare.com URL.")

    print(f"\n  Press Ctrl+C to stop.\n")
    print("=" * 60 + "\n")

    try:
        flask_proc.wait()
    except KeyboardInterrupt:
        print("\n\n  Shutting down...")
        flask_proc.terminate()
        if tunnel_proc:
            tunnel_proc.terminate()
        print("  Done.\n")
        sys.exit(0)


if __name__ == '__main__':
    main()
