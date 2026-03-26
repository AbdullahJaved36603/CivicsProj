from __future__ import annotations

import random
import secrets
import string
import importlib
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    from .google_sheets_controller import get_controller
except ImportError:
    from google_sheets_controller import get_controller

try:
    relational_fernet_module = importlib.import_module("relational_fernet")
    _relational_fernet = getattr(relational_fernet_module, "relational_fernet", None)
except Exception:  # pragma: no cover - depends on deployment environment
    _relational_fernet = None


MIN_PASSWORD_LENGTH = 10
UPPERCASE_CHARS = string.ascii_uppercase
LOWERCASE_CHARS = string.ascii_lowercase
NUMBER_CHARS = string.digits
SYMBOL_CHARS = "!@#$%&*"
USERNAME_EMPTY_MESSAGE = "Username cannot be empty"

TAB_ACCOUNTS = "Accounts"


class AccountsColumns:
    USER_ID = 0
    USERNAME = 1
    PASSWORD = 2
    ROLE = 3
    STATUS = 4


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _is_active(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "active"}


def normalize_username(username: str) -> str:
    return username.strip()


def validate_and_normalize_username(username: str) -> Dict[str, Any]:
    normalized_username = normalize_username(username)
    if not normalized_username:
        return _response(False, USERNAME_EMPTY_MESSAGE)
    return _response(True, "Username is valid.", {"username": normalized_username})


def _shuffle_chars(chars: List[str]) -> str:
    random.SystemRandom().shuffle(chars)
    return "".join(chars)


def _is_valid_password(password: str) -> bool:
    return (
        len(password) >= MIN_PASSWORD_LENGTH
        and any(ch in UPPERCASE_CHARS for ch in password)
        and any(ch in LOWERCASE_CHARS for ch in password)
        and any(ch in NUMBER_CHARS for ch in password)
    )


def generate_unique_password(existing_passwords: Iterable[str] | None = None, length: int = 12) -> str:
    """Generate a strong password not present in existing_passwords."""
    existing = set(existing_passwords or [])
    final_length = max(length, MIN_PASSWORD_LENGTH)
    character_pool = UPPERCASE_CHARS + LOWERCASE_CHARS + NUMBER_CHARS + SYMBOL_CHARS

    for _ in range(500):
        candidate_chars = [
            secrets.choice(UPPERCASE_CHARS),
            secrets.choice(LOWERCASE_CHARS),
            secrets.choice(NUMBER_CHARS),
        ]
        while len(candidate_chars) < final_length:
            candidate_chars.append(secrets.choice(character_pool))
        candidate = _shuffle_chars(candidate_chars)
        if candidate not in existing and _is_valid_password(candidate):
            return candidate

    raise RuntimeError("Failed to generate a unique password after multiple attempts.")


def get_existing_plain_passwords(accounts_rows: List[List[str]], password_column_index: int) -> Set[str]:
    """Decrypt encrypted passwords when decryption is available, used for uniqueness checks."""
    passwords: Set[str] = set()
    if _relational_fernet is None:
        return passwords

    decrypt_method = getattr(_relational_fernet, "decrypt", None)
    if not callable(decrypt_method):
        return passwords

    for row in accounts_rows:
        if password_column_index >= len(row):
            continue
        encrypted = row[password_column_index]
        if not encrypted:
            continue
        try:
            decrypted = decrypt_method(encrypted.encode()).decode()
            passwords.add(decrypted)
        except Exception:
            continue
    return passwords


def authenticate(username: str, password: str) -> Dict[str, Any]:
    normalized_username = username.strip().lower()
    normalized_password = password.strip()

    if not normalized_username:
        return _response(False, "username is required.")
    if not normalized_password:
        return _response(False, "password is required.")
    if _relational_fernet is None:
        return _response(False, "Encryption service is unavailable.")

    decrypt_method = getattr(_relational_fernet, "decrypt", None)
    if not callable(decrypt_method):
        return _response(False, "Encryption service is unavailable.")

    try:
        controller = get_controller()
        rows = controller.read_tab(TAB_ACCOUNTS)
        for row in rows[1:]:
            row_username = row[AccountsColumns.USERNAME].strip().lower() if AccountsColumns.USERNAME < len(row) else ""
            if row_username != normalized_username:
                continue

            status = row[AccountsColumns.STATUS] if AccountsColumns.STATUS < len(row) else ""
            if not _is_active(status):
                return _response(False, "Account is not active.")

            encrypted = row[AccountsColumns.PASSWORD] if AccountsColumns.PASSWORD < len(row) else ""
            if not encrypted:
                return _response(False, "Invalid username or password.")

            try:
                plain = decrypt_method(encrypted.encode()).decode()
            except Exception:
                return _response(False, "Invalid username or password.")

            if plain != normalized_password:
                return _response(False, "Invalid username or password.")

            return _response(
                True,
                "Login successful.",
                {
                    "user_id": row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else "",
                    "username": row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else "",
                    "role": row[AccountsColumns.ROLE] if AccountsColumns.ROLE < len(row) else "",
                    "status": status,
                },
            )

        return _response(False, "Invalid username or password.")
    except Exception as exc:
        return _response(False, f"Authentication failed: {exc}")
