# Milly

> **The first local LLM with a built-in security layer.**  
> Air-gapped. Auditable. Yours.

---

## The Problem With Every Other Local LLM

You ran Ollama. You ran LM Studio. You pointed a chat UI at your local model and felt good about "privacy."

But nothing was watching the memory layer. Nothing was signing the conversation history. Nothing was auditing what the model was being told — or what it was learning about you. You had local compute. You didn't have local security.

Milly fixes that.

---

## What It Does

Milly is a security-hardened local LLM chatbot built on Ollama with an architecture designed from first principles around integrity, auditability, and isolation. It's not a wrapper. The security layer is structural.

- **HMAC-signed conversation memory** — every memory entry is cryptographically signed; tampering is detectable
- **TF-IDF RAG engine** — local retrieval-augmented generation with no external API calls, ever
- **Air-gapped by design** — no telemetry, no cloud fallback, no call-home behavior; verified working fully offline
- **Full audit trail** — every inference, every memory read/write, logged and attributable
- **157 passing tests** — security properties are verified, not assumed

---

## Security Architecture

```
┌──────────────────────────────────────────────┐
│                  User Input                  │
└───────────────────┬──────────────────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│              Input Sanitizer                 │
│        (injection detection layer)           │
└───────────────────┬──────────────────────────┘
                    │
       ┌────────────┴────────────┐
       │                         │
┌──────▼──────┐         ┌────────▼────────┐
│  TF-IDF RAG │         │   HMAC Memory   │
│   Retrieval │         │     Store       │
│   (local)   │         │  (signed blobs) │
└──────┬──────┘         └────────┬────────┘
       │                         │
       └────────────┬────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│              Ollama Inference                │
│           (local model, no egress)           │
└───────────────────┬──────────────────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│              Audit Logger                    │
│     (tamper-evident inference record)        │
└──────────────────────────────────────────────┘
```

---

## Threat Mitigations

| Threat | Mitigation |
|--------|-----------|
| Memory poisoning | HMAC signing on all stored memory entries |
| Prompt injection via RAG | Input sanitization before retrieval |
| Data exfiltration | Zero network egress by architecture |
| History tampering | Cryptographic audit trail |
| Model substitution | Local model hash verification |

---

## Quick Start

**1. Install Ollama**

- **Mac:** Download the app from [ollama.com/download](https://ollama.com/download) — installs to your menu bar, no manual `ollama serve` needed
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

**2. Pull a model**

```bash
ollama pull llama3.2       # default, ~2GB
ollama pull gemma3:1b      # lightweight alternative, ~800MB
```

**3. Clone and run**

```bash
git clone https://github.com/noisyloop/Milly
cd Milly
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Your HMAC key is generated automatically on first launch and stays local in `memory/.key` at mode `0600`.

---

## Test Suite

```bash
pytest -v
# Covering the Guardian security layer (injection detection, sanitization,
# output filtering) plus memory integrity (HMAC signing, tamper rejection).
```

Security properties are tested, not documented. If it's not in the test suite, it's not a feature.

---

## RAG — Drop In Your Own Docs

Put any `.txt` or `.md` files in the `docs/` folder, then run `/ingest` inside Milly. It indexes them locally using TF-IDF and retrieves relevant context on each query — no embeddings API, no internet, no cloud.

```
/ingest
```

Ask Milly about anything in your docs. It cites from your local knowledge base, not the internet.

---

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show commands |
| `/status` | Model, memory, RAG, and Guardian stats |
| `/audit` | Security event summary for this session |
| `/ingest` | Re-index the `docs/` folder |
| `/clear` | Clear session history |
| `/session new NAME` | Start a new named session |
| `/session list` | List saved sessions |
| `/session load NAME` | Load a previous session |
| `/model NAME` | Switch model (e.g. `/model gemma3:1b`) |
| `/exit` | Quit |

---

## Tested Models

| Model | Size | Notes |
|-------|------|-------|
| llama3.2 | ~2GB | Default |
| gemma3:1b | ~800MB | Lightweight, works well |

Any model available via `ollama pull` should work. Switch with `/model NAME` at runtime.

---

## Offline Use

Once Ollama and your model are pulled, Milly runs fully offline. No internet connection required. This is the air-gapped claim in practice — verified.

---

## Use Cases

- **Security researchers** who need an LLM that won't leak context
- **Red teamers** building AI-assisted tooling for air-gapped environments
- **Engineers** in regulated industries where cloud LLM use is prohibited
- **Anyone** who actually read the terms of service for the big providers

---

## License

MIT
