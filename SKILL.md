---
name: amazon-competitor-monitor
description: Run reliable one-off Amazon competitor monitoring jobs from manually pasted Amazon product-detail or ASIN-filter collection links. Use when Codex needs to control the user's Chrome browser with Seller Sprite, split large ASIN collections into stable batches, retry and fall back to detail pages, extract standardized product metrics, validate and rotate daily CSV/JSON snapshots, compare material changes, and automatically send one organized Feishu/Lark daily report. Do not use for scheduled monitors or persistent competitor link libraries.
---

# Amazon Competitor Monitor V1.1

## Operating Contract

Treat every run as manually triggered and temporary. Accept only links supplied in the current request. Never maintain or infer a persistent competitor-link library. Keep pasted collection URLs only in `tmp/` during the run; never write them to snapshots or reports.

Use the bundled scripts for deterministic work:

- `scripts/preflight.py`: check local readiness before browsing.
- `scripts/snapshot_ops.py`: normalize links, write/validate/compare snapshots, and rotate storage.
- `scripts/feishu_webhook.py`: generate and deliver one organized Feishu report with retry and deduplication.

Load `references/browser-extraction.md`, `references/data-schema.md`, and `references/feishu-messages.md` before their corresponding stages.

## Run Workflow

1. Run preflight.
   - Execute `preflight.py --data-dir competitor-monitor-data`.
   - Resolve missing webhook or data-directory failures before crawling.
   - In Chrome, verify that Codex is Connected, Seller Sprite is logged in, and Amazon is not showing a CAPTCHA.

2. Normalize the pasted links.
   - Run `snapshot_ops.py normalize-links --collection-chunk-size 8`.
   - De-duplicate and validate ASINs.
   - Split ASIN-filter collection links into crawl pages containing at most eight ASINs each.
   - Keep one canonical `https://www.amazon.com/dp/{asin}` fallback task per ASIN.

3. Crawl collection pages with Chrome and Seller Sprite.
   - Process each generated `crawl_pages[]` entry.
   - Wait for Amazon DOM, then Seller Sprite, then three additional seconds before extraction.
   - If Amazon or Seller Sprite is incomplete, reload once and repeat the wait sequence.
   - Save normalized records incrementally in `tmp/records.json` so an interrupted run can resume without repeating completed ASINs.

4. Recover missing ASINs automatically.
   - Open the canonical detail page for every ASIN absent or incomplete on its collection page; no extra user confirmation is required.
   - Verify the final page ASIN after navigation. If it redirects to another ASIN, keep the requested `asin`, set `status=invalid`, `error_type=asin_redirected`, and fill `resolved_asin` plus `redirected_to_asin`.
   - Distinguish unavailable pages, CAPTCHA/blocking, Seller Sprite timeout, and parse failure using the schema error types.
   - Emit exactly one record for every expected ASIN, including failures.

5. Write and strictly validate the pending snapshot.
   - Run `write-snapshot` to create the dated JSON/CSV pair.
   - Run `validate-snapshot` with both `--expected-count` and `--expected-tasks tmp/tasks.json`.
   - Reject duplicate ASINs, missing/unexpected ASINs, invalid statuses, excessive failures, or weak core-field coverage.
   - Never rotate storage when validation exits non-zero.

6. Compare with the active prior snapshot.
   - Run `compare` to write dated JSON and Markdown reports.
   - Use `material_changed_count` for the headline, not raw `changed_count`.
   - Treat ordinary image-URL changes and small BSR drift as informational noise. Rank changes become critical only when both absolute and percentage thresholds are crossed.
   - If no prior snapshot exists, create a baseline without fake new-ASIN alerts.

7. Activate the validated snapshot safely.
   - Run `rotate --date YYYYMMDD` only after validation and comparison succeed.
   - Rotate only that date's JSON/CSV pair. The script rolls back file moves if activation fails.
   - Keep exactly one validated snapshot pair in `active/`; retain older pairs in `archive/`.

8. Send one Feishu daily report automatically.
   - Run `feishu_webhook.py daily-report` with snapshot, report, CSV, Markdown, and `--delivery-log competitor-monitor-data/reports/feishu-delivery.json`.
   - Send exactly one final report containing the result, urgent status changes, key business changes, top BSR signals, recommended actions, and local file paths.
   - Do not send progress, per-ASIN, test, or duplicate summary messages during normal runs.
   - The sender validates Feishu's business response, retries transient failures, and skips a date already marked delivered unless `--force` is explicitly requested.
   - If the run fails before activation, preserve the prior active snapshot and send one concise exception message when delivery is available.

9. Clean temporary data.
   - Delete pasted links, task files, logs, and browser scratch files after successful delivery.
   - Preserve `tmp/records.json` only when the run is interrupted and resumable or when debugging evidence is needed.

## Storage Layout

```text
competitor-monitor-data/
  active/       # latest validated JSON/CSV pair
  archive/      # prior validated pairs
  pending/      # current unactivated pair
  reports/      # JSON/Markdown reports and Feishu delivery log
  tmp/          # per-run links, tasks, records, and browser scratch data
```

Do not delete archived snapshots during normal operation. Copy `active/` and `archive/` to a new computer only when historical comparison continuity is required; otherwise the first run on that computer becomes a baseline.

## Cross-Computer Setup

On each new computer:

1. Install this Skill from GitHub.
2. Enable the Codex Chrome extension and confirm Connected.
3. Install, enable, and sign in to Seller Sprite.
4. Store the Feishu webhook locally as `FEISHU_WEBHOOK_URL`; never commit it.
5. Copy snapshot history when continuity is needed.
6. Run preflight before the first monitor job.

On Windows, save the webhook for the current user without placing it in a file:

```powershell
[Environment]::SetEnvironmentVariable('FEISHU_WEBHOOK_URL', '<webhook-url>', 'User')
```

## Common Commands

```bash
python scripts/preflight.py --data-dir competitor-monitor-data
python scripts/snapshot_ops.py normalize-links --input links.txt --output competitor-monitor-data/tmp/tasks.json --collection-chunk-size 8
python scripts/snapshot_ops.py write-snapshot --records competitor-monitor-data/tmp/records.json --pending-dir competitor-monitor-data/pending --date 20260713
python scripts/snapshot_ops.py validate-snapshot --snapshot competitor-monitor-data/pending/竞品快照_20260713.json --expected-count 32 --expected-tasks competitor-monitor-data/tmp/tasks.json
python scripts/snapshot_ops.py compare --old competitor-monitor-data/active/竞品快照_20260712.json --new competitor-monitor-data/pending/竞品快照_20260713.json --out competitor-monitor-data/reports/变动报告_20260713.json --markdown-out competitor-monitor-data/reports/变动报告_20260713.md
python scripts/snapshot_ops.py rotate --active-dir competitor-monitor-data/active --archive-dir competitor-monitor-data/archive --pending-dir competitor-monitor-data/pending --date 20260713
python scripts/feishu_webhook.py --delivery-log competitor-monitor-data/reports/feishu-delivery.json daily-report --snapshot competitor-monitor-data/active/竞品快照_20260713.json --report competitor-monitor-data/reports/变动报告_20260713.json --csv competitor-monitor-data/active/竞品快照_20260713.csv --markdown competitor-monitor-data/reports/变动报告_20260713.md
```
