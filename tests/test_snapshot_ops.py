from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import snapshot_ops  # noqa: E402


def record(asin: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "asin": asin,
        "status": "ok",
        "error_type": "",
        "error_message": "",
        "title": f"Product {asin}",
        "current_price": 100.0,
        "rating": 4.5,
        "small_bsr_rank": 1000,
        "main_category_rank": 10000,
    }
    value.update(overrides)
    return value


class SnapshotOpsTests(unittest.TestCase):
    def test_collection_urls_are_chunked_in_groups_of_eight(self) -> None:
        asins = [f"B{i:09d}" for i in range(1, 18)]
        url = "https://www.amazon.com/s?rh=p_78:" + "|".join(asins)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            links = root / "links.txt"
            tasks = root / "tasks.json"
            links.write_text(url, encoding="utf-8")

            payload = snapshot_ops.normalize_links(links, tasks, "amazon.com", 8)

        self.assertEqual([len(page["expected_asins"]) for page in payload["crawl_pages"]], [8, 8, 1])
        for page in payload["crawl_pages"]:
            self.assertEqual(snapshot_ops.extract_asins(page["url"]), page["expected_asins"])

    def test_duplicate_asin_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate ASIN"):
            snapshot_ops.coerce_records([record("B000000001"), record("B000000001")])

    def test_validation_requires_exact_expected_asin_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / "snapshot.json"
            tasks = root / "tasks.json"
            snapshot.write_text(json.dumps({"records": [record("B000000001")]}), encoding="utf-8")
            tasks.write_text(
                json.dumps({"tasks": [{"asin": "B000000001"}, {"asin": "B000000002"}]}),
                encoding="utf-8",
            )

            result = snapshot_ops.validate_snapshot(snapshot, 2, 0.25, tasks, 0.9)

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_asins"], ["B000000002"])

    def test_small_bsr_drift_and_image_url_are_info_only(self) -> None:
        thresholds = snapshot_ops.Thresholds(1.0, 5.0, 500, 20.0, 0.2, 10)
        old = record("B000000001", small_bsr_rank=10000, image_url="old")
        new = record("B000000001", small_bsr_rank=10500, main_category_rank=13000, image_url="new")

        changes = snapshot_ops.compare_pair(old, new, thresholds)

        self.assertEqual({change["severity"] for change in changes}, {"info"})

    def test_rotate_activates_only_requested_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            active = root / "active"
            archive = root / "archive"
            pending = root / "pending"
            active.mkdir()
            pending.mkdir()
            for suffix in ("json", "csv"):
                (active / f"竞品快照_20260712.{suffix}").write_text("old", encoding="utf-8")
                (pending / f"竞品快照_20260713.{suffix}").write_text("new", encoding="utf-8")
                (pending / f"竞品快照_20260711.{suffix}").write_text("stale", encoding="utf-8")

            result = snapshot_ops.rotate(active, archive, pending, "20260713")

            self.assertEqual(len(result["activated"]), 2)
            self.assertEqual(sorted(path.name for path in active.iterdir()), ["竞品快照_20260713.csv", "竞品快照_20260713.json"])
            self.assertTrue((pending / "竞品快照_20260711.json").exists())
            self.assertTrue((archive / "竞品快照_20260712.json").exists())

    def test_incomplete_pending_pair_preserves_active_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            active = root / "active"
            archive = root / "archive"
            pending = root / "pending"
            active.mkdir()
            pending.mkdir()
            old = active / "竞品快照_20260712.json"
            old.write_text("old", encoding="utf-8")
            (pending / "竞品快照_20260713.json").write_text("new", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                snapshot_ops.rotate(active, archive, pending, "20260713")

            self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
