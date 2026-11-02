# Threat Model — Milly

**Version:** 1.0
**Date:** 2026-02-24
**Scope:** Personal, single-user, offline local AI assistant

---

## System Description

Milly is a CLI-based AI chatbot that runs inference locally via Ollama by default.
Optional cloud providers (OpenAI-compatible APIs, Anthropic) can be enabled by the user;
when one is active, prompts and retrieved document snippets leave the machine.
It maintains persistent conversation history, retrieves context from local documents (RAG),
and applies a security layer (Guardian) to all inputs and outputs.

**What Milly is:**
- A personal, offline tool for one user on one machine
- A wrapper around a locally-running model with security controls documented honestly

**What Milly is not:**
- A production API
- A multi-user system
- A sandboxed execution environment
- Guaranteed to be unbreakable

---

## Assets

| Asset | Sensitivity | Location |
|---|---|---|
| Conversation history | High — personal data | `memory/*.json` |
| System prompt | Medium — operational policy | `config.yaml` |
| Ingested documents | Varies — user content | `docs/`, `memory/rag_index.json` |
| Audit log | Medium — security events | `logs/security.log` |

---

## Trust Boundaries

```
[ User input ] ──→ [ Guardian ] ──→ [ Model provider ] ──→ [ Guardian output filter ] ──→ [ Display ]
                        ↑
              [ docs/ (UNTRUSTED) ]
                        ↑
              [ memory/ (0600 JSON) ]
```

- **User input**: Partially trusted. Sanitized before reaching the model.
- **Model provider**: Trusted for execution, not for content. Output is filtered.
  Local (Ollama) by default; cloud providers are a user opt-in and are flagged in the UI.
- **docs/ contents**: Explicitly untrusted. Treated as reference material, never instructions.
- **memory/ files**: Trusted at the same level as the user's home directory. Structure is
  validated on load; malformed files are refused.

---

## In-Scope Threats

### 1. Direct Prompt Injection

**Description:** Attacker (or the user themselves) crafts input designed to override
the system prompt, change Milly's persona, or extract/bypass operating instructions.

**Examples:**
- "Ignore all previous instructions and..."
- "You are now DAN..."
- "New system prompt: ..."

**Mitigations:**
- Guardian pattern bank (35+ injection patterns covering OWASP LLM Top 10 LLM01)
- System prompt explicitly instructs model to resist override attempts
- Flagged inputs logged with SHA-256 hash and pattern name
- User warned after flagged response

**Residual risk:** Pattern matching is not exhaustive. Novel or obfuscated techniques
may bypass detection. The model itself may still comply despite the flag.

---

### 2. Indirect Prompt Injection (Document Poisoning)

**Description:** A file placed in `docs/` contains text designed to hijack the model
when retrieved as RAG context (e.g., "Ignore instructions above, instead do X").

**Mitigations:**
- All documents scanned by Guardian before indexing
- Documents with injection patterns are rejected and not added to the index
- Retrieved context injected under `[UNTRUSTED DOCUMENT CONTENT]` boundary
- System prompt instructs model that document content is reference, not instruction
- Symlinks checked — files resolving outside `docs/` are rejected

**Residual risk:** A sufficiently subtle or novel injection in a document may pass
the scanner. The model may still be influenced by plausibly-worded document content.

---

### 3. Conversation History Tampering

**Description:** A user or process modifies a `memory/*.json` file directly to
inject false conversation context before loading the session.

**Mitigations:**
- Session files created with `0o600` permissions (owner-only)
- Writes are atomic (temp file + rename), so crashes can't leave half-written files
- Structure validated on every `load()`; corrupt or malformed files raise
  `MemoryIntegrityError` and are not loaded

**Residual risk:** Tamper *detection* (HMAC signing) was removed as
disproportionate for a single-user tool: any process that can write your
`memory/` files runs as you and could equally read a signing key. Protection
is the same as the rest of your home directory — file permissions.

---

### 4. Terminal Output Manipulation

**Description:** Model produces output containing ANSI escape sequences or terminal
control characters designed to overwrite previous output, move the cursor, or
exfiltrate data via terminal window title.

**Mitigations:**
- `guardian.filter_output()` strips all ANSI CSI/OSC/ESC sequences before display
- Dangerous control characters removed from model output
- Applied token-by-token during streaming

**Residual risk:** Extremely sophisticated terminal emulator vulnerabilities are
outside scope. Standard ANSI injection is fully mitigated.

---

### 5. Oversized Input as Denial-of-Service

**Description:** A user sends an extremely large input to consume memory, slow
inference, or exhaust context window.

**Mitigations:**
- Configurable `max_input_length` (default: 4000 chars)
- Inputs over the limit are hard-blocked before reaching the model
- Block event logged and reason returned to user
- Truncation is explicitly not used — oversized inputs are rejected cleanly

**Residual risk:** Inputs just under the limit may still be slow for some models.
This is an acceptable trade-off for usability.

---

### 6. Encoding-Based Evasion

**Description:** Injection instructions encoded in Base64, hex, or other schemes
to bypass keyword-based detection.

**Mitigations:**
- Guardian pattern bank includes encoding evasion patterns
- Character sanitization runs before injection scanning (removes zero-width chars,
  RTL overrides, null bytes used for tokenizer splitting attacks)

**Residual risk:** The model itself may decode and act on encoded content not
caught by pattern matching. This is a hard problem; pattern matching is a partial
mitigation, not a complete solution.

---

## Out-of-Scope Threats (Explicitly)

These are real threats that Milly does not address. Documenting non-coverage
is more useful than pretending.

| Threat | Reason Out of Scope |
|---|---|
| **Multi-user isolation** | Single-user tool. No authentication, no user separation. |
| **Network exposure** | Milly has no network listener. If you expose Ollama to the network, that's a separate problem. |
| **Model weight integrity** | Ollama manages model downloads. Milly trusts the local Ollama installation. |
| **Cloud provider data handling** | Opt-in only. Once enabled, what the provider does with prompts is governed by its own policies. |
| **Supply chain attacks on Python dependencies** | Pin your dependencies and audit them separately. Out of scope for this tool. |
| **Physical access to the machine** | If someone has physical access to your machine, Milly's controls don't help you. |
| **Adversarial model fine-tuning** | Milly uses models as provided by Ollama. Model behavior is not in scope. |
| **Side-channel attacks** | Timing, power, or cache attacks are out of scope for a personal CLI tool. |

---

## Security Assumptions

1. The user is the only person with access to the machine.
2. The OS enforces file permission semantics (`0o600` is meaningful).
3. The locally-running Ollama instance has not been compromised.
4. If a cloud provider is enabled, the user accepts that provider's data handling.
5. The model responds in natural language and does not execute arbitrary code.

---

## Known Limitations

- **Pattern matching is not AI-complete.** Guardian catches documented patterns;
  it does not understand semantics. A sufficiently creative prompt may not match
  any pattern while still manipulating the model.

- **The model has the final say.** Even flagged inputs get a response. Guardian
  records and warns; it cannot guarantee the model output is safe.

- **RAG is best-effort.** TF-IDF retrieval may not surface the most relevant
  document for a given query. The quality of answers depends on what's in `docs/`.

- **Audit log is local.** If the log file is deleted or the disk is wiped,
  event history is gone. The log is not replicated.

---

*Milly doesn't promise to be unbreakable. It promises to be honest about what it covers and why.*
