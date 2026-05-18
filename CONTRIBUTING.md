# Contributing

Thanks for improving Auto TikTok.

## Local Setup

```bash
pip install -r requirements-dev.txt
cp .env.example .env
python -m pytest -q
python -m ruff check .
```

`ffmpeg` and `ffprobe` must be available on `PATH` for media composition features.

## Development Rules

- Do not commit `.env`, API keys, generated videos, logs, or output directories.
- Keep changes focused and covered by tests when behavior changes.
- Run the full validation set before opening a pull request:

```bash
python -m ruff check .
python -m pytest -q
python -m compileall config src main.py douyin_main.py auto_scheduler.py run_daily.py dashboard.py autopilot.py ops.py output_manager.py
```

## Pull Requests

Include:

- What changed
- How it was tested
- Any quota, API, or deployment impact

For publishing or platform API changes, mention whether real third-party calls were executed.
