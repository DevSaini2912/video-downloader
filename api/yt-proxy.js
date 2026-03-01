/**
 * Vercel Edge Function — proxies YouTube innertube API calls.
 * Edge Functions run on Vercel's Edge Network (different IPs from Lambda).
 * YouTube may treat these IPs differently from datacenter Lambda IPs.
 */
export const config = { runtime: 'edge' };

const ALLOWED_HOSTS = [
  'www.youtube.com',
  'youtubei.googleapis.com',
  'youtube.googleapis.com',
];

export default async function handler(req) {
  // GET /api/yt-proxy — return the edge IP (for debugging)
  if (req.method === 'GET') {
    try {
      const ipResp = await fetch('https://api.ipify.org?format=json');
      const ipData = await ipResp.json();
      return new Response(JSON.stringify({ edge_ip: ipData.ip, runtime: 'edge' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), { status: 500 });
    }
  }

  // POST /api/yt-proxy — proxy a YouTube API call
  if (req.method === 'POST') {
    try {
      const body = await req.json();
      const targetUrl = body.url;
      const targetHeaders = body.headers || {};
      const targetBody = body.body; // string (JSON-encoded)

      // Validate target URL
      const parsed = new URL(targetUrl);
      if (!ALLOWED_HOSTS.includes(parsed.hostname)) {
        return new Response(JSON.stringify({ error: 'Host not allowed' }), { status: 403 });
      }

      // Forward the request to YouTube
      const resp = await fetch(targetUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
          'Origin': 'https://www.youtube.com',
          'Referer': 'https://www.youtube.com/',
          ...targetHeaders,
        },
        body: targetBody,
      });

      const respBody = await resp.text();
      return new Response(respBody, {
        status: resp.status,
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), { status: 500 });
    }
  }

  return new Response('Method not allowed', { status: 405 });
}
