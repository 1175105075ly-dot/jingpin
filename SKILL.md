---
name: amazon-competitor-monitor
description: Run one-off Amazon competitor monitoring jobs from pasted product-detail links. Use when Codex needs to manually trigger a temporary competitor crawl, drive a browser with the Seller Sprite extension, wait for extension-rendered data, extract standardized Amazon product metrics, write daily CSV/JSON snapshots, compare today's data with the active prior snapshot, rotate archives, and push Feishu/Lark bot alerts or daily reports. Do not use for long-running scheduled monitors or persistent competitor link libraries.
---

# Amazon Competitor Monitor

## Operating Contract

Treat every run as manually triggered and temporary. Accept only the links the user provides in the current request; do not maintain, infer, append to, or persist a competitor-link library. Clear the per-run link task file, browser scratch data, and temporary logs after the final report and archive rotation.

Use `scripts/snapshot_ops.py` for deterministic link parsing, snapshot writing, comparison, and active/archive rotation. Load `references/data-schema.md` before mapping scraped data into records. Load `references/browser-extraction.md` before browser automation. Load `references/feishu-messages.md` before sending Feishu/Lark messages.

## Run Workflow

1. Parse the pasted links with `snapshot_ops.py normalize-links`.
   - Accept multi-line pasted text.
   - Split, de-duplicate, validate Amazon product-detail URLs, and extract ASINs.
   - Store the normalized task list only in a temporary run folder.
   - Report invalid links before crawling.

2. Start an automation browser profile that has the Seller Sprite extension enabled.
   - Prefer the user's Chrome profile when extension access or login state is required.
   - Open one ASIN at a time using the canonical URL generated from the ASIN.
   - Do not keep a persistent browser-side competitor list.

3. Wait for each page with the staged strategy in `references/browser-extraction.md`.
   - Wait for base product DOM readiness first.
   - Poll for Seller Sprite's rendered data module.
   - After the module appears, wait 3 more seconds before reading.
   - If the module is still absent after 30 seconds for one ASIN, mark only that ASIN failed and continue.

4. Extract one normalized record per ASIN.
   - Required field groups: identity, price, coupons, ranking, inventory/variants, reviews, ads/deals, and crawl status.
   - Do not persist the original pasted URL in snapshots.
   - Use `error_type` and `error_message` for 404, unavailable pages, extension timeout, parse failures, or missing critical fields.

5. Build today's pending snapshot with `snapshot_ops.py write-snapshot`.
   - Output both `竞品快照_YYYYMMDD.json` and `竞品快照_YYYYMMDD.csv`.
   - Validate missing ASIN rate before rotation; treat widespread failures as a stop condition that requires user confirmation.

6. Compare against yesterday's active snapshot with `snapshot_ops.py compare`.
   - Apply user-provided thresholds if present; otherwise use defaults from the script help.
   - Highlight price changes, coupon and discount changes, BSR swings, stock recovery/outage, LD/7DD changes, rating/review risk, variant changes, title/image edits, removed ASINs, and unavailable pages.

7. Push Feishu/Lark notifications.
   - Send real-time change cards for material changes after comparison.
   - Send one daily summary card/report after all products are processed.
   - Send a separate exception card for failed, invalid, 404, down, or extension-timeout ASINs.
   - Attach the daily CSV snapshot to the daily summary when a Feishu file upload path is available.

8. Finalize and clean up.
   - Run `snapshot_ops.py rotate` only after today's snapshot is complete and validated.
   - Move the previous active snapshot into the archive folder, then replace active with today's files.
   - Delete temporary link/task/log files for the current run.

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

The `active/` folder must contain only the latest validated snapshot. Move older snapshots to `archive/`; never delete archived snapshots during normal operation.

## Failure Policy

Continue per-ASIN failures and include them in exception reporting. Stop the run only when browser startup fails, Seller Sprite is unavailable for all sampled pages, snapshot writing fails, or today's snapshot fails integrity checks. Never rotate active storage after a failed or clearly incomplete run.

## Common Commands

```bash
python scripts/snapshot_ops.py normalize-links --input links.txt --output tmp/tasks.json
python scripts/snapshot_ops.py write-snapshot --records tmp/records.json --pending-dir competitor-monitor-data/pending
python scripts/snapshot_ops.py compare --old competitor-monitor-data/active/竞品快照_YYYYMMDD.json --new competitor-monitor-data/pending/竞品快照_YYYYMMDD.json --out competitor-monitor-data/reports/异动报告_YYYYMMDD.json --markdown-out competitor-monitor-data/reports/异动报告_YYYYMMDD.md
python scripts/snapshot_ops.py rotate --active-dir competitor-monitor-data/active --archive-dir competitor-monitor-data/archive --pending-dir competitor-monitor-data/pending
```
