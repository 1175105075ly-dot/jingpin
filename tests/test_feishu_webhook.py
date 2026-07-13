from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import feishu_webhook  # noqa: E402


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"code":0,"msg":"success"}'


class FeishuWebhookTests(unittest.TestCase):
    def test_business_response_code_is_checked(self) -> None:
        self.assertTrue(feishu_webhook.response_ok(200, '{"code":0}'))
        self.assertTrue(feishu_webhook.response_ok(200, '{"StatusCode":0}'))
        self.assertFalse(feishu_webhook.response_ok(200, '{"code":19001}'))
        self.assertFalse(feishu_webhook.response_ok(500, '{"code":0}'))

    @mock.patch("feishu_webhook.time.sleep")
    @mock.patch("feishu_webhook.urllib.request.urlopen")
    def test_delivery_retries_transient_failure(self, urlopen: mock.Mock, sleep: mock.Mock) -> None:
        urlopen.side_effect = [urllib.error.URLError("temporary"), FakeResponse()]

        result = feishu_webhook.post_text("https://example.invalid/hook", "message", attempts=3)

        self.assertTrue(result["ok"])
        self.assertEqual(result["attempt"], 2)
        sleep.assert_called_once()

    def test_daily_report_is_organized_and_delivery_log_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot_path = root / "snapshot.json"
            report_path = root / "report.json"
            log_path = root / "delivery.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "snapshot_date": "20260713",
                        "records": [
                            {"asin": "B000000001", "status": "ok", "error_type": ""},
                            {"asin": "B000000002", "status": "unavailable", "error_type": "amazon_unavailable", "error_message": "page unavailable"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps(
                    {
                        "summary": {"material_changed_count": 1},
                        "changed": [
                            {
                                "asin": "B000000001",
                                "severity": "critical",
                                "changes": [{"field": "current_price", "old": 100, "new": 130}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            message = feishu_webhook.daily_report_message(snapshot_path, report_path, root / "snapshot.csv", root / "report.md")
            feishu_webhook.mark_delivered(log_path, "20260713", {"attempt": 1})
            delivered = feishu_webhook.read_delivery_log(log_path)["delivered"]

        self.assertIn("【需要先看】", message)
        self.assertIn("【关键业务变化】", message)
        self.assertIn("【本地文件】", message)
        self.assertIn("20260713", delivered)


if __name__ == "__main__":
    unittest.main()
