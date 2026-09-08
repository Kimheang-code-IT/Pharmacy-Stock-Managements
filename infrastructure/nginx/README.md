# Host reverse proxy

Use this folder for **host-level** Nginx or Caddy configuration that sits in front of Docker Compose (TLS termination, public HTTP entry).

The frontend container already ships its own SPA nginx config at `frontend/nginx.conf` (static files + `/api` → API). Do not move that file here — Docker builds it from the `frontend/` context.

## Recommended production shape

```text
Internet → host Nginx/Caddy (this folder) → frontend:80 → /api → api:8000
```

Add concrete site configs here when you introduce a dedicated reverse-proxy Compose service or a host install (for example `stock-pos.conf` or `Caddyfile`).
