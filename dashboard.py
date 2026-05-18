#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动本地 Dashboard/API 服务。"""

from __future__ import annotations

import argparse

from src.dashboard.server import run_dashboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto TikTok 本地 Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=7860, help="监听端口")
    parser.add_argument("--base-dir", default="output", help="输出目录")
    args = parser.parse_args()

    run_dashboard(host=args.host, port=args.port, base_dir=args.base_dir)


if __name__ == "__main__":
    main()
