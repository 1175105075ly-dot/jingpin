---
name: amazon-competitor-monitor
description: Run one-off Amazon competitor monitoring jobs from manually pasted Amazon product-detail or ASIN-filter collection links. Use when Codex needs to trigger a temporary competitor crawl, drive the user's Chrome browser with the Seller Sprite extension, wait for extension-rendered data, extract standardized Amazon product metrics, write daily CSV/JSON snapshots, compare today's data with the active prior snapshot, rotate archives, and push Feishu/Lark webhook alerts or daily reports. Do not use for long-running scheduled monitors or persistent competitor link libraries.
---

# Amazon Competitor Monitor

## Operating Contract

Treat every run as manually triggered and temporary. Accept only links the user provides in the current request; do not maintain, infer, append to, or persist a competitor-link library. Store collection URLs only inside the current run's temporary task file, never in daily snapshots. Clear per-run link/task/browser scratch data after the final report and archive rotation unless the user asks to keep debugging evidence.

Use `scripts/snapshot_ops.py` for deterministic link parsing, snapshot writing, comparison, validation, and active/archive rotation. Load `references/data-schema.md` before mapping scraped data into records. Load `references/browser-extraction.md` before browser automation. Load `references/feishu-messages.md` before sending Feishu/Lark webhook messages.

## Run Workflow

1. Parse pasted links with `snapshot_ops.py normalize-links`.
   - Accept multi-line pasted text.
   - Split, de-duplicate, validate Amazon detail URLs and ASIN-filter collection URLs.
   - For `rh=p_78:ASIN|ASIN` or `%7C` encoded filters, keep one `crawl_pages[]` entry with `url` and `expected_asins`.
   - Keep one ASIN task per product with a generated canonical `https://www.amazon.com/dp/{asin}` link.

2. Start the user's Chrome browser profile with Seller Sprite installed and authenticated.
   - Open each temporary Amazon collection/search page from `crawl_pages[].url`.
   - Use canonical `/dp/{asin}` pages only as a fallback for missing products or report links.
   - Do not keep a persistent browser-side competitor list.

3. Wait for the collection page with `references/browser-extraction.md`.
   - Wait for base Amazon list DOM first.
   - Poll up to 30 seconds for Seller Sprite's rendered module or stable marker.
   - After Seller Sprite appears, wait 3 more seconds before extracting.
   - If Seller Sprite never appears for a page, emit failed records for that page's expected ASINs with `error_type=seller_sprite_timeout`.

4. Extract one normalized record per expected ASIN.
   - Required groups: identity, price, coupons, ranking, inventory/variants, reviews, ads/deals, and crawl status.
   - If an expected ASIN is absent from the page, emit `status=failed`, `error_type=asin_missing_from_collection`.
   - Do not persist `source_url` or the original pasted URL in snapshots.

5. Write and validate today's pending snapshot.
   - `snapshot_ops.py write-snapshot` writes `竞品快照_YYYYMMDD.json` and `竞品快照_YYYYMMDD.csv`.
   - Run `snapshot_ops.py validate-snapshot --expected-count <N>` before rotation.
   - Treat widespread failures or count mismatch as a stop condition; do not rotate active storage after a failed or clearly incomplete run.

6. Compare against the active prior snapshot.
   - `snapshot_ops.py compare` writes `异动报告_YYYYMMDD.json/md`.
   - If no prior active snapshot exists, the report is a baseline: all ASINs are treated as unchanged/baseline and no fake "new ASIN" alert is produced.

7. Push Feishu/Lark webhook notifications when requested.
   - Use `scripts/feishu_webhook.py --webhook <url>` or `FEISHU_WEBHOOK_URL`.
   - Send a test message before the first real push.
   - Send exception and daily summary text. Webhook does not upload files; include the local CSV path in the summary.

8. Finalize and clean up.
   - Run `snapshot_ops.py rotate` only after validation passes.
   - Move the previous active snapshot into `archive/`, then activate today's pending files.
   - Delete temporary link/task/log files unless preserving them for debugging.

## Storage Layout

Use this layout unless the user gives a project-specific path:

```text
competitor-monitor-data/
  active/
    竞品快照_YYYYMMDD.json
    竞品快照_YYYYMMDD.csv
  archive/
    竞品快照_YYYYMMDD.json
    竞品快照_YYYYMMDD.csv
  pending/
    竞品快照_YYYYMMDD.json
    竞品快照_YYYYMMDD.csv
  reports/
    异动报告_YYYYMMDD.json
    异动报告_YYYYMMDD.md
  tmp/
```

`active/` must contain only the latest validated snapshot. Move older snapshots to `archive/`; never delete archived snapshots during normal operation.

## Failure Policy

Continue per-ASIN failures and include them in exception reporting. Stop the run only when browser startup fails, Seller Sprite is unavailable for all sampled pages, snapshot writing fails, or today's snapshot fails integrity checks. Never rotate active storage after a failed or incomplete run.

## Common Commands

```bash
python scripts/snapshot_ops.py normalize-links --input links.txt --output tmp/tasks.json
python scripts/snapshot_ops.py write-snapshot --records tmp/records.json --pending-dir competitor-monitor-data/pending --date 20260623
python scripts/snapshot_ops.py validate-snapshot --snapshot competitor-monitor-data/pending/竞品快照_20260623.json --expected-count 32
python scripts/snapshot_ops.py compare --old competitor-monitor-data/active/竞品快照_20260622.json --new competitor-monitor-data/pending/竞品快照_20260623.json --out competitor-monitor-data/reports/异动报告_20260623.json --markdown-out competitor-monitor-data/reports/异动报告_20260623.md
python scripts/feishu_webhook.py --webhook "$FEISHU_WEBHOOK_URL" test
python scripts/feishu_webhook.py --webhook "$FEISHU_WEBHOOK_URL" snapshot-summary --snapshot competitor-monitor-data/pending/竞品快照_20260623.json --csv competitor-monitor-data/pending/竞品快照_20260623.csv
python scripts/snapshot_ops.py rotate --active-dir competitor-monitor-data/active --archive-dir competitor-monitor-data/archive --pending-dir competitor-monitor-data/pending
```
