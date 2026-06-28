# Milly

> **Local LLM with a built-in security layer.**  
> Auditable. Offline. Yours.

---

## What It Does

Milly is a security-hardened local LLM chatbot built on Ollama. The security layer is structural, not bolted on.

- **HMAC-signed conversation memory** — every memory entry is cryptographically signed; tampering is detectable
- **TF-IDF RAG engine** — local retrieval-augmented generation with no external API calls
- **Guardian layer** — prompt injection detection, input sanitization, output filtering
- **Full audit trail** — every inference, every memory read/write, logged and attributable
- **Offline by design** — no telemetry, no cloud fallback, no call-home behavior. For full air-gap, disable Ollama analytics with `OLLAMA_NO_ANALYTICS=1`
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

- **Mac:** Download the app from [ollama.com/download](https://ollama.com/download)
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

export OLLAMA_NO_ANALYTICS=1
python main.py
```

Your HMAC key is generated automatically on first launch and stays local in `memory/.key` at mode `0600`.

---

## Test Suite

```bash
pytest -v
```

Security properties are tested, not documented. If it's not in the test suite, it's not a feature.

---

## Knowledge Base

Drop `.md` or `.txt` files into the `docs/` folder, then run `/ingest` inside Milly. It indexes them locally using TF-IDF and retrieves relevant context on each query. No embeddings API, no internet, no cloud.

Included reference docs:

| File | Contents |
|------|----------|
| `guardian.md` | Attack pattern reference for the Guardian layer |
| `threats.md` | Threat models for local LLMs with risk matrix |
| `owasp-llm.md` | OWASP LLM Top 10 mapped to Milly's mitigations |
| `researcher.md` | Operator context for security research use |
| `opsec.md` | Operational security principles |
| `security.md` | Security concepts reference |

Add your own docs to extend the knowledge base. The `docs/` folder is in `.gitignore` — your personal knowledge stays local.

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
| `/model NAME` | Switch model at runtime |
| `/exit` | Quit |

---

## Tested Models

| Model | Size | Notes |
|-------|------|-------|
| llama3.2 | ~2GB | Default |
| gemma3:1b | ~800MB | Lightweight, fast |
| dolphin3 | ~2GB | Less filtered |
| mistral | ~4GB | Strong general purpose |

Any local model available via `ollama pull` should work. Cloud models (`:cloud` tag) are not supported — they break the offline guarantee.

---

## Offline Use

Once Ollama and your model are downloaded, Milly runs fully offline. No internet connection required. Verified working with wifi disabled.

---

## Privacy Controls

**Disable Ollama analytics:**

```bash
export OLLAMA_NO_ANALYTICS=1
```

Add to your shell profile (`~/.zshrc` or `~/.bashrc`) to make it permanent.

**Disable Milly's audit logging:**

Audit logs are stored locally in the `memory/` directory. To clear them:

```bash
rm memory/*.json
```

To clear your HMAC key and start fresh:

```bash
rm memory/.key
```

A new key is generated automatically on next launch.

**Clear all local data:**

```bash
rm -rf memory/
```

**Clear security logs:**

```bash
rm logs/security.log
```

Nothing is sent anywhere. Everything Milly stores is in `memory/`, `logs/`, and `docs/` on your machine. Delete them and it's gone.

---

## License

MIT
