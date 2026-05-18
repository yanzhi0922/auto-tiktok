# Deployment

## Local Dashboard

```bash
python dashboard.py --host 127.0.0.1 --port 7860
```

Open:

```text
http://127.0.0.1:7860
```

## Docker Dashboard

```bash
docker compose up --build dashboard
```

The default Compose mapping is local-only:

```yaml
127.0.0.1:7860:7860
```

## Environment

Create `.env` from `.env.example` and fill in your own keys:

```bash
cp .env.example .env
```

For remote Dashboard access:

```env
AUTO_TIKTOK_DASHBOARD_TOKEN=replace_with_a_long_random_token
AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true
```

Use a real HTTPS reverse proxy before setting secure cookies.

## Health Check

```bash
curl http://127.0.0.1:7860/healthz
python ops.py health
```

## Backups

```bash
python ops.py backup
python ops.py rotate-logs --keep-days 14
```

Backups intentionally exclude the root `.env` file.
