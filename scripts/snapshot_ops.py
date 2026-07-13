#!/usr/bin/env python3
"""Utilities for Amazon competitor monitoring snapshots.

The script intentionally avoids persisting user-pasted source URLs in daily
snapshots. Link normalization may keep collection URLs only in temporary task
files so the current manual run can be crawled.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse


SNAPSHOT_PREFIX = "竞品快照"
REPORT_PREFIX = "异动报告"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
AMAZON_HOST_RE = re.compile(r"(^|\.)amazon\.", re.IGNORECASE)
FIELD_ORDER = [
    "asin",
    "resolved_asin",
    "redirected_to_asin",
    "scraped_at",
    "status",
    "error_type",
    "error_message",
    "title",
    "image_url",
    "brand",
    "seller_name",
    "current_price",
    "list_price",
    "discount_percent",
    "limited_discount_status",
    "discount_ends_at",
    "has_coupon",
    "coupon_value",
    "coupon_valid_until",
    "coupon_minimum",
    "small_category_node",
    "small_bsr_rank",
    "main_category_rank",
    "variant_count",
    "is_out_of_stock",
    "variant_price_min",
    "variant_price_max",
    "rating",
    "review_count",
    "new_negative_review_today",
    "has_sp_ad",
    "has_sd_ad",
    "has_ld",
    "has_7_day_deal",
]


@dataclass(frozen=True)
class Thresholds:
    price_usd: float
    price_pct: float
    bsr_rank: int
    bsr_pct: float
    rating_drop: float
    review_count: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_stamp() -> str:
    return datetime.now().strftime("%Y%m%d")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def split_link_text(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        for chunk in re.split(r"[\s,，]+", line.strip()):
            if chunk:
                parts.append(chunk)
    return parts


def normalize_url(raw_url: str) -> str:
    return raw_url if "://" in raw_url else f"https://{raw_url}"


def split_asin_filter(value: str) -> list[str]:
    asins: list[str] = []
    for candidate in re.split(r"(?:\||%7C)", value, flags=re.IGNORECASE):
        cleaned = candidate.strip().upper()
        if ASIN_RE.match(cleaned) and cleaned not in asins:
            asins.append(cleaned)
    return asins


def extract_asins(raw_url: str) -> list[str]:
    parsed = urlparse(normalize_url(raw_url))
    if not AMAZON_HOST_RE.search(parsed.netloc):
        return []

    path_parts = [p for p in parsed.path.split("/") if p]
    for marker in ("dp", "gp/product", "product-reviews"):
        marker_parts = marker.split("/")
        for idx in range(0, len(path_parts) - len(marker_parts) + 1):
            if [p.lower() for p in path_parts[idx : idx + len(marker_parts)]] == marker_parts:
                next_idx = idx + len(marker_parts)
                if next_idx < len(path_parts) and ASIN_RE.match(path_parts[next_idx]):
                    return [path_parts[next_idx].upper()]

    query = parse_qs(parsed.query)
    for key in ("asin", "ASIN"):
        for value in query.get(key, []):
            if ASIN_RE.match(value):
                return [value.upper()]

    asins: list[str] = []
    for rh in query.get("rh", []) + query.get("RH", []):
        decoded = unquote(rh)
        match = re.search(r"(?:^|,)p_78:([^,]+)", decoded)
        if not match:
            continue
        for asin in split_asin_filter(match.group(1)):
            if asin not in asins:
                asins.append(asin)
    return asins


def is_collection_url(raw_url: str, asins: list[str]) -> bool:
    if len(asins) <= 1:
        return False
    parsed = urlparse(normalize_url(raw_url))
    query = parse_qs(parsed.query)
    return bool(query.get("rh") or query.get("RH"))


def canonical_url(asin: str, domain: str = "amazon.com") -> str:
    return f"https://www.{domain}/dp/{asin.upper()}"


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    if size < 1:
        raise ValueError("collection chunk size must be at least 1")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def collection_url_for_asins(raw_url: str, asins: list[str]) -> str:
    parsed = urlparse(normalize_url(raw_url))
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    replacement = "|".join(asins)
    replaced = False
    updated_pairs: list[tuple[str, str]] = []

    for key, value in query_pairs:
        if key.lower() == "rh" and not replaced:
            value, count = re.subn(
                r"((?:^|,)p_78:)[^,]+",
                lambda match: f"{match.group(1)}{replacement}",
                value,
                count=1,
                flags=re.IGNORECASE,
            )
            replaced = count == 1
        updated_pairs.append((key, value))

    if not replaced:
        raise ValueError("collection URL does not contain a replaceable p_78 ASIN filter")

    query = urlencode(updated_pairs, doseq=True, safe="|:,")
    return urlunparse(parsed._replace(query=query))


def normalize_links(input_path: Path, output_path: Path, domain: str, collection_chunk_size: int) -> dict[str, Any]:
    seen: set[str] = set()
    valid: list[dict[str, str]] = []
    invalid: list[str] = []
    crawl_pages: list[dict[str, Any]] = []

    for raw in split_link_text(read_text(input_path)):
        asins = extract_asins(raw)
        if not asins:
            invalid.append(raw)
            continue

        new_asins: list[str] = []
        for asin in asins:
            if asin in seen:
                continue
            seen.add(asin)
            new_asins.append(asin)
            valid.append({"asin": asin, "canonical_url": canonical_url(asin, domain)})

        if not new_asins:
            continue

        if is_collection_url(raw, asins):
            for asin_group in chunked(new_asins, collection_chunk_size):
                crawl_pages.append(
                    {
                        "url": collection_url_for_asins(raw, asin_group),
                        "expected_asins": asin_group,
                        "page_type": "collection",
                    }
                )
        else:
            for asin in new_asins:
                crawl_pages.append(
                    {
                        "url": canonical_url(asin, domain),
                        "expected_asins": [asin],
                        "page_type": "detail",
                    }
                )

    payload = {
        "created_at": utc_now_iso(),
        "count": len(valid),
        "collection_chunk_size": collection_chunk_size,
        "tasks": valid,
        "crawl_pages": crawl_pages,
        "invalid": invalid,
    }
    write_json(output_path, payload)
    return payload


def coerce_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        records = data["records"]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("records JSON must be a list or an object with a records list")

    normalized: list[dict[str, Any]] = []
    seen_asins: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("each record must be an object")
        asin = str(item.get("asin", "")).upper().strip()
        if not ASIN_RE.match(asin):
            raise ValueError(f"invalid ASIN in record: {asin!r}")
        if asin in seen_asins:
            raise ValueError(f"duplicate ASIN in records: {asin}")
        seen_asins.add(asin)
        record = {field: item.get(field) for field in FIELD_ORDER}
        for key, value in item.items():
            if key not in record and key != "source_url":
                record[key] = value
        record["asin"] = asin
        for field in ("resolved_asin", "redirected_to_asin"):
            value = str(record.get(field) or "").upper().strip()
            if value and not ASIN_RE.match(value):
                raise ValueError(f"invalid {field} in record {asin}: {value!r}")
            record[field] = value
        record.setdefault("scraped_at", utc_now_iso())
        record["scraped_at"] = record["scraped_at"] or utc_now_iso()
        record["status"] = record.get("status") or "ok"
        record["error_type"] = record.get("error_type") or ""
        record["error_message"] = record.get("error_message") or ""
        normalized.append(record)
    return sorted(normalized, key=lambda row: row["asin"])


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra_fields = sorted({key for record in records for key in record if key not in FIELD_ORDER})
    fields = FIELD_ORDER + extra_fields
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def write_snapshot(records_path: Path, pending_dir: Path, date: str) -> dict[str, Any]:
    records = coerce_records(read_json(records_path))
    pending_dir.mkdir(parents=True, exist_ok=True)
    base = f"{SNAPSHOT_PREFIX}_{date}"
    json_path = pending_dir / f"{base}.json"
    csv_path = pending_dir / f"{base}.csv"
    payload = {
        "snapshot_date": date,
        "created_at": utc_now_iso(),
        "record_count": len(records),
        "records": records,
    }
    write_json(json_path, payload)
    write_csv(csv_path, records)
    return {"json": str(json_path), "csv": str(csv_path), "record_count": len(records)}


def as_records_by_asin(snapshot: Any) -> dict[str, dict[str, Any]]:
    records = snapshot.get("records", snapshot) if isinstance(snapshot, dict) else snapshot
    return {str(row["asin"]).upper(): row for row in coerce_records(records)}


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)):
            return None
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


def pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return ((new - old) / old) * 100


def add_change(changes: list[dict[str, Any]], field: str, old: Any, new: Any, severity: str, reason: str) -> None:
    changes.append({"field": field, "old": old, "new": new, "severity": severity, "reason": reason})


def compare_pair(old: dict[str, Any], new: dict[str, Any], thresholds: Thresholds) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []

    old_price = to_float(old.get("current_price"))
    new_price = to_float(new.get("current_price"))
    if old_price is not None and new_price is not None and old_price != new_price:
        abs_delta = abs(new_price - old_price)
        pct_delta = abs(pct_change(old_price, new_price) or 0)
        if abs_delta >= thresholds.price_usd or pct_delta >= thresholds.price_pct:
            add_change(changes, "current_price", old_price, new_price, "critical", "price threshold exceeded")
        else:
            add_change(changes, "current_price", old_price, new_price, "info", "price changed below threshold")

    for field in ("has_coupon", "coupon_value", "limited_discount_status", "discount_percent", "has_ld", "has_7_day_deal"):
        if old.get(field) != new.get(field):
            add_change(changes, field, old.get(field), new.get(field), "warning", "promotion or coupon changed")

    for field in ("small_bsr_rank", "main_category_rank"):
        old_rank = to_int(old.get(field))
        new_rank = to_int(new.get(field))
        if old_rank is not None and new_rank is not None and old_rank != new_rank:
            delta = new_rank - old_rank
            pct_delta = abs(pct_change(float(old_rank), float(new_rank)) or 0)
            severity = (
                "critical"
                if field == "small_bsr_rank" and abs(delta) >= thresholds.bsr_rank and pct_delta >= thresholds.bsr_pct
                else "info"
            )
            direction = "worsened" if delta > 0 else "improved"
            add_change(changes, field, old_rank, new_rank, severity, f"rank {direction} ({pct_delta:.1f}%)")

    if old.get("is_out_of_stock") != new.get("is_out_of_stock"):
        add_change(changes, "is_out_of_stock", old.get("is_out_of_stock"), new.get("is_out_of_stock"), "critical", "stock status changed")

    old_rating = to_float(old.get("rating"))
    new_rating = to_float(new.get("rating"))
    if old_rating is not None and new_rating is not None and old_rating - new_rating >= thresholds.rating_drop:
        add_change(changes, "rating", old_rating, new_rating, "critical", "rating dropped")

    old_reviews = to_int(old.get("review_count"))
    new_reviews = to_int(new.get("review_count"))
    if old_reviews is not None and new_reviews is not None and new_reviews - old_reviews >= thresholds.review_count:
        add_change(changes, "review_count", old_reviews, new_reviews, "warning", "review count increased")

    if old.get("new_negative_review_today") != new.get("new_negative_review_today") and new.get("new_negative_review_today"):
        add_change(changes, "new_negative_review_today", old.get("new_negative_review_today"), new.get("new_negative_review_today"), "critical", "new negative review marker")

    for field in ("variant_count", "title", "image_url", "status", "error_type", "redirected_to_asin"):
        if old.get(field) != new.get(field):
            if field in ("status", "error_type", "redirected_to_asin"):
                severity = "critical" if new.get("status") != "ok" else "warning"
            elif field == "image_url":
                severity = "info"
            else:
                severity = "warning"
            add_change(changes, field, old.get(field), new.get(field), severity, f"{field} changed")

    return changes


def severity_for(changes: Iterable[dict[str, Any]]) -> str:
    severities = [change.get("severity") for change in changes]
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    return "info"


def failed_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in records
        if row.get("status") in {"failed", "unavailable", "invalid"} or row.get("error_type")
    ]


def compare_snapshots(old_path: Path, new_path: Path, out_path: Path, markdown_out: Path | None, thresholds: Thresholds) -> dict[str, Any]:
    old_exists = old_path.exists()
    old_records = as_records_by_asin(read_json(old_path)) if old_exists else {}
    new_records = as_records_by_asin(read_json(new_path))
    old_asins = set(old_records)
    new_asins = set(new_records)
    changed: list[dict[str, Any]] = []

    if old_exists:
        for asin in sorted(old_asins | new_asins):
            if asin not in old_records:
                changed.append({"asin": asin, "severity": "info", "status": "new", "changes": [{"field": "asin", "old": None, "new": asin, "severity": "info", "reason": "new ASIN in today's run"}]})
                continue
            if asin not in new_records:
                changed.append({"asin": asin, "severity": "critical", "status": "missing", "changes": [{"field": "asin", "old": asin, "new": None, "severity": "critical", "reason": "ASIN missing from today's snapshot"}]})
                continue
            changes = compare_pair(old_records[asin], new_records[asin], thresholds)
            if changes:
                changed.append({"asin": asin, "severity": severity_for(changes), "status": "changed", "changes": changes})

    failed = failed_records(new_records.values())
    unchanged = sorted((old_asins & new_asins) - {item["asin"] for item in changed}) if old_exists else sorted(new_asins)
    critical_count = sum(item["severity"] == "critical" for item in changed)
    warning_count = sum(item["severity"] == "warning" for item in changed)
    info_only_count = sum(item["severity"] == "info" for item in changed)
    report = {
        "created_at": utc_now_iso(),
        "baseline": not old_exists,
        "old_snapshot": str(old_path) if old_exists else "",
        "new_snapshot": str(new_path),
        "summary": {
            "old_count": len(old_records),
            "new_count": len(new_records),
            "changed_count": len(changed),
            "material_changed_count": critical_count + warning_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_only_count": info_only_count,
            "unchanged_count": len(unchanged),
            "failed_count": len(failed),
        },
        "changed": changed,
        "unchanged": unchanged,
        "failed": failed,
    }
    write_json(out_path, report)
    if markdown_out:
        write_markdown_report(markdown_out, report)
    return report


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        f"# {REPORT_PREFIX}",
        "",
        f"- Created: {report['created_at']}",
        f"- Baseline: {report.get('baseline', False)}",
        f"- Old count: {report['summary']['old_count']}",
        f"- New count: {report['summary']['new_count']}",
        f"- Changed: {report['summary']['changed_count']}",
        f"- Material changed: {report['summary'].get('material_changed_count', report['summary']['changed_count'])}",
        f"- Critical: {report['summary'].get('critical_count', 0)}",
        f"- Warning: {report['summary'].get('warning_count', 0)}",
        f"- Info only: {report['summary'].get('info_only_count', 0)}",
        f"- Unchanged: {report['summary']['unchanged_count']}",
        f"- Failed: {report['summary']['failed_count']}",
        "",
        "## Changes",
    ]
    if not report["changed"]:
        lines.append("- None")
    for item in report["changed"]:
        lines.append(f"- {item['asin']} [{item['severity']}] {item['status']}")
        for change in item["changes"]:
            lines.append(f"  - {change['field']}: {change['old']} -> {change['new']} ({change['reason']})")
    lines.append("")
    lines.append("## Failed")
    if not report["failed"]:
        lines.append("- None")
    for item in report["failed"]:
        lines.append(f"- {item.get('asin')}: {item.get('error_type')} {item.get('error_message')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def expected_asins_from_tasks(tasks_path: Path | None) -> set[str] | None:
    if tasks_path is None:
        return None
    payload = read_json(tasks_path)
    tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
    return {str(item.get("asin", "")).upper() for item in tasks if isinstance(item, dict) and ASIN_RE.match(str(item.get("asin", "")))}


def validate_snapshot(
    snapshot_path: Path,
    expected_count: int | None,
    max_failed_rate: float,
    expected_tasks: Path | None,
    min_core_coverage: float,
) -> dict[str, Any]:
    try:
        records = coerce_records(read_json(snapshot_path))
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "reason": str(exc), "snapshot": str(snapshot_path)}

    failed = failed_records(records)
    actual_asins = {row["asin"] for row in records}
    expected_asins = expected_asins_from_tasks(expected_tasks)
    count_ok = expected_count is None or len(records) == expected_count
    asin_set_ok = expected_asins is None or actual_asins == expected_asins
    missing_asins = sorted((expected_asins or set()) - actual_asins)
    unexpected_asins = sorted(actual_asins - (expected_asins or actual_asins))
    failed_rate = (len(failed) / len(records)) if records else 1.0
    ok_records = [row for row in records if row.get("status") == "ok" and not row.get("error_type")]
    core_fields = ("title", "current_price", "rating", "small_bsr_rank", "main_category_rank")
    core_coverage = {
        field: (sum(row.get(field) not in (None, "") for row in ok_records) / len(ok_records)) if ok_records else 0.0
        for field in core_fields
    }
    core_coverage_ok = bool(ok_records) and all(value >= min_core_coverage for value in core_coverage.values())
    status_errors = [
        row["asin"]
        for row in records
        if row.get("status") not in {"ok", "failed", "unavailable", "invalid"}
        or (row.get("status") != "ok" and not row.get("error_type"))
    ]
    status_ok = not status_errors
    ok = count_ok and asin_set_ok and failed_rate <= max_failed_rate and core_coverage_ok and status_ok
    result = {
        "ok": ok,
        "record_count": len(records),
        "expected_count": expected_count,
        "count_ok": count_ok,
        "asin_set_ok": asin_set_ok,
        "missing_asins": missing_asins,
        "unexpected_asins": unexpected_asins,
        "failed_count": len(failed),
        "failed_rate": failed_rate,
        "max_failed_rate": max_failed_rate,
        "core_coverage": core_coverage,
        "min_core_coverage": min_core_coverage,
        "core_coverage_ok": core_coverage_ok,
        "status_ok": status_ok,
        "status_errors": status_errors,
    }
    if not ok:
        result["reason"] = "snapshot integrity check failed"
    return result


def rotate(active_dir: Path, archive_dir: Path, pending_dir: Path, date: str) -> dict[str, Any]:
    active_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    base = f"{SNAPSHOT_PREFIX}_{date}"
    pending_files = [pending_dir / f"{base}.json", pending_dir / f"{base}.csv"]
    missing = [str(path) for path in pending_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"pending snapshot pair is incomplete: {missing}")

    archived: list[str] = []
    activated: list[str] = []
    archive_moves: list[tuple[Path, Path]] = []
    activation_moves: list[tuple[Path, Path]] = []
    try:
        for existing in list(active_dir.glob(f"{SNAPSHOT_PREFIX}_*.json")) + list(active_dir.glob(f"{SNAPSHOT_PREFIX}_*.csv")):
            target = archive_dir / existing.name
            if target.exists():
                target = archive_dir / f"{existing.stem}_{datetime.now().strftime('%H%M%S')}{existing.suffix}"
            shutil.move(str(existing), str(target))
            archive_moves.append((target, existing))
            archived.append(str(target))

        for pending in pending_files:
            target = active_dir / pending.name
            shutil.move(str(pending), str(target))
            activation_moves.append((target, pending))
            activated.append(str(target))
    except Exception:
        for target, original in reversed(activation_moves):
            if target.exists():
                shutil.move(str(target), str(original))
        for target, original in reversed(archive_moves):
            if target.exists():
                shutil.move(str(target), str(original))
        raise

    return {"date": date, "archived": archived, "activated": activated}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon competitor monitor snapshot utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    normalize = sub.add_parser("normalize-links", help="Parse pasted Amazon links into temporary ASIN tasks")
    normalize.add_argument("--input", required=True, type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    normalize.add_argument("--domain", default="amazon.com")
    normalize.add_argument("--collection-chunk-size", type=int, default=8)

    write = sub.add_parser("write-snapshot", help="Write pending JSON and CSV snapshot files")
    write.add_argument("--records", required=True, type=Path)
    write.add_argument("--pending-dir", required=True, type=Path)
    write.add_argument("--date", default=today_stamp())

    compare = sub.add_parser("compare", help="Compare old and new snapshot JSON files")
    compare.add_argument("--old", required=True, type=Path)
    compare.add_argument("--new", required=True, type=Path)
    compare.add_argument("--out", required=True, type=Path)
    compare.add_argument("--markdown-out", type=Path)
    compare.add_argument("--price-usd-threshold", type=float, default=1.0)
    compare.add_argument("--price-pct-threshold", type=float, default=5.0)
    compare.add_argument("--bsr-rank-threshold", type=int, default=500)
    compare.add_argument("--bsr-pct-threshold", type=float, default=20.0)
    compare.add_argument("--rating-drop-threshold", type=float, default=0.2)
    compare.add_argument("--review-count-threshold", type=int, default=10)

    validate = sub.add_parser("validate-snapshot", help="Validate snapshot completeness before rotation")
    validate.add_argument("--snapshot", required=True, type=Path)
    validate.add_argument("--expected-count", type=int)
    validate.add_argument("--expected-tasks", type=Path)
    validate.add_argument("--max-failed-rate", type=float, default=0.25)
    validate.add_argument("--min-core-coverage", type=float, default=0.9)

    rotate_cmd = sub.add_parser("rotate", help="Archive active snapshots and activate pending snapshots")
    rotate_cmd.add_argument("--active-dir", required=True, type=Path)
    rotate_cmd.add_argument("--archive-dir", required=True, type=Path)
    rotate_cmd.add_argument("--pending-dir", required=True, type=Path)
    rotate_cmd.add_argument("--date", default=today_stamp())
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    if args.command == "normalize-links":
        result = normalize_links(args.input, args.output, args.domain, args.collection_chunk_size)
    elif args.command == "write-snapshot":
        result = write_snapshot(args.records, args.pending_dir, args.date)
    elif args.command == "compare":
        thresholds = Thresholds(
            price_usd=args.price_usd_threshold,
            price_pct=args.price_pct_threshold,
            bsr_rank=args.bsr_rank_threshold,
            bsr_pct=args.bsr_pct_threshold,
            rating_drop=args.rating_drop_threshold,
            review_count=args.review_count_threshold,
        )
        result = compare_snapshots(args.old, args.new, args.out, args.markdown_out, thresholds)
    elif args.command == "validate-snapshot":
        result = validate_snapshot(
            args.snapshot,
            args.expected_count,
            args.max_failed_rate,
            args.expected_tasks,
            args.min_core_coverage,
        )
    elif args.command == "rotate":
        result = rotate(args.active_dir, args.archive_dir, args.pending_dir, args.date)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "validate-snapshot" and not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
