"""
providers.py — Model backends for Milly.

Milly talks to models through a small Provider interface so the same chat
loop (Guardian -> RAG -> model -> memory) works with:

  ollama     Local models via Ollama (default — nothing leaves the machine)
  openai     Any OpenAI-compatible endpoint: OpenAI, LM Studio, llama.cpp
             server, vLLM, OpenRouter, Groq, ... (needs `pip install openai`)
  anthropic  Claude models via the Anthropic API (needs `pip install anthropic`)

You can define as many named providers as you like in config.yaml, e.g. an
"lmstudio" provider of type openai pointing at localhost:1234.

Thinking / reasoning models (qwen3, deepseek-r1, gpt-oss, ...) are handled
too: reasoning arrives either in a separate `thinking` field or inline as
<think>...</think> tags. Both are separated from the answer, so reasoning is
never stored in history and is only shown when `show_thinking: true`.

Every provider's stream_chat() yields (kind, text) tuples where kind is
"text" (answer) or "thinking" (reasoning).
"""

from __future__ import annotations

import os
from typing import Iterator, Optional

Chunk = tuple[str, str]  # ("text" | "thinking", content)

LOCAL_TYPES = {"ollama"}


class ProviderError(Exception):
    """Raised for configuration or SDK problems with a provider."""


# ---------------------------------------------------------------------------
# <think> tag splitter (for models that inline their reasoning)
# ---------------------------------------------------------------------------

class ThinkTagSplitter:
    """Split a token stream into answer text and <think>...</think> reasoning.

    Tags may be split across chunk boundaries, so a small tail is held back
    until it can't be the start of a tag.
    """

    OPEN = ("<think>", "<thinking>")
    CLOSE = ("</think>", "</thinking>")

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def _tags(self) -> tuple[str, ...]:
        return self.CLOSE if self._in_think else self.OPEN

    def feed(self, text: str) -> list[Chunk]:
        self._buf += text
        out: list[Chunk] = []
        while self._buf:
            tags = self._tags()
            idx, tag = min(
                ((self._buf.find(t), t) for t in tags if t in self._buf),
                default=(-1, ""),
            )
            if idx >= 0:
                if idx:
                    out.append(self._emit(self._buf[:idx]))
                self._buf = self._buf[idx + len(tag):]
                self._in_think = not self._in_think
                continue
            # No complete tag — keep back any suffix that could start one.
            hold = 0
            for t in tags:
                for n in range(min(len(t) - 1, len(self._buf)), 0, -1):
                    if t.startswith(self._buf[-n:]):
                        hold = max(hold, n)
                        break
            emit, self._buf = self._buf[: len(self._buf) - hold], self._buf[len(self._buf) - hold:]
            if emit:
                out.append(self._emit(emit))
            break
        return out

    def flush(self) -> list[Chunk]:
        out = [self._emit(self._buf)] if self._buf else []
        self._buf = ""
        return out

    def _emit(self, s: str) -> Chunk:
        return ("thinking" if self._in_think else "text", s)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class Provider:
    type: str = "base"

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg or {}

    @property
    def is_local(self) -> bool:
        return self.type in LOCAL_TYPES or bool(self.cfg.get("local", False))

    def stream_chat(
        self, model: str, messages: list[dict], temperature: Optional[float]
    ) -> Iterator[Chunk]:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        return []

    def _api_key(self, default_env: str) -> Optional[str]:
        if self.cfg.get("api_key"):
            return str(self.cfg["api_key"])
        env = self.cfg.get("api_key_env", default_env)
        return os.environ.get(env) if env else None


class OllamaProvider(Provider):
    type = "ollama"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        import ollama  # core dependency

        self._client = ollama.Client(host=self.cfg.get("host", "http://localhost:11434"))

    def stream_chat(self, model, messages, temperature):
        options = {} if temperature is None else {"temperature": temperature}
        if self.cfg.get("num_ctx"):
            options["num_ctx"] = int(self.cfg["num_ctx"])
        stream = self._client.chat(
            model=model, messages=messages, stream=True, options=options
        )
        splitter = ThinkTagSplitter()
        for chunk in stream:
            msg = getattr(chunk, "message", None)
            if msg is None and isinstance(chunk, dict):  # very old SDKs
                msg = chunk.get("message", {})
            get = (lambda k: msg.get(k)) if isinstance(msg, dict) else (lambda k: getattr(msg, k, None))
            thinking = get("thinking")
            if thinking:
                yield ("thinking", thinking)
            content = get("content")
            if content:
                yield from splitter.feed(content)
        yield from splitter.flush()

    def list_models(self) -> list[str]:
        resp = self._client.list()
        models = getattr(resp, "models", None)
        if models is None and isinstance(resp, dict):
            models = resp.get("models", [])
        names = []
        for m in models or []:
            name = getattr(m, "model", None) or (m.get("model") or m.get("name") if isinstance(m, dict) else None)
            if name:
                names.append(name)
        return sorted(names)


