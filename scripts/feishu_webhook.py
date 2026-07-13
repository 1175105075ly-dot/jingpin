#!/usr/bin/env python3
"""Send Amazon competitor monitor summaries to a Feishu bot webhook."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def default_webhook() -> str | None:
    webhook = os.environ.get("FEISHU_WEBHOOK_URL")
    if webhook or os.name != "nt":
        return webhook

    # User-level environment changes are not inherited by an already-running app.
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            value, _ = winreg.QueryValueEx(key, "FEISHU_WEBHOOK_URL")
            return str(value) if value else None
    except (FileNotFoundError, OSError):
        return None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def response_ok(status: int, body: str) -> bool:
    if status < 200 or status >= 300:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    code = payload.get("code", payload.get("StatusCode"))
    return code == 0


def post_text(webhook: str, text: str, attempts: int = 3) -> dict[str, Any]:
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    last_result: dict[str, Any] = {"ok": False, "status": 0, "body": ""}
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8", errors="replace")
                last_result = {
                    "ok": response_ok(response.status, body),
                    "status": response.status,
                    "body": body,
                    "attempt": attempt,
                }
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_result = {"ok": False, "status": exc.code, "body": body, "error": str(exc), "attempt": attempt}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_result = {"ok": False, "status": 0, "body": "", "error": str(exc), "attempt": attempt}

        if last_result["ok"]:
            return last_result
        if attempt < attempts:
            time.sleep(2 ** (attempt - 1))
    return last_result


def pct_change(old: Any, new: Any) -> float | None:
    try:
        old_number = float(old)
        new_number = float(new)
    except (TypeError, ValueError):
        return None
    if old_number == 0:
        return None
    return ((new_number - old_number) / old_number) * 100


def compact_number(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def amazon_link(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}"


def display_value(value: Any) -> str:
    if value is True:
        return "有"
    if value is False:
        return "无"
    translations = {"active": "进行中", "none": "无", "unknown": "未知", "ok": "正常", "unavailable": "不可用"}
    return translations.get(str(value), str(value))


def daily_report_message(snapshot_path: Path, report_path: Path, csv_path: Path | None, markdown_path: Path | None) -> str:
    snapshot = read_json(snapshot_path)
    report = read_json(report_path)
    records = snapshot.get("records", [])
    summary = report.get("summary", {})
    failed = [row for row in records if row.get("status") != "ok" or row.get("error_type")]
    ok_count = len(records) - len(failed)
    changed = report.get("changed", [])

    recovered: list[str] = []
    status_alerts: list[str] = []
    price_moves: list[tuple[float, str]] = []
    bsr_moves: list[tuple[float, int, str]] = []
    business_changes: list[str] = []
    listing_risks: set[str] = set()
    business_labels = {
        "has_coupon": "优惠券",
        "coupon_value": "优惠内容",
        "limited_discount_status": "限时优惠",
        "has_ld": "秒杀活动",
        "has_7_day_deal": "7天促销",
    }
    error_labels = {
        "amazon_unavailable": "页面不可用",
        "amazon_redirected_to_other_asin": "跳转到其他ASIN",
        "asin_redirected": "跳转到其他ASIN",
        "amazon_blocked": "页面被拦截或出现验证码",
        "seller_sprite_timeout": "Seller Sprite 加载超时",
        "parse_error": "页面解析失败",
    }

    for item in changed:
        asin = str(item.get("asin", ""))
        item_recovered = any(
            change.get("field") == "status" and change.get("new") == "ok" and change.get("old") != "ok"
            for change in item.get("changes", [])
        )
        for change in item.get("changes", []):
            field = change.get("field")
            old = change.get("old")
            new = change.get("new")
            if field == "status":
                if new == "ok" and old != "ok":
                    recovered.append(asin)
                elif new != "ok":
                    status_alerts.append(f"{asin}: {old or 'unknown'} -> {new}")
            elif field == "redirected_to_asin" and new:
                status_alerts.append(f"{asin}: 跳转到 {new}")
            elif field == "current_price":
                pct = pct_change(old, new)
                if pct is not None:
                    price_moves.append((abs(pct), f"{asin}: ${compact_number(old)} -> ${compact_number(new)} ({pct:+.1f}%)"))
            elif field == "small_bsr_rank":
                pct = pct_change(old, new)
                if pct is not None:
                    bsr_moves.append((abs(pct), 1 if pct > 0 else -1, f"{asin}: {old} -> {new} ({pct:+.1f}%)"))
            elif field == "rating":
                business_changes.append(f"{asin}: 评分 {old} -> {new}")
            elif field in {"has_coupon", "coupon_value", "limited_discount_status", "has_ld", "has_7_day_deal"}:
                business_changes.append(
                    f"{asin}: {business_labels[field]} {display_value(old)} -> {display_value(new)}"
                )
            elif field in {"title", "variant_count"} and not item_recovered:
                listing_risks.add(asin)

    lines = [
        f"Amazon竞品监控日报 | {snapshot.get('snapshot_date', '')}",
        f"结果：共 {len(records)} 个，成功 {ok_count} 个，异常 {len(failed)} 个，有效异动 {summary.get('material_changed_count', summary.get('changed_count', 0))} 个。",
    ]

    urgent: list[str] = []
    urgent.extend(status_alerts)
    urgent.extend(
        f"{row.get('asin')}: {error_labels.get(str(row.get('error_type')), row.get('error_type') or row.get('status'))}"
        for row in failed
    )
    if recovered:
        urgent.append(f"恢复正常：{', '.join(sorted(set(recovered)))}")
    if urgent:
        lines.extend(["", "【需要先看】"])
        lines.extend(f"- {entry}" for entry in list(dict.fromkeys(urgent))[:8])

    if price_moves or business_changes or listing_risks:
        lines.extend(["", "【关键业务变化】"])
        for _, entry in sorted(price_moves, reverse=True)[:5]:
            lines.append(f"- {entry}")
        lines.extend(f"- {entry}" for entry in list(dict.fromkeys(business_changes))[:5])
        for asin in sorted(listing_risks)[:5]:
            lines.append(f"- {asin}: 标题或变体发生变化，建议核对商品页面 {amazon_link(asin)}")

    improved = [entry for _, direction, entry in sorted(bsr_moves, reverse=True) if direction < 0][:3]
    worsened = [entry for _, direction, entry in sorted(bsr_moves, reverse=True) if direction > 0][:3]
    if improved or worsened:
        lines.extend(["", "【排名信号】"])
        lines.extend(f"- 改善：{entry}" for entry in improved)
        lines.extend(f"- 下滑：{entry}" for entry in worsened)

    actions: list[str] = []
    if failed or status_alerts:
        actions.append("优先复核异常和跳转商品，确认是否下架、换绑或被亚马逊合并页面。")
    if listing_risks:
        actions.append("核对标题、尺寸和变体，排除同一 ASIN 商品内容被替换。")
    if price_moves:
        actions.append("检查大幅调价商品的优惠结束、变体切换和跟卖情况。")
    if actions:
        lines.extend(["", "【建议动作】"])
        lines.extend(f"- {action}" for action in actions)

    lines.extend(["", "【本地文件】"])
    if csv_path:
        lines.append(f"- CSV快照：{csv_path}")
    lines.append(f"- JSON报告：{report_path}")
    if markdown_path:
        lines.append(f"- 可读报告：{markdown_path}")
    lines.append("说明：以上是本地文件路径，飞书机器人未上传附件。")
    return "\n".join(lines)


def delivery_key(snapshot_path: Path) -> str:
    snapshot = read_json(snapshot_path)
    return str(snapshot.get("snapshot_date") or snapshot_path.stem)


def read_delivery_log(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"delivered": {}}
    try:
        payload = read_json(path)
        return payload if isinstance(payload, dict) else {"delivered": {}}
    except (json.JSONDecodeError, OSError):
        return {"delivered": {}}


def mark_delivered(path: Path, key: str, result: dict[str, Any]) -> None:
    payload = read_delivery_log(path)
    delivered = payload.setdefault("delivered", {})
    delivered[key] = {"delivered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "attempt": result.get("attempt")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    parser.add_argument("--webhook", default=default_webhook(), help="Feishu bot webhook URL or FEISHU_WEBHOOK_URL")
    parser.add_argument("--attempts", type=int, default=3, help="Delivery attempts for transient failures")
    parser.add_argument("--delivery-log", type=Path, help="Optional JSON delivery log used to prevent duplicate daily messages")
    parser.add_argument("--force", action="store_true", help="Send even when the delivery log already contains this date")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("test", help="Send a simple connectivity test message")

    snapshot = sub.add_parser("snapshot-summary", help="Send daily snapshot summary")
    snapshot.add_argument("--snapshot", required=True, type=Path)
    snapshot.add_argument("--csv", type=Path)

    report = sub.add_parser("report-summary", help="Send comparison/change report summary")
    report.add_argument("--report", required=True, type=Path)

    daily = sub.add_parser("daily-report", help="Send one organized snapshot and comparison report")
    daily.add_argument("--snapshot", required=True, type=Path)
    daily.add_argument("--report", required=True, type=Path)
    daily.add_argument("--csv", type=Path)
    daily.add_argument("--markdown", type=Path)

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
    elif args.command == "daily-report":
        key = delivery_key(args.snapshot)
        if args.delivery_log and not args.force:
            delivered = read_delivery_log(args.delivery_log).get("delivered", {})
            if key in delivered:
                print(json.dumps({"ok": True, "skipped": True, "reason": "already delivered", "key": key}, ensure_ascii=False, indent=2))
                return
        text = daily_report_message(args.snapshot, args.report, args.csv, args.markdown)
    elif args.command == "text":
        text = args.message
    else:
        raise AssertionError(args.command)

    result = post_text(args.webhook, text, attempts=max(1, args.attempts))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)
    if args.command == "daily-report" and args.delivery_log:
        mark_delivered(args.delivery_log, key, result)


if __name__ == "__main__":
    main()
