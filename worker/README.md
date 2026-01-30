# Cloudflare Worker OpenAI Proxy

## Setup

1) Install Wrangler (once):
```
npm install -g wrangler
```

2) Login:
```
wrangler login
```

3) Set secrets:
```
wrangler secret put OPENAI_API_KEY
wrangler secret put PROXY_KEY
```
`PROXY_KEY` is optional.

4) Deploy:
```
wrangler deploy
```

## Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/review`
- `POST /api/suggest`
- `POST /api/chat`
- `POST /api/create`

## Frontend

Set the API Base URL in Preferences to:

```
https://<your-worker-subdomain>.workers.dev
```

If you set `PROXY_KEY`, also fill Proxy Key in Preferences.
