#!/usr/bin/env python3
"""Check whether a computer is ready for an Amazon competitor monitor run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from feishu_webhook import default_webhook


def check_writable(data_dir: Path) -> tuple[bool, str]:
    probe = data_dir / "tmp" / ".preflight-write-test"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, "数据目录可写"
    except OSError as exc:
        return False, f"数据目录不可写: {exc}"


def active_baseline(data_dir: Path) -> dict[str, object]:
    active = data_dir / "active"
    json_files = sorted(active.glob("竞品快照_*.json")) if active.exists() else []
    csv_files = sorted(active.glob("竞品快照_*.csv")) if active.exists() else []
    paired_stems = {path.stem for path in json_files} & {path.stem for path in csv_files}
    return {
        "available": bool(paired_stems),
        "latest": sorted(paired_stems)[-1] if paired_stems else "",
        "message": "已发现历史基线" if paired_stems else "未发现历史基线，首次运行将建立基线",
    }


def run(data_dir: Path) -> dict[str, object]:
    writable, writable_message = check_writable(data_dir)
    webhook_ready = bool(default_webhook())
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "message": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "data_directory": {"ok": writable, "message": writable_message},
        "feishu_webhook": {
            "ok": webhook_ready,
            "message": "飞书自动通知已配置" if webhook_ready else "缺少 FEISHU_WEBHOOK_URL",
        },
        "baseline": active_baseline(data_dir),
    }
    blocking = [name for name in ("python", "data_directory", "feishu_webhook") if not checks[name]["ok"]]
    return {
        "ready": not blocking,
        "blocking": blocking,
        "checks": checks,
        "browser_manual_checks": [
            "Chrome 中 Codex 扩展已启用并显示 Connected",
            "Seller Sprite 扩展已启用并完成登录",
            "Amazon.com 页面可正常打开且没有 CAPTCHA",
        ],
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Preflight checks for Amazon competitor monitoring")
    parser.add_argument("--data-dir", type=Path, default=Path("competitor-monitor-data"))
    args = parser.parse_args()
    result = run(args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
