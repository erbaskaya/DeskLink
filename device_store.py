"""Local-only device identity and saved contacts for DeskLink.

The private 256-bit device key is never added to saved contacts or UI logs.
Users remain in control: a saved ID is an address, not unattended access.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from datetime import datetime, timezone

from platform_support import settings_file

IDENTITY_PATTERN = re.compile(r"^[0-9]{9}$")
KEY_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_SAVED = 100


def normalize_id(value: str) -> str:
    return ''.join(c for c in str(value) if '0' <= c <= '9')


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace prevents truncated identity/contact files on power loss.
    fd, filename = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=str(path.parent))
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write('\n')
        os.replace(filename, path)
    finally:
        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass


def get_or_create_identity(path: Path | None = None) -> tuple[str, str]:
    """The ID persists across relaunches; the secret proves ID ownership to relay."""
    path = path or settings_file()
    data = _read(path)
    identity = data.get('device_identity', {})
    if isinstance(identity, dict):
        identifier = identity.get('id')
        key = identity.get('key')
        if isinstance(identifier, str) and IDENTITY_PATTERN.fullmatch(identifier) and isinstance(key, str) and KEY_PATTERN.fullmatch(key):
            return identifier, key
    return rotate_identity(path)


def rotate_identity(path: Path | None = None) -> tuple[str, str]:
    """Used only when the server reports a previously claimed ID."""
    path = path or settings_file()
    data = _read(path)
    identifier = f'{100_000_000 + secrets.randbelow(900_000_000):09d}'
    secret = secrets.token_hex(32)
    data['device_identity'] = {'id': identifier, 'key': secret}
    _write(path, data)
    return identifier, secret


def get_server_url(default_url: str, path: Path | None = None) -> str:
    return str(_read(path or settings_file()).get('server_url', default_url))


def put_server_url(url: str, path: Path | None = None) -> None:
    path = path or settings_file()
    data = _read(path)
    data['server_url'] = url
    _write(path, data)


def contacts(server_url: str, path: Path | None = None) -> list[dict]:
    raw = _read(path or settings_file()).get('saved_devices', [])
    if not isinstance(raw, list):
        return []
    result = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get('id', '')
        if entry.get('server') != server_url or not isinstance(identifier, str) or not IDENTITY_PATTERN.fullmatch(identifier) or identifier in seen:
            continue
        seen.add(identifier)
        result.append({'id': identifier, 'name': str(entry.get('name', '')).strip()[:48] or f'Bilgisayar {identifier}',
                       'server': server_url, 'last_connected': str(entry.get('last_connected', ''))[:40]})
    return result[:MAX_SAVED]


def save_contact(server_url: str, identifier: str, name: str = '', *, connected: bool = False,
                 path: Path | None = None) -> None:
    if not IDENTITY_PATTERN.fullmatch(identifier):
        raise ValueError('Bilgisayar ID 9 haneli olmalı.')
    path = path or settings_file()
    data = _read(path)
    raw = data.get('saved_devices', [])
    if not isinstance(raw, list):
        raw = []
    record = next((x for x in raw if isinstance(x, dict) and x.get('id') == identifier and x.get('server') == server_url), None)
    current_name = record.get('name') if record else ''
    clean_name = name.strip()[:48]
    if not clean_name:
        clean_name = str(current_name or f'Bilgisayar {identifier}')[:48]
    timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds') if connected else str((record or {}).get('last_connected', ''))
    cleaned = [x for x in raw if isinstance(x, dict) and not (x.get('id') == identifier and x.get('server') == server_url)]
    data['saved_devices'] = ([{'id': identifier, 'name': clean_name, 'server': server_url, 'last_connected': timestamp}] + cleaned)[:MAX_SAVED]
    _write(path, data)


def delete_contact(server_url: str, identifier: str, path: Path | None = None) -> None:
    path = path or settings_file()
    data = _read(path)
    raw = data.get('saved_devices', [])
    if not isinstance(raw, list):
        return
    data['saved_devices'] = [x for x in raw if isinstance(x, dict) and not (x.get('id') == identifier and x.get('server') == server_url)]
    _write(path, data)
