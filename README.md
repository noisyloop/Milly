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
- **Air-gapped by design** — no telemetry, no cloud fallback, no call-home behavior
- **Full audit trail** — every inference, every memory read/write, logged and attributable
- **136 passing tests** — security properties are verified, not assumed

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

```bash
# Requirements: Python 3.10+, Ollama running locally
git clone https://github.com/m0rs3c0d3/milly
cd milly
pip install -r requirements.txt

# Generate your HMAC key (stays local, stays yours)
python scripts/keygen.py

# Run
python milly.py
```

---

## Test Suite

```bash
pytest tests/ -v
# 136 tests — covering memory integrity, RAG retrieval, audit logging, injection resistance
```

Security properties are tested, not documented. If it's not in the test suite, it's not a feature.

---

## Use Cases

- **Security researchers** who need an LLM that won't leak context
- **Red teamers** building AI-assisted tooling for air-gapped environments  
- **Engineers** in regulated industries where cloud LLM use is prohibited
- **Anyone** who actually read the terms of service for the big providers

---

## License

MIT

---

*Part of the [m0rs3c0d3](https://github.com/m0rs3c0d3) security tooling portfolio.*
