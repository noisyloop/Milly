"""
test_session.py — Session create/load round-trip tests for ChatEngine.

Regression coverage for the bug where `/session new NAME` created a session
that `/session load NAME` then reported as "not found", because a new session
was only written to disk after the first successful chat turn.

Run with:
    python -m pytest test_session.py -v
    # or without pytest:
    python test_session.py
"""

import sys
import tempfile
import unittest
from pathlib import Path

from audit import AuditLog
from chat import ChatEngine
from guardian import Guardian
from memory import Memory, MemoryIntegrityError
from rag import RAG


def build_engine(root: Path) -> ChatEngine:
    """Construct a ChatEngine backed by isolated temp directories.

    No network is touched: the ollama client is created but never called, since
    these tests exercise only session persistence (new/load), not inference.
    """
    guardian = Guardian({})
    audit = AuditLog(log_dir=str(root / "logs"))
    memory = Memory(memory_dir=str(root / "memory"))
    rag = RAG(
        config={},
        guardian=guardian,
        docs_dir=str(root / "docs"),
        memory_dir=str(root / "memory"),
    )
    cfg = {
        "model": "llama3.2",
        "temperature": 0.7,
        "ollama_host": "http://localhost:11434",
        "system_prompt": "You are Milly.",
        "rag": {"enabled": False},
        "guardian": {},
    }
    return ChatEngine(
        config=cfg, guardian=guardian, memory=memory, audit=audit, rag=rag
    )


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.engine = build_engine(self.root)

    def tearDown(self):
        self._tmp.cleanup()


class TestNewSessionPersistence(SessionTestCase):
    def test_new_session_is_immediately_loadable(self):
        # The original bug: create then load reported "not found".
        self.engine.new_session("test1")
        # Loading must not raise FileNotFoundError.
        self.engine.load_session("test1")
        self.assertEqual(self.engine.session_id, "test1")

    def test_new_session_appears_in_list(self):
        self.engine.new_session("test1")
        self.assertIn("test1", self.engine.memory.list_sessions())

    def test_new_session_writes_file(self):
        self.engine.new_session("test1")
        self.assertTrue((self.root / "memory" / "test1.json").exists())


class TestSessionRoundTrip(SessionTestCase):
    def test_message_survives_save_and_load(self):
        # 1. Create a session.
        self.engine.new_session("test1")

        # 2. Add a message (mirrors what ChatEngine.chat persists after a turn).
        self.engine.history = self.engine.memory.append(
            "test1", self.engine.history, "user", "remember this token: xyzzy"
        )
        self.engine.history = self.engine.memory.append(
            "test1", self.engine.history, "assistant", "got it"
        )
        self.engine.memory.save("test1", self.engine.history)

        # 3. Load the session in a *fresh* engine (same memory dir).
        engine2 = build_engine(self.root)
        engine2.load_session("test1")

        # 4. Confirm the message is there.
        contents = [m["content"] for m in engine2.history]
        self.assertIn("remember this token: xyzzy", contents)
        self.assertIn("got it", contents)

    def test_load_unknown_session_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.engine.load_session("never-created")

    def test_new_session_signed_envelope_verifies(self):
        # A freshly created empty session must pass HMAC verification on load.
        self.engine.new_session("fresh")
        try:
            loaded = self.engine.memory.load("fresh")
        except MemoryIntegrityError as e:  # pragma: no cover - failure path
            self.fail(f"new session failed integrity check: {e}")
        self.assertEqual(loaded, [])


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
