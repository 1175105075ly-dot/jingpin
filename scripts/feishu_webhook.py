#!/usr/bin/env python3
"""Send Amazon competitor monitor summaries to a Feishu bot webhook."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def post_text(webhook: str, text: str) -> dict[str, Any]:
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status": response.status, "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "body": body, "error": str(exc)}


def snapshot_summary(snapshot_path: Path, csv_path: Path | None) -> str:
    snapshot = read_json(snapshot_path)
    records = snapshot.get("records", [])
    failed = [row for row in records if row.get("status") in {"failed", "unavailable", "invalid"} or row.get("error_type")]
    ok_count = len(records) - len(failed)
    lines = [
        "Amazon竞品监控日报",
        f"日期: {snapshot.get('snapshot_date', '')}",
        f"总ASIN: {len(records)}",
        f"成功: {ok_count}",
        f"异常: {len(failed)}",
    ]
    if csv_path:
        lines.append(f"CSV快照: {csv_path}")
    if failed:
        lines.append("")
        lines.append("异常ASIN:")
        for row in failed[:20]:
            lines.append(f"- {row.get('asin')}: {row.get('error_type')} {row.get('error_message')}")
        if len(failed) > 20:
            lines.append(f"- 另有 {len(failed) - 20} 条异常")
    return "\n".join(lines)


def report_summary(report_path: Path) -> str:
    report = read_json(report_path)
    summary = report.get("summary", {})
    lines = [
        "Amazon竞品异动摘要",
        f"Baseline: {report.get('baseline', False)}",
        f"今日ASIN: {summary.get('new_count', 0)}",
        f"异动: {summary.get('changed_count', 0)}",
        f"无变化/基线: {summary.get('unchanged_count', 0)}",
        f"异常: {summary.get('failed_count', 0)}",
    ]
    changed = report.get("changed", [])
    if changed:
        lines.append("")
        lines.append("重点异动:")
        for item in changed[:12]:
            first_change = item.get("changes", [{}])[0]
            lines.append(
                f"- {item.get('asin')} [{item.get('severity')}] "
                f"{first_change.get('field')}: {first_change.get('old')} -> {first_change.get('new')}"
            )
        if len(changed) > 12:
            lines.append(f"- 另有 {len(changed) - 12} 条异动")
    if report.get("failed"):
        lines.append("")
        lines.append("异常请查看日报或本地报告文件。")
    return "\n".join(lines)


def test_message() -> str:
    return "Amazon竞品监控 Webhook 测试消息：飞书机器人连接正常。"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send Feishu webhook notifications for competitor monitor runs")
    parser.add_argument("--webhook", default=os.environ.get("FEISHU_WEBHOOK_URL"), help="Feishu bot webhook URL or FEISHU_WEBHOOK_URL")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("test", help="Send a simple connectivity test message")

    snapshot = sub.add_parser("snapshot-summary", help="Send daily snapshot summary")
    snapshot.add_argument("--snapshot", required=True, type=Path)
    snapshot.add_argument("--csv", type=Path)

    report = sub.add_parser("report-summary", help="Send comparison/change report summary")
    report.add_argument("--report", required=True, type=Path)

    text = sub.add_parser("text", help="Send arbitrary text")
    text.add_argument("--message", required=True)
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if not args.webhook:
        raise SystemExit("missing --webhook or FEISHU_WEBHOOK_URL")

    if args.command == "test":
        text = test_message()
    elif args.command == "snapshot-summary":
        text = snapshot_summary(args.snapshot, args.csv)
    elif args.command == "report-summary":
        text = report_summary(args.report)
    elif args.command == "text":
        text = args.message
    else:
        raise AssertionError(args.command)

    result = post_text(args.webhook, text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status", 500) >= 400:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
