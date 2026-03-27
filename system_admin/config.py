from __future__ import annotations

import base64
import binascii
import importlib
import json
import os


# ===========================
# CONFIG
# ===========================
SERVICE_ACCOUNT_FILE = "Service.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyFwe4noMjFg_2l0tGNTRBnJACvefRW6zgTQknTy3MH773SA4pGCUbnjO7nQntAPwyy/exec"
HARDCODED_EDITOR_EMAIL = "test-368@sheettest-490119.iam.gserviceaccount.com"
ACCOUNTS_SHEET_ID = "1dBOT2Jw89w00Mi1cTxbfnQDa4xQ0-DX75DDijITc7jM"

# encryption/decryption.
RELATIONAL_PASSWORD_KEY =b"n2w1HFlx8_WI4SnfMvI4zr4yr8ezyNCx7i53F8NceJY="



_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_LOCAL_PATH = os.path.join(_THIS_DIR, SERVICE_ACCOUNT_FILE)


def _parse_service_account_json(raw_json: str) -> dict | None:
    try:
        payload = json.loads(raw_json)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("client_email"):
        return payload
    return None


def _load_service_account_info_from_env() -> dict | None:
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        parsed = _parse_service_account_json(raw_json)
        if parsed:
            return parsed

    raw_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "").strip()
    if raw_b64:
        try:
            decoded = base64.b64decode(raw_b64).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            decoded = ""
        if decoded:
            parsed = _parse_service_account_json(decoded)
            if parsed:
                return parsed

    return None


def _load_service_account_info_from_streamlit_secrets() -> dict | None:
    try:
        streamlit = importlib.import_module("streamlit")
    except Exception:
        return None

    secrets = getattr(streamlit, "secrets", None)
    if secrets is None:
        return None

    # Preferred Streamlit Cloud format:
    # [gcp_service_account]
    # type = "service_account"
    gcp_section = secrets.get("gcp_service_account") if hasattr(secrets, "get") else None
    if gcp_section:
        try:
            section_dict = dict(gcp_section)
        except Exception:
            section_dict = None
        if isinstance(section_dict, dict) and section_dict.get("client_email"):
            return section_dict

    # Fallback: JSON text stored in Streamlit secrets.
    raw_json = secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON") if hasattr(secrets, "get") else None
    if isinstance(raw_json, str) and raw_json.strip():
        parsed = _parse_service_account_json(raw_json.strip())
        if parsed:
            return parsed

    return None

if os.path.exists(_SERVICE_LOCAL_PATH):
    RESOLVED_SERVICE_ACCOUNT_FILE = _SERVICE_LOCAL_PATH
else:
    RESOLVED_SERVICE_ACCOUNT_FILE = SERVICE_ACCOUNT_FILE


RESOLVED_SERVICE_ACCOUNT_INFO = (
    _load_service_account_info_from_env() or _load_service_account_info_from_streamlit_secrets()
)
