"""
test_audit.py — Unit tests for audit.py, focused on session export.

Run with:
    python -m pytest test_audit.py -v
    # or without pytest:
    python test_audit.py
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from audit import AuditLog


class AuditTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.audit = AuditLog(log_dir=str(self.root / "logs"))
        self.export_dir = self.root / "exports"

    def tearDown(self):
        self._tmp.cleanup()


class TestExportSession(AuditTestCase):
    def test_export_creates_file_with_expected_name(self):
        self.audit.log("abc123", "session_start", model="llama3.2")
        path = self.audit.export_session("abc123", export_dir=str(self.export_dir))

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(path.name, f"audit_{date_str}_session-abc123.json")
        self.assertTrue(path.exists())

    def test_export_contains_all_events(self):
        self.audit.log("s1", "session_start", model="m")
        self.audit.log("s1", "injection_attempt", pattern="instruction_override",
                        input_hash="sha256:deadbeef", disposition="flagged")
        self.audit.log("s1", "chat_turn", disposition="ok")

        path = self.audit.export_session("s1", export_dir=str(self.export_dir))
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["session_id"], "s1")
        self.assertEqual(payload["event_count"], 3)
        self.assertEqual(len(payload["events"]), 3)
        events = payload["events"]
        self.assertTrue(all("timestamp" in e for e in events))
        # Pattern types are preserved.
        patterns = [e.get("pattern") for e in events if "pattern" in e]
        self.assertIn("instruction_override", patterns)

    def test_export_only_includes_target_session(self):
        self.audit.log("keep", "session_start")
        self.audit.log("other", "session_start")
        path = self.audit.export_session("keep", export_dir=str(self.export_dir))
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["event_count"], 1)
        self.assertTrue(all(e["session_id"] == "keep" for e in payload["events"]))

    def test_export_excludes_raw_input(self):
        # Audit entries only ever store hashes; the export must inherit that.
        self.audit.log("s1", "injection_attempt", input_hash="sha256:abc",
                        disposition="flagged")
        path = self.audit.export_session("s1", export_dir=str(self.export_dir))
        text = path.read_text(encoding="utf-8")
        self.assertIn("sha256:abc", text)
        # No "input" / "content" key carrying raw text should appear.
        payload = json.loads(text)
        for e in payload["events"]:
            self.assertNotIn("input", e)
            self.assertNotIn("content", e)

    def test_export_empty_session_is_valid(self):
        path = self.audit.export_session("nope", export_dir=str(self.export_dir))
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["event_count"], 0)
        self.assertEqual(payload["events"], [])

    def test_export_file_permissions_restricted(self):
        self.audit.log("s1", "session_start")
        path = self.audit.export_session("s1", export_dir=str(self.export_dir))
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_export_creates_directory(self):
        self.assertFalse(self.export_dir.exists())
        self.audit.log("s1", "session_start")
        self.audit.export_session("s1", export_dir=str(self.export_dir))
        self.assertTrue(self.export_dir.is_dir())


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
