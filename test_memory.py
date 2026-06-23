"""
test_memory.py — Unit tests for memory.py

Run with:
    python -m pytest test_memory.py -v
    # or without pytest:
    python test_memory.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from memory import Memory, MemoryIntegrityError


SAMPLE_HISTORY = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "hi there"},
]


class MemoryTestCase(unittest.TestCase):
    """Base class giving each test an isolated, temporary memory dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.mem = Memory(memory_dir=str(self.dir))

    def tearDown(self):
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

class TestKeyManagement(MemoryTestCase):
    def test_key_created_on_init(self):
        key_path = self.dir / ".key"
        self.assertTrue(key_path.exists())
        self.assertEqual(len(key_path.read_bytes()), 32)

    def test_key_file_permissions_restricted(self):
        mode = (self.dir / ".key").stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_key_reused_across_instances(self):
        first = (self.dir / ".key").read_bytes()
        Memory(memory_dir=str(self.dir))  # second instance, same dir
        second = (self.dir / ".key").read_bytes()
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# Save / load round-trip
# ---------------------------------------------------------------------------

class TestSaveLoad(MemoryTestCase):
    def test_round_trip(self):
        self.mem.save("sess1", SAMPLE_HISTORY)
        loaded = self.mem.load("sess1")
        self.assertEqual(loaded, SAMPLE_HISTORY)

    def test_session_file_permissions_restricted(self):
        self.mem.save("sess1", SAMPLE_HISTORY)
        mode = (self.dir / "sess1.json").stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_load_missing_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            self.mem.load("does-not-exist")

    def test_unicode_round_trip(self):
        history = [{"role": "user", "content": "café — naïve — 日本語 — 🔐"}]
        self.mem.save("u", history)
        self.assertEqual(self.mem.load("u"), history)


# ---------------------------------------------------------------------------
# Integrity / tamper detection
# ---------------------------------------------------------------------------

class TestIntegrity(MemoryTestCase):
    def _write_raw(self, session_id: str, obj) -> None:
        (self.dir / f"{session_id}.json").write_text(
            json.dumps(obj), encoding="utf-8"
        )

    def test_tampered_data_rejected(self):
        self.mem.save("sess1", SAMPLE_HISTORY)
        path = self.dir / "sess1.json"
        stored = json.loads(path.read_text())
        # Flip the stored history without updating the signature.
        stored["data"] = json.dumps([{"role": "user", "content": "evil"}])
        path.write_text(json.dumps(stored), encoding="utf-8")
        with self.assertRaises(MemoryIntegrityError):
            self.mem.load("sess1")

    def test_wrong_key_rejected(self):
        self.mem.save("sess1", SAMPLE_HISTORY)
        # A different Memory instance with a different key cannot verify.
        other_dir = tempfile.TemporaryDirectory()
        try:
            other = Memory(memory_dir=other_dir.name)
            # Copy the signed file into the other dir, keeping its (foreign) sig.
            (Path(other_dir.name) / "sess1.json").write_text(
                (self.dir / "sess1.json").read_text(), encoding="utf-8"
            )
            with self.assertRaises(MemoryIntegrityError):
                other.load("sess1")
        finally:
            other_dir.cleanup()

    def test_non_dict_envelope_rejected(self):
        # Regression: a bare list (e.g. the RAG index file) must not crash
        # load() with an AttributeError — it should be a clean integrity error.
        self._write_raw("rag_index", [])
        with self.assertRaises(MemoryIntegrityError):
            self.mem.load("rag_index")

    def test_missing_sig_rejected(self):
        self._write_raw("nosig", {"data": "[]"})
        with self.assertRaises(MemoryIntegrityError):
            self.mem.load("nosig")


# ---------------------------------------------------------------------------
# append() trimming and immutability
# ---------------------------------------------------------------------------

class TestAppend(MemoryTestCase):
    def test_append_does_not_mutate_input(self):
        original = list(SAMPLE_HISTORY)
        result = self.mem.append("s", original, "user", "new")
        self.assertEqual(len(original), len(SAMPLE_HISTORY))
        self.assertEqual(result[-1], {"role": "user", "content": "new"})

    def test_append_trims_to_cap(self):
        mem = Memory(memory_dir=str(self.dir), max_history=2)  # cap = 4 entries
        history: list[dict] = []
        for i in range(10):
            history = mem.append("s", history, "user", f"msg{i}")
        self.assertEqual(len(history), 4)
        # Most recent entries are retained.
        self.assertEqual(history[-1]["content"], "msg9")


# ---------------------------------------------------------------------------
# Session listing / clearing / deletion
# ---------------------------------------------------------------------------

class TestSessionManagement(MemoryTestCase):
    def test_list_sessions_sorted(self):
        self.mem.save("bravo", SAMPLE_HISTORY)
        self.mem.save("alpha", SAMPLE_HISTORY)
        self.assertEqual(self.mem.list_sessions(), ["alpha", "bravo"])

    def test_list_sessions_excludes_non_session_json(self):
        # Regression: the RAG index lives in memory/ but is not a session.
        self.mem.save("real", SAMPLE_HISTORY)
        (self.dir / "rag_index.json").write_text("[]", encoding="utf-8")
        self.assertEqual(self.mem.list_sessions(), ["real"])

    def test_list_sessions_skips_corrupt_json(self):
        self.mem.save("real", SAMPLE_HISTORY)
        (self.dir / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.mem.list_sessions(), ["real"])

    def test_clear_persists_empty(self):
        self.mem.save("s", SAMPLE_HISTORY)
        self.assertEqual(self.mem.clear("s"), [])
        self.assertEqual(self.mem.load("s"), [])

    def test_delete_session(self):
        self.mem.save("s", SAMPLE_HISTORY)
        self.mem.delete_session("s")
        self.assertNotIn("s", self.mem.list_sessions())

    def test_delete_missing_is_noop(self):
        self.mem.delete_session("never-existed")  # must not raise


# ---------------------------------------------------------------------------
# Session-ID sanitization
# ---------------------------------------------------------------------------

class TestSessionIdSanitization(MemoryTestCase):
    def test_path_traversal_stripped(self):
        # "../../etc/passwd" must not escape the memory dir.
        self.mem.save("../../etc/passwd", SAMPLE_HISTORY)
        created = list(self.dir.glob("*.json"))
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].name.endswith(".json"))
        # File stays inside the memory dir.
        self.assertEqual(created[0].parent.resolve(), self.dir.resolve())

    def test_empty_after_sanitization_raises(self):
        with self.assertRaises(ValueError):
            self.mem.save("///", SAMPLE_HISTORY)


# ---------------------------------------------------------------------------
# Entry point for running without pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
