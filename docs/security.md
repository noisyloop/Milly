# Security Concepts Reference

## Threat Modeling
- STRIDE: A framework covering six threat categories — Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, and Elevation of Privilege
- NIST AI RMF: Risk management framework for AI systems covering Govern, Map, Measure, and Manage functions
- Attack surface: The sum of all points where an attacker can try to enter or extract data

## eBPF
Extended Berkeley Packet Filter. Allows sandboxed programs to run in the Linux kernel without changing kernel source or loading modules. Used for observability, networking, and security tooling.

## HMAC
Hash-based Message Authentication Code. Used to verify both data integrity and authenticity. Milly uses HMAC to sign every memory entry so tampering is detectable.

## Prompt Injection
An attack where malicious input tricks an LLM into deviating from its intended behavior or revealing sensitive information. Common approaches include attempts to override the model's directives, assume a different persona, or claim false authority. Milly's Guardian layer detects and flags these patterns.

## RAG
Retrieval-Augmented Generation. A technique where relevant documents are retrieved and injected into the model's context before inference. Milly uses TF-IDF for local retrieval with no external API calls.

## TF-IDF
Term Frequency-Inverse Document Frequency. A statistical measure used to evaluate how relevant a word is to a document in a collection. Used by Milly's RAG engine to find the most relevant context chunks for each query.

## Air-Gapped
A system physically or logically isolated from unsecured networks. In Milly's context this means zero network egress by architecture — no telemetry, no cloud fallback, no call-home behavior. Verified working fully offline.

## Passive Fingerprinting
Identifying devices or systems by observing their behavior without sending active probes.

## Supply Chain Attack
An attack that targets less-secure elements in the supply chain. In LLM contexts this includes model poisoning, dependency confusion, and distillation attacks.

## Responsible Disclosure
The practice of reporting security vulnerabilities to the affected vendor before making them public, giving them time to patch.