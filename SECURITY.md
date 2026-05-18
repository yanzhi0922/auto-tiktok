# Security Policy

## Secrets

Never commit real API keys, OAuth tokens, `.env`, generated logs, or output artifacts.

This project includes log and API-response redaction, but that is a defense-in-depth measure, not a replacement for secret management. For public deployments:

- Use a secret manager or platform-provided environment secrets.
- Rotate keys regularly.
- Rotate immediately if a key is pasted into an issue, chat, log, or commit.
- Avoid sharing `docker compose config` output because it can expand environment variables.

## Dashboard

The Dashboard is designed for local or private-network operation.

- Bind to `127.0.0.1` by default.
- Set `AUTO_TIKTOK_DASHBOARD_TOKEN` before exposing it beyond localhost.
- Use HTTPS reverse proxy and `AUTO_TIKTOK_DASHBOARD_SECURE_COOKIES=true` for remote access.

## Reporting Vulnerabilities

If you find a vulnerability, please open a private security advisory on GitHub if available, or contact the maintainer directly. Do not publish exploitable details before a fix is available.
