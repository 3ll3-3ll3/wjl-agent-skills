# ADR-006 — Human Windows / Telegram E2E Is the Default Release Gate

## Status
Accepted, with an explicit one-release exception recorded for v0.3.1 on 2026-08-30.

## Context
GitHub Actions can validate unit/mock behavior, Windows packaging, OS Session lock, native exit codes and packaged smoke, but cannot safely use the user's real Telegram credentials/session or inspect the user's real `%APPDATA%` runtime state.

## Default decision
High-impact Telegram/runtime releases normally use:

```text
Automated Candidate green
→ frozen/hash-traceable Windows Candidate
→ local Windows / real-account acceptance
→ user explicit merge/release authorization
→ merge + formal Release workflow
```

CI never receives real Telegram credentials. Human checks must not be reported as PASS unless actually performed.

## v0.3.1 exception
On 2026-08-30, after the final automated Candidate was fully green, the user explicitly authorized publishing v0.3.1 immediately and explicitly waived waiting for the remaining real Windows / Telegram human E2E.

Therefore for **v0.3.1 only**:

```text
Automated Candidate green
→ user explicitly accepts residual real-environment risk and waives remaining human E2E
→ final authorization-only docs/workflow CI green
→ merge + formal Release workflow
```

The waived checks remain recorded as **not performed / unverified**, never as PASS.

This exception does not authorize Telegram writes and does not change the default rule for future releases. A future release requires human E2E again unless the user explicitly grants another release-specific waiver.

## Alternatives rejected
- silently pretending human E2E passed: false project history;
- putting real Telegram credentials in GitHub Actions: unacceptable secret/account risk;
- treating a Candidate artifact as a formal Release: breaks traceability.

## Consequences
Release documentation must distinguish automated PASS from human E2E waived/unverified. Formal binaries are rebuilt from merged main and the Release workflow must not overwrite an existing tag or Release.
