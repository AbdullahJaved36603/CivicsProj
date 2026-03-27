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
        error_text = str(exc)
        if "Invalid JWT Signature" in error_text:
            return _response(
                False,
                "Google service account key is invalid or revoked. Replace system_admin/Service.json with a fresh key for the configured service account.",
            )
        return _response(False, f"Authentication failed: {exc}")


def change_user_credentials(
    user_id: str,
    current_username: str,
    current_password: str,
    new_username: str,
    new_password: str,
) -> Dict[str, Any]:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return _response(False, "user_id is required.")

    if not current_username.strip():
        return _response(False, "current_username is required.")
    if not current_password.strip():
        return _response(False, "current_password is required.")
    if not new_password.strip():
        return _response(False, "new_password is required.")

    username_validation = validate_and_normalize_username(new_username)
    if not username_validation.get("success"):
        return _response(False, USERNAME_EMPTY_MESSAGE)
    normalized_new_username = str(username_validation.get("data", {}).get("username", "")).strip()

    auth_response = authenticate(current_username, current_password)
    if not auth_response.get("success"):
        return _response(False, "Current username or password is incorrect.")

    authenticated_user_id = str(auth_response.get("data", {}).get("user_id", "")).strip()
    if authenticated_user_id != normalized_user_id:
        return _response(False, "Current credentials do not match the signed-in user.")

    if _relational_fernet is None:
        return _response(False, "Encryption service is unavailable.")

    encrypt_method = getattr(_relational_fernet, "encrypt", None)
    if not callable(encrypt_method):
        return _response(False, "Encryption service is unavailable.")

    try:
        controller = get_controller()
        rows = controller.read_tab(TAB_ACCOUNTS)

        target_row_index: Optional[int] = None
        target_row: List[str] = []
        for row_index, row in enumerate(rows[1:], start=2):
            row_user_id = row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else ""
            row_username = row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else ""
            if row_user_id != normalized_user_id and row_username.strip().lower() == normalized_new_username.lower():
                return _response(False, "Username already exists")
            if row_user_id == normalized_user_id:
                target_row_index = row_index
                target_row = row

        if target_row_index is None:
            return _response(False, "User does not exist.")

        role = target_row[AccountsColumns.ROLE] if AccountsColumns.ROLE < len(target_row) else ""
        status = target_row[AccountsColumns.STATUS] if AccountsColumns.STATUS < len(target_row) else ""

        encrypted_password = encrypt_method(new_password.strip().encode())
        encrypted_password_str = encrypted_password.decode() if isinstance(encrypted_password, bytes) else str(encrypted_password)

        controller.update_row(
            TAB_ACCOUNTS,
            target_row_index,
            [normalized_user_id, normalized_new_username, encrypted_password_str, role, status],
        )
        return _response(
            True,
            "Credentials updated successfully.",
            {
                "user_id": normalized_user_id,
                "username": normalized_new_username,
            },
        )
    except Exception as exc:
        error_text = str(exc)
        if "Invalid JWT Signature" in error_text:
            return _response(
                False,
                "Google service account key is invalid or revoked. Replace system_admin/Service.json with a fresh key for the configured service account.",
            )
        return _response(False, f"Failed to change credentials: {exc}")
