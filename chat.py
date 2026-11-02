"""
chat.py — Conversation engine for Milly.

Wires together Guardian → RAG → model provider → Memory → AuditLog.

The model backend is pluggable (see providers.py): Ollama by default, or any
OpenAI-compatible endpoint, or Anthropic.

Usage:
    engine = ChatEngine(config, guardian, memory, audit, rag)

    # Stream a response
    try:
        for token in engine.chat("Hello"):
            print(token, end="", flush=True)
    except InputBlockedError as e:
        print(f"Blocked: {e}")

After each call, engine.last_guard_result holds the GuardianResult
(useful to surface flagged-but-not-blocked warnings to the user).
"""

import uuid
from typing import Generator, Optional

from audit import AuditLog
from guardian import Guardian, GuardianResult
from memory import Memory
from providers import ProviderRegistry
from rag import RAG


class InputBlockedError(Exception):
    """Raised when Guardian hard-blocks an input."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ChatEngine:
    def __init__(
        self,
        config: dict,
        guardian: Guardian,
        memory: Memory,
        audit: AuditLog,
        rag: RAG,
        providers: Optional[ProviderRegistry] = None,
    ):
        self.config = config
        self.guardian = guardian
        self.memory = memory
        self.audit = audit
        self.rag = rag

        self.model: str = config.get("model", "llama3.2")
        self.temperature: float = float(config.get("temperature", 0.7))
        self.system_prompt: str = config.get("system_prompt", "You are Milly, a helpful local AI assistant.")
        self.rag_enabled: bool = config.get("rag", {}).get("enabled", True)
        self.show_thinking: bool = bool(config.get("show_thinking", False))

        self.providers = providers or ProviderRegistry(config)
        self.provider_name: str = config.get("provider", "ollama")
        if self.provider_name not in self.providers.configs:
            self.provider_name = "ollama"

        self.session_id: str = self._new_session_id()
        self.history: list[dict] = []
        self.last_guard_result: Optional[GuardianResult] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    @staticmethod
    def _new_session_id() -> str:
        return uuid.uuid4().hex[:6]

    def new_session(self, name: Optional[str] = None, persist: bool = True) -> str:
        self.session_id = name or self._new_session_id()
        self.history = []
        # Persist the (empty) session immediately so `/session new NAME` can be
        # loaded right away. The automatic startup session passes
        # persist=False so empty throwaway sessions don't pile up on disk —
        # it gets saved after the first reply.
        if persist:
            self.memory.save(self.session_id, self.history)
        self.audit.log(self.session_id, "session_start", model=self.model_label)
        return self.session_id

    def load_session(self, session_id: str) -> None:
        """Load an existing session. Raises MemoryIntegrityError on tamper."""
        self.history = self.memory.load(session_id)
        self.session_id = session_id
        self.audit.log(self.session_id, "session_load", model=self.model_label)

    def clear_history(self) -> None:
        self.history = self.memory.clear(self.session_id)
        self.audit.log(self.session_id, "history_clear", model=self.model_label)

    @property
    def model_label(self) -> str:
        return f"{self.provider_name}:{self.model}"

    @property
    def is_local(self) -> bool:
        return self.providers.is_local(self.provider_name)

    def switch_model(self, spec: str) -> None:
        """Switch model. Accepts "model" or "provider:model"."""
        old = self.model_label
        provider, model = self.providers.parse_spec(spec, self.provider_name)
        if provider != self.provider_name:
            self.providers.get(provider)  # fail fast on missing SDK / key
        self.provider_name, self.model = provider, model
        self.audit.log(
            self.session_id, "model_switch", model=self.model_label, previous=old
        )

    def switch_provider(self, name: str, model: Optional[str] = None) -> None:
        old = self.model_label
        self.providers.get(name)  # validates name, SDK, credentials
        self.provider_name = name
        if model:
            self.model = model
        else:
            default = self.providers.configs[name].get("default_model")
            if default:
                self.model = default
        self.audit.log(
            self.session_id, "model_switch", model=self.model_label, previous=old
        )

    def list_models(self) -> list[str]:
        return self.providers.get(self.provider_name).list_models()

    # ------------------------------------------------------------------
    # Core chat
    # ------------------------------------------------------------------

    def chat(self, raw_input: str) -> Generator:
        """
        Process raw_input through the security + inference pipeline.

        Yields streamed response tokens.
        Raises InputBlockedError if Guardian hard-blocks the input.
        Stores last_guard_result for the caller to inspect.
        """
        # --- Guardian check ---
        guard = self.guardian.check(raw_input)
        self.last_guard_result = guard

        if guard.blocked:
            self.audit.log(
                self.session_id,
                "input_blocked",
                model=self.model_label,
                reason=guard.reason,
                input_hash=guard.input_hash,
                disposition="blocked",
            )
            raise InputBlockedError(guard.reason)

        if guard.flagged and self.config.get("guardian", {}).get("log_detections", True):
            self.audit.log(
                self.session_id,
                "injection_attempt",
                model=self.model_label,
                pattern=guard.pattern,
                input_hash=guard.input_hash,
                disposition="flagged",
            )

        user_input = guard.sanitized_input

        # --- RAG retrieval ---
        rag_context = ""
        if self.rag_enabled and self.rag.doc_count > 0:
            docs = self.rag.query(user_input)
            if docs:
                rag_context = self.rag.format_context(docs)

        # --- Build message list ---
        messages = self._build_messages(user_input, rag_context)

        # --- Stream from the model provider ---
        # Reasoning ("thinking") from reasoning models is never stored in
        # history; it is yielded as a ("thinking", text) tuple only when
        # show_thinking is on. Answer tokens are yielded as plain strings.
        full_response = ""
        try:
            provider = self.providers.get(self.provider_name)
            for kind, token in provider.stream_chat(
                self.model, messages, self.temperature
            ):
                if not token:
                    continue
                token = self.guardian.filter_output(token)
                if kind == "thinking":
                    if self.show_thinking:
                        yield ("thinking", token)
                    continue
                full_response += token
                yield token

        except Exception as e:
            self.audit.log(
                self.session_id, "inference_error", model=self.model_label, error=str(e)
            )
            raise

        # --- Persist only after successful response ---
        if full_response:
            self.history = self.memory.append(
                self.session_id, self.history, "user", user_input
            )
            self.history = self.memory.append(
                self.session_id, self.history, "assistant", full_response
            )
            self.memory.save(self.session_id, self.history)

        self.audit.log(
            self.session_id, "chat_turn", model=self.model_label, disposition="ok"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_messages(self, user_input: str, rag_context: str) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)

        content = user_input
        if rag_context:
            content = f"{rag_context}\n\nUser: {user_input}"

        messages.append({"role": "user", "content": content})
        return messages

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        s = {
            "model": self.model,
            "provider": self.provider_name,
            "local": self.is_local,
            "session_id": self.session_id,
            "history_turns": len(self.history) // 2,
            "rag_docs": self.rag.doc_count,
            "rag_enabled": self.rag_enabled,
            "guardian_injection_detection": self.guardian.injection_detection,
            "guardian_output_sanitization": self.guardian.output_sanitization,
            "temperature": self.temperature,
        }
        s.update({"guardian_" + k: v for k, v in self.guardian.stats().items()})
        return s
