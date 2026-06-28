# OWASP LLM Top 10 Reference

The OWASP Top 10 for Large Language Model Applications identifies the most critical security risks. This is a quick reference for understanding each vulnerability and how it applies to local LLM deployments.

---

## LLM01: Prompt Injection

An attacker manipulates the LLM through crafted inputs, causing it to execute unintended actions. Direct injection overwrites the system prompt. Indirect injection manipulates through external content the model processes.

**Local relevance:** High. Even local models process untrusted input. RAG documents from external sources are an indirect injection vector.

**Milly mitigation:** Guardian layer with pattern matching, input sanitization before model and before RAG retrieval.

---

## LLM02: Insecure Output Handling

Model output is used downstream without validation — rendered as HTML, executed as code, passed to APIs, or used in database queries.

**Local relevance:** Medium. If Milly's output is piped into other tools or scripts, unsanitized output could cause harm.

**Milly mitigation:** Output sanitization strips ANSI escape sequences and flags responses that contradict system constraints.

---

## LLM03: Training Data Poisoning

Manipulation of pre-training or fine-tuning data to introduce vulnerabilities, backdoors, or biases into the model.

**Local relevance:** Low for pre-trained models from major labs. Higher if using community fine-tunes or models from unknown sources.

**Milly mitigation:** Model hash verification detects substitution. Use models from verified publishers only.

---

## LLM04: Model Denial of Service

Attacker causes resource-heavy operations through crafted inputs, consuming excessive compute, memory, or storage.

**Local relevance:** Medium. A very long input or recursive prompt could spike CPU/RAM on your local machine.

**Milly mitigation:** Guardian enforces configurable max input length. Oversized inputs are rejected and logged.

---

## LLM05: Supply Chain Vulnerabilities

Compromised components in the LLM supply chain — tampered models, poisoned training data, compromised plugins, or vulnerable dependencies.

**Local relevance:** High. You are pulling models from external registries and installing Python packages. Both are supply chain surfaces.

**Milly mitigation:** Model hash verification. Minimal dependency footprint. No plugin system. No external API calls.

---

## LLM06: Sensitive Information Disclosure

The model reveals confidential information through its responses — training data, system prompts, personal information, or proprietary content.

**Local relevance:** Medium. The model itself may leak training data. RAG content could be exposed through carefully crafted queries.

**Milly mitigation:** Audit logging tracks all queries and retrievals. Output sanitization flags suspicious disclosures. System prompt leaking attempts are detected by Guardian.

---

## LLM07: Insecure Plugin Design

Plugins with excessive permissions, insufficient input validation, or inadequate access control extend the attack surface.

**Local relevance:** N/A for Milly. No plugin system exists by design.

**Milly mitigation:** Not applicable. Deliberately excluded.

---

## LLM08: Excessive Agency

The model is given too much autonomy — ability to execute code, modify files, make API calls, or take actions without human confirmation.

**Local relevance:** Low for Milly. It is a chat interface, not an agent. It cannot execute code, modify files, or take autonomous actions.

**Milly mitigation:** Chat-only interface. No tool use. No code execution. No file system write access beyond its own memory.

---

## LLM09: Overreliance

Users trust model output without verification, leading to incorrect information being accepted as fact, flawed code being deployed, or bad advice being followed.

**Local relevance:** High. Smaller local models are less capable than frontier models and more likely to produce incorrect output.

**Milly mitigation:** Guardian flags unreliable responses. The audit trail creates a record for review. The README states that security properties are tested, not assumed.

---

## LLM10: Model Theft

Unauthorized access to, copying of, or exfiltration of the model weights, architecture, or fine-tuning data.

**Local relevance:** Low for open-weight models (they are already public). Higher for custom fine-tunes or proprietary models.

**Milly mitigation:** Air-gapped design prevents network exfiltration. Host security is the primary mitigation for physical access.