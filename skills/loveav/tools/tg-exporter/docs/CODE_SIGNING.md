# Windows code signing and antivirus false positives

> **Status: DEFERRED / not an active project priority.**
>
> The user explicitly deprioritized 360/antivirus false-positive handling and code-signing work on 2026-08-28. Keep this document only as historical/reference material. Do **not** proactively resume SignPath applications, 360 appeals, signing integration, antivirus bypasses, or related work unless the user explicitly reopens the topic. See `AGENTS.md`, `HANDOFF.md`, and decision D-013 in `docs/DECISIONS.md`.

## Current state

The project currently publishes unsigned Windows binaries. Unsigned PyInstaller one-file executables can trigger reputation or heuristic warnings in antivirus products even when the source and build pipeline are clean.

An open-source license alone does **not** make antivirus products trust an executable. A self-signed certificate also does not provide normal public Windows publisher trust.

## Historical free open-source signing path: SignPath Foundation

This repository uses the MIT License and is intended to remain fully open source. That can make it eligible to apply for SignPath Foundation's free OSS code-signing program, subject to SignPath's review and acceptance.

If the user explicitly reopens signing work in the future, maintainers may revisit:

1. Apply at https://signpath.org/ for the open-source program.
2. Authorize the SignPath GitHub App for this repository when requested.
3. Create the SignPath project/artifact configuration for a Windows PE/EXE using Authenticode SHA-256.
4. Configure the approved signing policy.
5. Add the identifiers/tokens required by SignPath as GitHub repository secrets or variables according to SignPath's then-current integration documentation.
6. Update the release workflow so the artifact is signed after build/tests and before the GitHub Release is created.
7. Verify the signed output with `Get-AuthenticodeSignature` in CI.

Do not commit signing tokens, credentials or private keys to the repository.

## Historical 360 false-positive handling

360 has provided software false-positive reporting channels. If the user explicitly asks to resume that path, use the exact Release asset and its SHA-256, provide the public source/release URL, and use official vendor channels.

Do not make the application disable antivirus, add itself to trusted lists, evade scanning, or weaken host security.

## Distribution formats

The project currently publishes both:

- **one-file EXE**: easiest to download, but implemented as a self-extracting executable;
- **portable onedir ZIP**: contains the application EXE plus runtime DLLs/files and avoids the one-file self-extraction layer.

These formats remain useful regardless of whether code signing is pursued later.
