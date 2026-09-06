from __future__ import annotations

import os
import time
from pathlib import Path


class FileBusyError(RuntimeError):
    """Raised when another process owns an OS-level file lease."""


class FileLease:
    """Small cross-platform advisory file lock.

    The file itself is only a carrier. Ownership is determined by the OS lock,
    never by whether the path exists. Windows locks the first byte with
    ``msvcrt.locking``; Unix uses ``flock``.
    """

    def __init__(self, path: Path, *, busy_message: str = "资源正在被另一个进程使用。"):
        self.path = Path(path)
        self.busy_message = busy_message
        self._file = None

    def acquire(self, *, timeout: float = 0.0, poll_interval: float = 0.05) -> None:
        if self._file is not None:
            return
        deadline = time.monotonic() + max(0.0, timeout)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            file = self.path.open("a+b")
            try:
                file.seek(0, os.SEEK_END)
                if file.tell() == 0:
                    file.write(b"0")
                    file.flush()
                file.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file = file
                return
            except (OSError, BlockingIOError) as exc:
                file.close()
                if time.monotonic() >= deadline:
                    raise FileBusyError(self.busy_message) from exc
                time.sleep(max(0.01, poll_interval))

    def release(self) -> None:
        file = self._file
        if file is None:
            return
        try:
            file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        finally:
            file.close()
            self._file = None

    @property
    def acquired(self) -> bool:
        return self._file is not None

    def __enter__(self) -> "FileLease":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class SessionBusyError(FileBusyError):
    """Raised when another TG Exporter process owns the shared Telegram session."""


class SessionLease(FileLease):
    def __init__(self, session_base: Path):
        super().__init__(
            session_base.with_suffix(".session.lock"),
            busy_message=(
                "Telegram Session 正在被另一个 TG Exporter/tgctl/daemon 进程使用。"
                "请等待旧进程退出后重试。"
            ),
        )

    def acquire(self, *, timeout: float = 0.0, poll_interval: float = 0.05) -> None:
        try:
            super().acquire(timeout=timeout, poll_interval=poll_interval)
        except FileBusyError as exc:
            raise SessionBusyError(str(exc)) from exc
