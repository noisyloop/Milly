"""
memory.py — Persistent conversation history.

Storage format (per session file, memory/<session>.json):
    {"version": 2, "history": [{"role": "user", "content": "..."}, ...]}

Properties:
  - Plain, human-readable JSON — easy to inspect, back up, or edit by hand.
  - Files created with mode 0o600 (owner read/write only).
  - Writes are atomic (temp file + rename), so a crash can't half-write a session.
  - User messages are written only after a successful model response.
  - History capped at max_history * 2 entries (user + assistant pairs).

Older sessions saved in the previous HMAC-signed envelope
({"data": "...", "sig": "..."}) still load; they are rewritten in the new
format the next time they are saved. The old memory/.key file is no longer
used and can be deleted.
"""

import json
import os
from pathlib import Path

FORMAT_VERSION = 2


class MemoryIntegrityError(Exception):
    """Raised when a session file is unreadable or not a valid session."""


def _valid_history(obj) -> bool:
    return isinstance(obj, list) and all(
        isinstance(m, dict) and isinstance(m.get("role"), str) and isinstance(m.get("content"), str)
        for m in obj
    )


class Memory:
    def __init__(self, memory_dir: str = "memory", max_history: int = 50):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_turns = max_history  # max user+assistant pairs

    # ------------------------------------------------------------------
    # Session paths
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        # Sanitize session ID to safe filename characters
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]
        if not safe:
            raise ValueError(f"Invalid session ID: '{session_id}' produces empty filename")
        return self.dir / f"{safe}.json"

    @staticmethod
    def _extract_history(stored) -> list[dict] | None:
        """Return the history list from a stored session, or None if not a session."""
        if not isinstance(stored, dict):
            return None
        if "history" in stored:
            hist = stored["history"]
        elif "data" in stored and "sig" in stored:  # legacy HMAC envelope
            try:
                hist = json.loads(stored["data"])
            except (TypeError, json.JSONDecodeError):
                return None
        else:
            return None
        return hist if _valid_history(hist) else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, session_id: str) -> list[dict]:
        """
        Load a session.
        Raises FileNotFoundError if the session does not exist.
        Raises MemoryIntegrityError if the file is corrupt or not a session.
        """
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found.")

        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise MemoryIntegrityError(
                f"Session '{session_id}' is corrupted ({e}). "
                "Use '/session new' to start fresh."
            ) from e

        history = self._extract_history(stored)
        if history is None:
            raise MemoryIntegrityError(
                f"Session '{session_id}' is not a valid session file. "
                "Use '/session new' to start fresh."
            )
        return history

    def save(self, session_id: str, history: list[dict]) -> None:
        """Atomically save session history with mode 0o600."""
        path = self._session_path(session_id)
        tmp = path.with_suffix(".json.tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                {"version": FORMAT_VERSION, "history": history},
                f,
                ensure_ascii=False,
                indent=1,
            )
        os.replace(tmp, path)

    def append(
        self,
        session_id: str,
        history: list[dict],
        role: str,
        content: str,
    ) -> list[dict]:
        """
        Return a new history list with the message appended.
        Trims to max_turns * 2 entries if needed.
        Does NOT save — caller saves only after model responds successfully.
        """
        updated = list(history)
        updated.append({"role": role, "content": content})
        cap = self.max_turns * 2
        if len(updated) > cap:
            updated = updated[-cap:]
        return updated

    def clear(self, session_id: str) -> list[dict]:
        """Clear history and persist the empty state."""
        self.save(session_id, [])
        return []

    def list_sessions(self) -> list[str]:
        """Return saved session IDs.

        The memory/ directory also holds non-session JSON (e.g. the RAG
        index), so only files that parse as sessions are listed.
        """
        sessions: list[str] = []
        for p in self.dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    stored = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if self._extract_history(stored) is not None:
                sessions.append(p.stem)
        return sorted(sessions)

    def delete_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