class OpenAICompatProvider(Provider):
    """OpenAI Chat Completions API — also LM Studio, llama.cpp, vLLM, OpenRouter..."""

    type = "openai"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        try:
            import openai
        except ImportError as e:
            raise ProviderError(
                f"Provider '{name}' needs the openai package: pip install openai"
            ) from e
        self._openai = openai
        base_url = self.cfg.get("base_url")
        api_key = self._api_key("OPENAI_API_KEY")
        if not api_key:
            if base_url and "api.openai.com" not in base_url:
                api_key = "not-needed"  # local servers usually ignore the key
            else:
                env = self.cfg.get("api_key_env", "OPENAI_API_KEY")
                raise ProviderError(f"Provider '{name}': set the {env} environment variable.")
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self._send_temperature = self.cfg.get("send_temperature", True)

    def stream_chat(self, model, messages, temperature):
        kwargs = dict(model=model, messages=messages, stream=True)
        if temperature is not None and self._send_temperature:
            kwargs["temperature"] = temperature
        try:
            stream = self._client.chat.completions.create(**kwargs)
        except self._openai.BadRequestError as e:
            # Reasoning models (o-series, gpt-5...) reject custom temperature.
            if "temperature" in str(e).lower() and "temperature" in kwargs:
                kwargs.pop("temperature")
                self._send_temperature = False
                stream = self._client.chat.completions.create(**kwargs)
            else:
                raise
        splitter = ThinkTagSplitter()
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                yield ("thinking", reasoning)
            if delta.content:
                yield from splitter.feed(delta.content)
        yield from splitter.flush()

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self._client.models.list())


class AnthropicProvider(Provider):
    """Claude models via the official Anthropic SDK."""

    type = "anthropic"

    # Models that accept the server-side refusal fallback ("default" form).
    _FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError(
                f"Provider '{name}' needs the anthropic package: pip install anthropic"
            ) from e
        kwargs = {}
        key = self._api_key("ANTHROPIC_API_KEY")
        if key:
            kwargs["api_key"] = key
        if self.cfg.get("base_url"):
            kwargs["base_url"] = self.cfg["base_url"]
        try:
            self._client = anthropic.Anthropic(**kwargs)
        except anthropic.AnthropicError as e:
            raise ProviderError(
                f"Provider '{name}': no Anthropic credentials found. "
                "Set ANTHROPIC_API_KEY or run `ant auth login`."
            ) from e

    def stream_chat(self, model, messages, temperature):
        # Claude takes the system prompt as a top-level field. Temperature is
        # intentionally not sent: current Claude models reject sampling params.
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] in ("user", "assistant")]
        kwargs = dict(
            model=model,
            max_tokens=int(self.cfg.get("max_tokens", 64000)),
            messages=convo,
        )
        if system:
            kwargs["system"] = system
        if self.cfg.get("effort"):
            kwargs["output_config"] = {"effort": self.cfg["effort"]}

        use_fallback = self.cfg.get("refusal_fallback", True) and model in self._FALLBACK_MODELS
        if use_fallback:
            ctx = self._client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            ctx = self._client.messages.stream(**kwargs)

        with ctx as stream:
            for text in stream.text_stream:
                if text:
                    yield ("text", text)
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield ("text", "\n[The model declined to answer this request.]")
        elif final.stop_reason == "max_tokens":
            yield ("text", "\n[Response cut off at max_tokens.]")

    def list_models(self) -> list[str]:
        return [m.id for m in self._client.models.list()]


PROVIDER_TYPES: dict[str, type[Provider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEFAULT_PROVIDERS: dict[str, dict] = {
    "ollama": {"type": "ollama", "host": "http://localhost:11434"},
    "openai": {"type": "openai", "api_key_env": "OPENAI_API_KEY"},
    "anthropic": {
        "type": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-5-5",
    },
}


class ProviderRegistry:
    """Named provider configs, instantiated lazily on first use.

    Lazy instantiation means a missing optional SDK (openai / anthropic) or a
    missing API key only matters if you actually switch to that provider.
    """

    def __init__(self, cfg: dict):
        merged = {k: dict(v) for k, v in DEFAULT_PROVIDERS.items()}
        # Back-compat: top-level ollama_host from older configs.
        if cfg.get("ollama_host"):
            merged["ollama"]["host"] = cfg["ollama_host"]
        for name, pcfg in (cfg.get("providers") or {}).items():
            pcfg = dict(pcfg or {})
            base = merged.get(name, {})
            base.update(pcfg)
            base.setdefault("type", name)
            merged[name] = base
        self.configs = merged
        self._instances: dict[str, Provider] = {}

    @property
    def names(self) -> list[str]:
        return list(self.configs)

    def get(self, name: str) -> Provider:
        if name not in self.configs:
            raise ProviderError(
                f"Unknown provider '{name}'. Known: {', '.join(self.names)}"
            )
        if name not in self._instances:
            pcfg = self.configs[name]
            ptype = pcfg.get("type", name)
            cls = PROVIDER_TYPES.get(ptype)
            if cls is None:
                raise ProviderError(
                    f"Provider '{name}' has unknown type '{ptype}'. "
                    f"Use one of: {', '.join(PROVIDER_TYPES)}"
                )
            self._instances[name] = cls(name, pcfg)
        return self._instances[name]

    def is_local(self, name: str) -> bool:
        pcfg = self.configs.get(name, {})
        return pcfg.get("type", name) in LOCAL_TYPES or bool(pcfg.get("local", False))

    def parse_spec(self, spec: str, current_provider: str) -> tuple[str, str]:
        """Parse a model spec into (provider, model).

        "anthropic:claude-opus-5-5" -> ("anthropic", "claude-opus-5-5")
        "qwen3:8b"                  -> (current_provider, "qwen3:8b")

        The prefix is only treated as a provider when it names a configured
        provider, so Ollama tags like "llama3.2:3b" keep working.
        """
        head, sep, tail = spec.partition(":")
        if sep and head in self.configs and tail:
            return head, tail
        return current_provider, spec
