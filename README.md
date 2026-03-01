# Video Downloader

A beautiful dark glassmorphism web app for downloading YouTube and Instagram videos with quality selection.

## Features
- **YouTube** — Download in any quality (up to 4K) with multiple format options
- **Instagram** — Download Reels, posts, and stories
- **Quality Selection** — Choose from available resolutions
- **Audio Only** — Extract audio as MP3
- **Dark Glassmorphism UI** — Modern animated design with blur effects

## Quick Start (Local)

```bash
# Install dependencies
pip install flask pytubefix yt-dlp nodejs-wheel-binaries

# Start the server
python app.py
```

Open http://localhost:5000 in your browser.

## Public Access (Cloudflare Tunnel)

To share your downloader with anyone on the internet:

1. **Download cloudflared** from [GitHub Releases](https://github.com/cloudflare/cloudflared/releases/latest)
   - Windows: `cloudflared-windows-amd64.exe` → rename to `cloudflared.exe`
   - Place it in this project folder

2. **Run the startup script:**
   ```bash
   python start.py
   ```
   This starts Flask + creates a free Cloudflare Quick Tunnel.
   You'll get a public URL like `https://random-words.trycloudflare.com`.

3. **Share the URL** — anyone can use it to download videos!

> **Note:** Your computer must stay on for the tunnel to work. The URL changes each time you restart.

### Why self-host?

YouTube aggressively blocks datacenter IPs (AWS, GCP, Azure, etc.) from accessing video streams. Free cloud platforms like Vercel, Render, and Railway all use these blocked IPs. Self-hosting uses your residential IP, which YouTube allows.

## Options

```bash
python start.py                  # Server + tunnel
python start.py --no-tunnel      # Server only (localhost)
python start.py --port 8080      # Custom port
```

## Tech Stack
- **Backend:** Python, Flask, pytubefix, yt-dlp
- **Frontend:** HTML/CSS/JS with glassmorphism design
- **Tunnel:** Cloudflare Quick Tunnel (free, no account needed)
