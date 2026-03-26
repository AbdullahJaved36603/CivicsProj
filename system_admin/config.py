from __future__ import annotations

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

if os.path.exists(_SERVICE_LOCAL_PATH):
    RESOLVED_SERVICE_ACCOUNT_FILE = _SERVICE_LOCAL_PATH
else:
    RESOLVED_SERVICE_ACCOUNT_FILE = SERVICE_ACCOUNT_FILE
