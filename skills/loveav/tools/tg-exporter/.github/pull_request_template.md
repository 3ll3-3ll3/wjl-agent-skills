## Summary

<!-- What changed and why? -->

## Product invariants checked

- [ ] I read `AGENTS.md` and the current `HANDOFF.md` before making this change.
- [ ] This remains an independent batch exporter (no master DB / historical merge).
- [ ] Media files are not downloaded unless the user explicitly changed that requirement.
- [ ] Per-group export rules remain independent.
- [ ] The focused workspace still shows only selected working groups, not the full catalogue.
- [ ] JSON remains the authoritative export format.

## Telegram / read-state safety

- [ ] Normal export/list/refresh paths do not mark messages read.
- [ ] If this touches `导出后标已读`, it remains explicit, per-group, default-OFF, and unread-mode-only.
- [ ] Export failure cannot send a read acknowledgement.
- [ ] Read acknowledgement cannot advance beyond the frozen unread snapshot upper bound.
- [ ] Any Telegram write-side effect is described explicitly in this PR.

## qasync / GUI safety

- [ ] No blocking nested Qt modal loop was introduced into an async/Telethon-active path (`exec()`, static `QMessageBox.*`, static `QInputDialog.getText()`, etc.).
- [ ] Shutdown remains tolerant of Telethon disconnect lifecycle differences.

## Security

- [ ] No `api_hash`, phone, verification code, 2FA password, `.session`, chat body, or real user export was committed/logged.
- [ ] New diagnostics/logging were reviewed for secret leakage.

## Validation

- [ ] `pytest -q`
- [ ] GUI import check
- [ ] Windows PyInstaller build
- [ ] Packaged EXE `--smoke-test`
- [ ] Real Telegram E2E performed if this changes Telegram behavior, OR the pending E2E is explicitly recorded in `HANDOFF.md`.

## Documentation / handoff

- [ ] `HANDOFF.md` updated for any user-visible feature, critical fix, release-state change, new known issue, or real-account verification.
- [ ] `docs/DECISIONS.md` updated if a long-term design decision changed.
- [ ] `docs/JSON_COMPATIBILITY.md` updated if Desktop JSON compatibility changed.
- [ ] Release notes/version updated if this requires a new binary Release.

## Release impact

- [ ] Docs-only / no binary release needed.
- [ ] Binary release needed; target version: `vX.Y.Z`.
