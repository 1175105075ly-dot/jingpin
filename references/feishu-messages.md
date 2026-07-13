# Feishu/Lark Messages

Use `scripts/feishu_webhook.py` for Feishu bot webhook delivery when the user provides an incoming webhook URL. Do not hardcode the webhook URL in the skill or repo; pass it with `--webhook` or `FEISHU_WEBHOOK_URL`.

Webhook messages are text-only. They cannot upload the CSV snapshot as an attachment. Include local file paths in the daily summary, and use a chat_id plus `lark-cli` file upload only if the user later asks for true file attachments.

## Default Delivery

When a webhook is configured, every monitoring run automatically sends one final Feishu message. Use the deterministic `daily-report` command; do not combine `snapshot-summary`, `report-summary`, or ad hoc `text` calls because that produces fragmented or duplicate notifications.

Send only after all ASINs are processed, the snapshot is validated, comparison is complete, and active/archive rotation succeeds. Do not send progress updates, per-ASIN cards, connectivity tests, or separate snapshot/change summaries during a normal run.

Pass `--delivery-log competitor-monitor-data/reports/feishu-delivery.json`. The sender validates Feishu's JSON business code, retries failed delivery up to three times, and skips dates already recorded as delivered. Use `--force` only when the user explicitly requests a resend.

A successful daily message should be readable at a glance in this order:

1. One-line result: date, total ASINs, successful count, unavailable/failed count, and material-change count.
2. Urgent status changes: newly unavailable products, recovered products, redirected/mismatched ASINs, and anything requiring immediate checking.
3. Important business changes: largest price moves, rating drops, coupon/deal starts or endings, and meaningful variant/title changes.
4. Ranking signal: at most the three strongest BSR improvements and three strongest deteriorations; omit tiny, noisy movements.
5. Recommended actions: short, concrete checks ordered by urgency.
6. File locations: final CSV snapshot and change report paths, explicitly described as local files rather than attachments.

Suppress image-URL-only changes, raw field dumps, long unchanged-ASIN lists, and low-value noise. Include canonical Amazon links only for products the user needs to inspect.

## Failure Delivery

If the monitoring run cannot reach a valid final snapshot, send one concise exception message instead of the daily message. Include the failed stage, affected ASINs or pages, whether the previous active snapshot was preserved, and the next retry action. Combine related failures into that single message.

Send a connectivity test only for a newly configured webhook before its first real delivery. Once a real message has been delivered successfully, do not test again unless the webhook changes or delivery starts failing.

## Link Policy

Do not send or store the user's original pasted links. Generate product links from ASINs:

```text
https://www.amazon.com/dp/{asin}
```

## Suggested Severity

- `critical`: page unavailable, out of stock, recovered from out of stock, rating drop over threshold, or large price/BSR movement.
- `warning`: coupon/deal change, moderate price movement, variant count change, or title change.
- `info`: image-URL changes, small BSR drift, and other low-value changes retained in the full report.

## Common Commands

```bash
python scripts/feishu_webhook.py --delivery-log competitor-monitor-data/reports/feishu-delivery.json daily-report --snapshot competitor-monitor-data/active/竞品快照_YYYYMMDD.json --report competitor-monitor-data/reports/变动报告_YYYYMMDD.json --csv competitor-monitor-data/active/竞品快照_YYYYMMDD.csv --markdown competitor-monitor-data/reports/变动报告_YYYYMMDD.md
```
