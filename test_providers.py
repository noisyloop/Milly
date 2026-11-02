"""
test_providers.py — Tests for providers.py and multi-provider ChatEngine wiring.

No network or API keys needed: a fake provider stands in for real backends.

Run with:
    python -m pytest test_providers.py -v
"""

import tempfile
import unittest
from pathlib import Path

from audit import AuditLog
from chat import ChatEngine
from guardian import Guardian
from memory import Memory
from providers import Provider, ProviderError, ProviderRegistry, ThinkTagSplitter
from rag import RAG


def split_all(chunks):
    s = ThinkTagSplitter()
    out = []
    for c in chunks:
        out.extend(s.feed(c))
    out.extend(s.flush())
    text = "".join(t for k, t in out if k == "text")
    thinking = "".join(t for k, t in out if k == "thinking")
    return text, thinking


class TestThinkTagSplitter(unittest.TestCase):
    def test_plain_text_passthrough(self):
        self.assertEqual(split_all(["hello ", "world"]), ("hello world", ""))

    def test_inline_think_block(self):
        text, thinking = split_all(["<think>pondering</think>Answer"])
        self.assertEqual(text, "Answer")
        self.assertEqual(thinking, "pondering")

    def test_tag_split_across_chunks(self):
        text, thinking = split_all(["<th", "ink>a", "b</thi", "nk>", "done"])
        self.assertEqual(text, "done")
        self.assertEqual(thinking, "ab")

    def test_thinking_tag_variant(self):
        text, thinking = split_all(["<thinking>x</thinking>y"])
        self.assertEqual((text, thinking), ("y", "x"))

    def test_lone_angle_bracket_not_swallowed(self):
        self.assertEqual(split_all(["a < b", " and c <"]), ("a < b and c <", ""))


class TestRegistry(unittest.TestCase):
    def test_defaults_present(self):
        reg = ProviderRegistry({})
        for name in ("ollama", "openai", "anthropic"):
            self.assertIn(name, reg.names)

    def test_parse_spec_with_provider_prefix(self):
        reg = ProviderRegistry({})
        self.assertEqual(
            reg.parse_spec("anthropic:claude-opus-5-5", "ollama"),
            ("anthropic", "claude-opus-5-5"),
        )

    def test_parse_spec_keeps_ollama_tags(self):
        reg = ProviderRegistry({})
        self.assertEqual(reg.parse_spec("qwen3:8b", "ollama"), ("ollama", "qwen3:8b"))
        self.assertEqual(reg.parse_spec("llama3.2", "ollama"), ("ollama", "llama3.2"))

    def test_custom_named_provider(self):
        reg = ProviderRegistry(
            {"providers": {"lmstudio": {"type": "openai", "base_url": "http://x/v1", "local": True}}}
        )
        self.assertIn("lmstudio", reg.names)
        self.assertTrue(reg.is_local("lmstudio"))
        self.assertFalse(reg.is_local("anthropic"))
        self.assertEqual(reg.parse_spec("lmstudio:phi-4", "ollama"), ("lmstudio", "phi-4"))

    def test_legacy_ollama_host(self):
        reg = ProviderRegistry({"ollama_host": "http://box:11434"})
        self.assertEqual(reg.configs["ollama"]["host"], "http://box:11434")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ProviderError):
            ProviderRegistry({}).get("nope")

    def test_unknown_type_raises(self):
        reg = ProviderRegistry({"providers": {"weird": {"type": "carrier-pigeon"}}})
        with self.assertRaises(ProviderError):
            reg.get("weird")


class FakeProvider(Provider):
    type = "ollama"  # counts as local

    def __init__(self, chunks):
        super().__init__("fake", {})
        self.chunks = chunks
        self.calls = []

    def stream_chat(self, model, messages, temperature):
        self.calls.append((model, messages, temperature))
        yield from self.chunks


class TestEngineWithProvider(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        guardian = Guardian({})
        self.registry = ProviderRegistry({})
        self.fake = FakeProvider(
            [("thinking", "secret reasoning"), ("text", "Hello"), ("text", " there")]
        )
        self.registry._instances["ollama"] = self.fake
        self.engine = ChatEngine(
            config={"model": "m", "system_prompt": "sys", "rag": {"enabled": False}, "guardian": {}},
            guardian=guardian,
            memory=Memory(memory_dir=str(root / "memory")),
            audit=AuditLog(log_dir=str(root / "logs")),
            rag=RAG(config={}, guardian=guardian, docs_dir=str(root / "docs"), memory_dir=str(root / "memory")),
            providers=self.registry,
        )
        self.engine.new_session("t")

    def tearDown(self):
        self._tmp.cleanup()

    def test_thinking_hidden_and_not_stored(self):
        out = list(self.engine.chat("hi"))
        self.assertEqual(out, ["Hello", " there"])
        self.assertEqual(self.engine.history[-1]["content"], "Hello there")
        self.assertNotIn("secret", str(self.engine.memory.load("t")))

    def test_thinking_shown_when_enabled(self):
        self.engine.show_thinking = True
        out = list(self.engine.chat("hi"))
        self.assertIn(("thinking", "secret reasoning"), out)
        self.assertEqual(self.engine.history[-1]["content"], "Hello there")

    def test_system_prompt_and_model_passed(self):
        list(self.engine.chat("hi"))
        model, messages, temp = self.fake.calls[0]
        self.assertEqual(model, "m")
        self.assertEqual(messages[0], {"role": "system", "content": "sys"})
        self.assertEqual(messages[-1]["content"], "hi")

    def test_switch_model_with_provider_prefix(self):
        self.registry._instances["anthropic"] = FakeProvider([])
        self.engine.switch_model("anthropic:claude-opus-5-5")
        self.assertEqual(self.engine.model_label, "anthropic:claude-opus-5-5")
        self.assertFalse(self.engine.is_local)

    def test_switch_provider_uses_its_default_model(self):
        self.registry._instances["anthropic"] = FakeProvider([])
        self.engine.switch_provider("anthropic")
        self.assertEqual(self.engine.model, "claude-opus-5-5")

    def test_guardian_still_blocks_on_any_provider(self):
        from chat import InputBlockedError

        with self.assertRaises(InputBlockedError):
            list(self.engine.chat("x" * 10_000))
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
