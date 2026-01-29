# OpenAI Proxy

Simple Node/Express proxy to forward requests to OpenAI.

## Setup

```
cd server
npm install
```

## Environment

- `OPENAI_API_KEY` (required)
- `PROXY_KEY` (optional; if set, clients must send `X-Proxy-Key`)
- `PORT` (optional, default 8787)

## Run

```
npm start
```

## Endpoints

- `GET /api/health`
- `GET /api/models`
- `POST /api/review`
- `POST /api/suggest`
- `POST /api/chat`
- `POST /api/create`

These forward to OpenAI `/v1/models` and `/v1/responses`.
