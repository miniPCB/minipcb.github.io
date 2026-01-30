# Vercel OpenAI Proxy (No Node Required)

## Deploy (dashboard, no CLI)

1) Create a new Vercel project and point it at this repo.
2) Set **Root Directory** to `proxy-vercel`.
3) Add Environment Variables:
   - `OPENAI_API_KEY` (required)
   - `PROXY_KEY` (optional; if set, clients must send `X-Proxy-Key`)
4) Deploy.

## Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/review`
- `POST /api/suggest`
- `POST /api/chat`
- `POST /api/create`

## Frontend Setup

In the Test Base 2026 Preferences:

```
API Base URL = https://<your-vercel-project>.vercel.app/api
Proxy Key     = <your PROXY_KEY>  (optional)
```

That’s it—GitHub Pages stays static, and Vercel handles the proxy.
