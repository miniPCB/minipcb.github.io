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
   - `CONTACT_TO_EMAIL` (optional; defaults to `REQUEST_TO_EMAIL`)
   - `CONTACT_FROM_EMAIL` (optional; defaults to `REQUEST_FROM_EMAIL`; should be a verified sender)
   - `CONTACT_ALLOWED_ORIGINS` (optional; comma-separated list of allowed browser origins for the public contact form)
   - `CONTACT_RATE_MAX` (optional; default `5`)
   - `CONTACT_RATE_WINDOW_MS` (optional; default `900000`)
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
- `POST /api/contact`
- `POST /api/part-availability`

## Frontend Setup

In the Test Base 2026 Preferences:

```
API Base URL = https://<your-vercel-project>.vercel.app/api
Proxy Key     = <your PROXY_KEY>  (optional)
```

## Contact Form Notes

- `POST /api/contact` is intended for the public `contact.html` page, so it does not use `PROXY_KEY`.
- Protect it with `CONTACT_ALLOWED_ORIGINS` and keep the form hosted on your expected site origins.
- The endpoint falls back to `REQUEST_TO_EMAIL` and `REQUEST_FROM_EMAIL` if `CONTACT_TO_EMAIL` and `CONTACT_FROM_EMAIL` are not set.

That’s it—GitHub Pages stays static, and Vercel handles the proxy.
