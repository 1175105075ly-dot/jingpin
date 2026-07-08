# Feishu/Lark Messages

Use `scripts/feishu_webhook.py` for Feishu bot webhook delivery when the user provides an incoming webhook URL. Do not hardcode the webhook URL in the skill or repo; pass it with `--webhook` or `FEISHU_WEBHOOK_URL`.

Webhook messages are text-only in the baseline implementation. They cannot upload the CSV snapshot as an attachment. Include the local CSV path in the daily summary, and use a chat_id plus `lark-cli` file upload only if the user later asks for true file attachments.

## Message Types

Real-time change card:
- Send one card per materially changed ASIN.
- Include ASIN, generated Amazon direct link, change summary, yesterday value, today value, and severity.
- Keep cards short; put full details in the daily report.

Daily summary:
- Send after all ASINs are processed and comparison is complete.
- Include total ASIN count, successful count, failed count, changed count, unchanged ASIN list, top price moves, top BSR moves, stock/deal events, and category price overview.
- Include the local CSV snapshot path. Do not claim the CSV was attached when using webhook-only delivery.

Exception card:
- Send separately for invalid links, Amazon unavailable pages, Seller Sprite timeouts, parse failures, and browser startup failures.
- Include enough detail for the user to retry the failed ASINs in the next manual run.

## Link Policy

Do not send or store the user's original pasted links. Generate product links from ASINs:

```text
https://www.amazon.com/dp/{asin}
```

## Suggested Severity

- `critical`: page unavailable, out of stock, recovered from out of stock, rating drop over threshold, or large price/BSR movement.
- `warning`: coupon/deal change, moderate price/BSR movement, variant count change, title/image change.
- `info`: low-value changes that pass reporting filters or unchanged daily summary entries.

## Common Commands

```bash
python scripts/feishu_webhook.py --webhook "$FEISHU_WEBHOOK_URL" test
python scripts/feishu_webhook.py --webhook "$FEISHU_WEBHOOK_URL" report-summary --report competitor-monitor-data/reports/异动报告_YYYYMMDD.json
python scripts/feishu_webhook.py --webhook "$FEISHU_WEBHOOK_URL" snapshot-summary --snapshot competitor-monitor-data/pending/竞品快照_YYYYMMDD.json --csv competitor-monitor-data/pending/竞品快照_YYYYMMDD.csv
```
