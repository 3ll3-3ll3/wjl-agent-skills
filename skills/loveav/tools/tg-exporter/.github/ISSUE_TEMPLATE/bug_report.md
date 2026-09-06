---
name: Bug report
about: Report a Telegram connection, export, GUI, or Windows packaged-app problem
title: "bug: "
labels: ""
assignees: ""
---

## Version

- App version / Release tag:
- Single EXE or portable ZIP:
- Windows version:

## What happened

<!-- Describe the visible behavior. -->

## Expected behavior

<!-- What should have happened? -->

## Steps to reproduce

1.
2.
3.

## Mode / scope

- [ ] Login / connection
- [ ] Proxy
- [ ] Group selector / workspace
- [ ] Date-range export
- [ ] Current unread export
- [ ] Since-last export
- [ ] `导出后标已读`
- [ ] JSON output
- [ ] Shutdown / close
- [ ] Packaging / startup

## Log excerpt (redacted)

Paste only the smallest relevant part of:

```text
%APPDATA%\TelegramMultiChatExporter\logs\app.log
```

**Before posting, remove/redact all of the following:**

- `api_hash`
- phone number
- Telegram verification code
- 2FA password
- session file/content
- private chat message bodies
- any other credential or secret

```text
paste redacted lines here
```

## Screenshots

<!-- Attach a screenshot if it helps. Redact private chat content and credentials. -->

## Read-state safety note

If the bug involves `导出后标已读`, state:

- Was the checkbox ON or OFF?
- What was unread count before export?
- Did phone/Desktop read state change after export?
- Did new messages arrive after the last group catalogue refresh?

## Additional context

<!-- Anything else useful. -->
