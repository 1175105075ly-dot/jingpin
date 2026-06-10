# Feishu/Lark Messages

Use the available Feishu/Lark messaging tool or `lark-cli` only after comparison output exists.

## Message Types

Real-time change card:
- Send one card per materially changed ASIN.
- Include ASIN, generated Amazon direct link, change summary, yesterday value, today value, and severity.
- Keep cards short; put full details in the daily report.

Daily summary:
- Send after all ASINs are processed and comparison is complete.
- Include total ASIN count, successful count, failed count, changed count, unchanged ASIN list, top price moves, top BSR moves, stock/deal events, and category price overview.
- Upload and attach the daily CSV snapshot when file upload is available.

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
