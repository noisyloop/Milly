# Threat Models for Local LLMs

This document covers threat scenarios specific to locally hosted LLMs and how to think about them.

---

## Why Local LLMs Still Have Threats

Running a model locally eliminates cloud-specific risks like data collection, API logging, and third-party access. It does not eliminate:

- Attacks via input (prompt injection)
- Attacks via documents (RAG poisoning)
- Attacks via the model itself (supply chain)
- Attacks via the environment (host compromise)
- Attacks via output (distillation, exfiltration by humans)

Local compute solves the privacy problem. It does not solve the integrity problem. That is what this tool exists to address.

---

## Threat: Model Supply Chain Attack

### What It Is
A model downloaded from a registry has been tampered with — backdoored weights, poisoned training data, or a trojaned quantization.

### How It Works
- Attacker publishes a model with a similar name to a popular one
- Model behaves normally on most inputs but has hidden behaviors on specific trigger phrases
- Quantized versions may introduce subtle behavior changes not present in the original
- GGUF files from unofficial sources may contain modified weights

### Mitigations
- Verify model checksums against official sources
- Use only models from verified publishers on Ollama and Hugging Face
- Compare model outputs against known-good baselines
- Monitor for unexpected behavior on specific input patterns
- Milly's model hash verification feature detects substitution

---

## Threat: Memory Poisoning

### What It Is
An attacker with access to the local machine modifies stored conversation memory to inject false context into future sessions.

### How It Works
- Attacker gains file system access (malware, physical access, shared machine)
- Modifies JSON memory files to include false context
- Next time the model loads memory, it treats poisoned context as legitimate history
- Model behavior shifts based on injected false memories

### Mitigations
- HMAC signing on all memory entries (Milly does this)
- Signature verification on every memory load
- Reject any memory entry with an invalid signature
- Alert on tamper detection
- Store HMAC key with restricted file permissions (0600)

---

## Threat: RAG Document Poisoning

### What It Is
A malicious document placed in the docs folder contains hidden directives designed to hijack the model's behavior when retrieved.

### How It Works
- User downloads a document from an untrusted source
- Document contains embedded directives that mimic system-level messaging
- When the RAG engine retrieves this document as context, the model follows the embedded directives
- The attack is indirect — the user never typed the injection, it came from a document

### Mitigations
- Input sanitization on all retrieved content before it reaches the model
- Pattern matching on RAG content for known injection signatures
- Treat all RAG content as untrusted input, not as system-level directives
- Log all RAG retrievals in the audit trail
- Only place trusted documents in the docs folder

---

## Threat: Conversation History Tampering

### What It Is
Modification of the stored conversation log to alter the record of what was asked and answered.

### How It Works
- Attacker modifies session JSON files
- Removes evidence of specific queries or responses
- Alters timestamps to create false timelines
- Inserts fabricated conversation turns

### Mitigations
- Cryptographic audit trail with hash chaining
- Each log entry references the hash of the previous entry
- Tampering with any entry breaks the chain
- Audit log stores input hashes, never raw content
- Regular audit review to detect chain breaks

---

## Threat: Model Output Distillation

### What It Is
Someone systematically queries your model to capture its responses and use them to train a smaller model that replicates its behavior.

### How It Works
- Attacker sends thousands of carefully crafted prompts
- Captures all responses as training data
- Trains a smaller model on the prompt-response pairs
- The result is a distilled copy of your model's behavior

### Limitations of Detection
- If done via API or programmatic access, query patterns can be detected
- If done by manually copying responses, no technical detection is possible
- Rate limiting and session fingerprinting can slow but not prevent it
- Output watermarking can prove provenance but not prevent copying

### Mitigations
- Monitor for systematic query patterns (eBPF-based detection)
- Rate limiting on inference requests
- Session fingerprinting to identify automated access
- Output watermarking for provenance tracking
- Access control on who can reach the inference endpoint

---

## Threat: Host Compromise

### What It Is
The machine running the local LLM is compromised, giving the attacker access to everything — model, memory, documents, keys.

### How It Works
- Standard endpoint compromise (malware, phishing, exploit)
- Once on the host, attacker has access to the HMAC signing key, all conversation memory, all RAG documents, the model weights, and the audit log

### Mitigations
- Standard endpoint security (patching, AV, EDR)
- Full disk encryption
- HMAC key stored with minimal permissions
- Air-gapped deployment for highest sensitivity
- Separate machine for sensitive research vs daily use
- Monitor for unauthorized process access to Milly directories

---

## Threat: Inference Side Channel

### What It Is
An observer on the same machine or network can infer what you are asking the model by monitoring resource usage patterns.

### How It Works
- GPU and CPU utilization patterns correlate with input length and complexity
- Memory access patterns during inference can leak information
- Token generation timing can reveal response length and structure
- Network monitoring (even on localhost) can observe request and response sizes

### Mitigations
- Run on a dedicated machine, not shared
- Localhost-only binding (no network exposure)
- Process isolation where possible
- Padding responses to uniform length (not implemented in most tools)

---

## Threat: Plugin and Extension Attacks

### What It Is
Third-party plugins, extensions, or integrations that connect to the LLM introduce new attack surfaces.

### How It Works
- A plugin requests access to conversation history
- A browser extension intercepts model responses
- An integration sends queries to an external service
- A tool-use plugin executes commands based on model output

### Mitigations
- Milly has no plugin system by design
- No external integrations, no browser extensions
- All functionality is built-in and auditable
- Any future extensions should be reviewed for data egress

---

## Risk Matrix

| Threat | Likelihood | Impact | Milly Mitigation |
|--------|-----------|--------|-----------------|
| Prompt injection | High | Medium | Guardian input sanitizer |
| RAG document poisoning | Medium | High | Input sanitization on retrieval |
| Memory poisoning | Low | High | HMAC signing |
| History tampering | Low | Medium | Cryptographic audit trail |
| Model supply chain | Low | Critical | Hash verification |
| Output distillation | Medium | Medium | Partial (pattern detection only) |
| Host compromise | Low | Critical | Minimal (out of scope) |
| Inference side channel | Low | Low | Localhost-only binding |
| Plugin attacks | N/A | N/A | No plugin system by design |