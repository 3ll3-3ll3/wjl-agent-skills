from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from .paths import ipc_identity_lock_path, ipc_identity_path
from .session_lock import FileLease

IDENTITY_VERSION = 1


@dataclass(frozen=True, slots=True)
class IPCIdentity:
    instance_id: str
    auth_secret: bytes

    @property
    def authkey(self) -> bytes:
        return self.auth_secret


def _decode(payload: dict) -> IPCIdentity:
    if int(payload.get("version", 0)) != IDENTITY_VERSION:
        raise ValueError("Unsupported IPC identity version")
    instance_id = str(payload["instance_id"])
    if not instance_id or len(instance_id) > 64:
        raise ValueError("Invalid IPC instance id")
    secret = base64.urlsafe_b64decode(str(payload["auth_secret_b64"]).encode("ascii"))
    if len(secret) < 32:
        raise ValueError("IPC auth secret is too short")
    return IPCIdentity(instance_id=instance_id, auth_secret=secret)


def _read(path: Path) -> IPCIdentity | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return None
    if not isinstance(payload, dict):
        raise ValueError("IPC identity file must contain a JSON object")
    return _decode(payload)


def _write_atomic(path: Path, identity: IPCIdentity) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    payload = {
        "version": IDENTITY_VERSION,
        "instance_id": identity.instance_id,
        "auth_secret_b64": base64.urlsafe_b64encode(identity.auth_secret).decode("ascii"),
    }
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def load_or_create_identity(path: Path | None = None) -> IPCIdentity:
    target = Path(path or ipc_identity_path())
    lease = FileLease(ipc_identity_lock_path(), busy_message="IPC identity 正在被另一个进程初始化。")
    lease.acquire(timeout=5.0)
    try:
        existing = _read(target)
        if existing is not None:
            return existing
        identity = IPCIdentity(instance_id=uuid.uuid4().hex[:24], auth_secret=secrets.token_bytes(32))
        _write_atomic(target, identity)
        return identity
    finally:
        lease.release()
