# First-login qasync modal-dialog failure

A Windows real-account test showed that Telegram transport was already healthy through the detected Windows/Clash proxy (`http://127.0.0.1:7890`), but a blocking Qt modal dialog caused qasync task re-entry while Telethon background tasks were active.

This is fixed in the subsequent application code by replacing blocking dialog execution inside async flows with non-blocking dialogs awaited through Qt signals.
