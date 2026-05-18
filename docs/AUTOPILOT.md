# Autopilot

Autopilot is the hands-off production path.

It automatically:

- Builds a topic plan from local `trending_topics` and optional external URLs.
- Limits target count based on available video/image quota.
- Generates multiple script candidates and applies a quality score gate.
- Skips low-score content before expensive video calls when possible.
- Repairs missing assets such as video, subtitle, final composition, and cover.
- Exports a manual publish package by default.
- Uses TikTok publishing only when configured.

## Commands

```bash
python autopilot.py run --count 3 --min-score 65 --provider manual
python autopilot.py run --count 3 --provider auto
python autopilot.py run --dry-run --count 5
```

## Docker

```bash
docker compose --profile autopilot up --build autopilot
```

## Scheduled Run

```bash
python auto_scheduler.py --install-task --autopilot --time 09:00 --count 3 --min-score 65 --provider auto
```

## External Topic Source

Set one or more comma-separated URLs:

```env
AUTO_TIKTOK_TRENDING_URLS=https://example.com/topics.json
```

Supported JSON formats:

```json
[
  {"topic": "desk lighting tricks", "content_type": "knowledge"}
]
```

or:

```json
{
  "knowledge": ["cold facts", "science hooks"],
  "life_hacks": ["kitchen tips"]
}
```

Category aliases such as `knowledge`, `life_hacks`, `food`, `travel`, and `pets` are mapped to the built-in Chinese content types.
