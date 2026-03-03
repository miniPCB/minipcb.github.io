# Vercel OpenAI Proxy (No Node Required)

## Deploy (dashboard, no CLI)

1) Create a new Vercel project and point it at this repo.
2) Set **Root Directory** to `proxy-vercel`.
3) Add Environment Variables:
   - `OPENAI_API_KEY` (required)
   - `PROXY_KEY` (optional; if set, clients must send `X-Proxy-Key`)
   - `RESEND_API_KEY` (required for part requests)
   - `REQUEST_TO_EMAIL` (required for part requests)
   - `REQUEST_FROM_EMAIL` (required for part requests; must be a verified sender)
   - `DIGIKEY_CLIENT_ID` (required for DigiKey availability)
   - `DIGIKEY_CLIENT_SECRET` (required for DigiKey availability)
   - `DIGIKEY_SITE` (optional; default `US`)
   - `DIGIKEY_LANGUAGE` (optional; default `en`)
   - `DIGIKEY_CURRENCY` (optional; default `USD`)
   - `MOUSER_API_KEY` (required for Mouser availability)
   - `AVAILABILITY_CACHE_TTL_MS` (optional; default `300000`)
4) Deploy.

## Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/review`
- `POST /api/suggest`
- `POST /api/chat`
- `POST /api/create`
- `POST /api/part-request`
- `POST /api/part-availability`

## Frontend Setup

In the Test Base 2026 Preferences:

```
API Base URL = https://<your-vercel-project>.vercel.app/api
Proxy Key     = <your PROXY_KEY>  (optional)
```

That’s it—GitHub Pages stays static, and Vercel handles the proxy.
