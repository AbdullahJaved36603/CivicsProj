import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import importlib.util

import requests
from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ===========================
# CONFIG
# ===========================
SERVICE_ACCOUNT_FILE = "Service.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyFwe4noMjFg_2l0tGNTRBnJACvefRW6zgTQknTy3MH773SA4pGCUbnjO7nQntAPwyy/exec"
HARDCODED_EDITOR_EMAIL = "test-368@sheettest-490119.iam.gserviceaccount.com"
ACCOUNTS_SHEET_ID = "1dBOT2Jw89w00Mi1cTxbfnQDa4xQ0-DX75DDijITc7jM"
ENCRYPTION_KEY = b"q8A2dCPN9EcbQ4L0aX4XzRk8wW3VY6MypfSkjHj8m5A="

ACCOUNTS_TAB = "Accounts"
SESSIONS_TAB = "Sessions"
SCHOOLS_TAB = "Schools"
SCHOOL_SHEETS_TAB = "SchoolSheets"

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build("sheets", "v4", credentials=creds)
fernet = Fernet(ENCRYPTION_KEY)

legacy_controller = None
try:
    legacy_path = Path(__file__).resolve().parents[1] / "GoogleSheetController.py"
    if legacy_path.exists():
        spec = importlib.util.spec_from_file_location("legacy_google_sheet_controller", str(legacy_path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            legacy_controller = module
except Exception:
    legacy_controller = None

_ALL_SHEET_DATA: Dict[str, List[List[str]]] = {}


# ===========================
# Utilities
# ===========================
def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_session_name(session_name: str) -> str:
    return session_name.strip().replace("Session_", "")


def session_folder_name(session_name: str) -> str:
    clean = normalize_session_name(session_name)
    return f"Session_{clean}"


def extract_sheet_id(sheet_url: str) -> Optional[str]:
    if not sheet_url:
        return None
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    return match.group(1) if match else None


def get_backend_editor_email() -> str:
    return HARDCODED_EDITOR_EMAIL


def resolve_sheet_editor_email(preferred_email: str = "") -> str:
    return HARDCODED_EDITOR_EMAIL


def encrypt_password(password: str) -> str:
    return fernet.encrypt(password.encode()).decode()


def decrypt_password(enc_password: str) -> str:
    try:
        return fernet.decrypt(enc_password.encode()).decode()
    except InvalidToken:
        return ""


def _post_webapp(payload: Dict) -> Optional[Dict]:
    try:
        response = requests.post(WEB_APP_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"WebApp request failed: {exc}")
        return None


def _tab_name_from_range(range_name: str) -> str:
    tab = (range_name or "").split("!")[0]
    if tab.startswith("'") and tab.endswith("'"):
        tab = tab[1:-1]
    return tab


def refresh_all_sheets_cache() -> Dict[str, List[List[str]]]:
    global _ALL_SHEET_DATA

    try:
        meta = service.spreadsheets().get(spreadsheetId=ACCOUNTS_SHEET_ID).execute()
        sheet_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if not sheet_names:
            _ALL_SHEET_DATA = {}
            return _ALL_SHEET_DATA

        ranges = [f"{tab}!A2:Z" for tab in sheet_names]
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=ACCOUNTS_SHEET_ID,
            ranges=ranges,
        ).execute()

        data: Dict[str, List[List[str]]] = {}
        for value_range in result.get("valueRanges", []):
            range_name = value_range.get("range", "")
            tab_name = _tab_name_from_range(range_name)
            rows = value_range.get("values", [])
            data[tab_name] = [list(row) for row in rows]

        for tab_name in sheet_names:
            data.setdefault(tab_name, [])

        _ALL_SHEET_DATA = data
        return _ALL_SHEET_DATA
    except Exception as exc:
        print(f"Failed loading sheets cache: {exc}")
        if not _ALL_SHEET_DATA:
            _ALL_SHEET_DATA = {}
        return _ALL_SHEET_DATA


def _ensure_cache_loaded() -> None:
    if not _ALL_SHEET_DATA:
        refresh_all_sheets_cache()


# ===========================
# Read/Write Helpers
# ===========================
def get_tab_rows(tab_name: str) -> List[List[str]]:
    _ensure_cache_loaded()
    return _ALL_SHEET_DATA.get(tab_name, [])


def append_row(tab_name: str, row: List[str]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=ACCOUNTS_SHEET_ID,
        range=f"{tab_name}!A:Z",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    _ALL_SHEET_DATA.setdefault(tab_name, []).append(row)


def update_row(tab_name: str, row_index: int, row: List[str]) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=ACCOUNTS_SHEET_ID,
        range=f"{tab_name}!A{row_index + 2}",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()

    rows = _ALL_SHEET_DATA.setdefault(tab_name, [])
    if row_index < len(rows):
        rows[row_index] = row
    elif row_index == len(rows):
        rows.append(row)


# ===========================
# Accounts Operations
# ===========================
def get_accounts() -> List[Dict[str, str]]:
    rows = get_tab_rows(ACCOUNTS_TAB)
    return [
        {
            "username": row[0],
            "encrypted_password": row[1] if len(row) > 1 else "",
            "role": row[2] if len(row) > 2 else "",
            "schools_assigned": row[3] if len(row) > 3 else "",
        }
        for row in rows
        if row
    ]


def get_user(username: str) -> Optional[Dict[str, str]]:
    clean = username.strip()
    if not clean:
        return None

    for account in get_accounts():
        if account.get("username") == clean:
            return account
    return None


def make_user(username: str, password: str, role: str, schools_assigned: str = "") -> bool:
    username = username.strip()
    if not username or not password or not role:
        return False

    encrypted_pass = encrypt_password(password)
    rows = get_tab_rows(ACCOUNTS_TAB)
    for idx, row in enumerate(rows):
        if row and row[0] == username:
            update_row(ACCOUNTS_TAB, idx, [username, encrypted_pass, role, schools_assigned])
            return True

    append_row(ACCOUNTS_TAB, [username, encrypted_pass, role, schools_assigned])
    return True


def validate_user(username: str, password: str) -> Optional[str]:
    rows = get_tab_rows(ACCOUNTS_TAB)
    for row in rows:
        if len(row) >= 3 and row[0] == username and decrypt_password(row[1]) == password:
            return row[2]
    return None


def update_user_schools(username: str, schools: List[str]) -> bool:
    clean_schools = sorted({s.strip() for s in schools if s.strip()})
    rows = get_tab_rows(ACCOUNTS_TAB)
    for idx, row in enumerate(rows):
        if row and row[0] == username:
            encrypted_password = row[1] if len(row) > 1 else ""
            role = row[2] if len(row) > 2 else ""
            update_row(ACCOUNTS_TAB, idx, [username, encrypted_password, role, ",".join(clean_schools)])
            return True
    return False


def list_principals() -> List[str]:
    return [a["username"] for a in get_accounts() if a.get("role") == "principal"]


# ===========================
# Sessions Operations
# ===========================
def list_session_records(active_only: bool = True) -> List[Dict[str, str]]:
    rows = get_tab_rows(SESSIONS_TAB)
    records = []
    for row in rows:
        if not row:
            continue

        normalized_session = normalize_session_name(row[0] if len(row) > 0 else "")
        status = row[3] if len(row) > 3 else "active"
        if active_only and status != "active":
            continue

        records.append(
            {
                "session_name": normalized_session,
                "folder_id": row[1] if len(row) > 1 else "",
                "created_at": row[2] if len(row) > 2 else "",
                "status": status,
            }
        )
    return records


def get_session_folder_id(session_name: str) -> Optional[str]:
    clean = normalize_session_name(session_name)
    for record in list_session_records(active_only=True):
        if record["session_name"] == clean:
            return record["folder_id"]
    return None


def create_session_record(session_name: str, folder_id: str) -> bool:
    clean = normalize_session_name(session_name)
    if get_session_folder_id(clean):
        return False

    append_row(SESSIONS_TAB, [clean, folder_id, now_iso(), "active"])
    return True


def deactivate_session_record(session_name: str) -> bool:
    clean = normalize_session_name(session_name)
    rows = get_tab_rows(SESSIONS_TAB)
    for idx, row in enumerate(rows):
        row_session = normalize_session_name(row[0] if len(row) > 0 else "")
        if row and row_session == clean:
            folder_id = row[1] if len(row) > 1 else ""
            created_at = row[2] if len(row) > 2 else ""
            update_row(SESSIONS_TAB, idx, [clean, folder_id, created_at, "inactive"])
            return True
    return False


# ===========================
# Schools Operations
# ===========================
def list_school_records(active_only: bool = True) -> List[Dict[str, str]]:
    rows = get_tab_rows(SCHOOLS_TAB)
    records = []
    for row in rows:
        if not row:
            continue

        status = row[3] if len(row) > 3 else "active"
        if active_only and status != "active":
            continue

        records.append(
            {
                "school_name": row[0] if len(row) > 0 else "",
                "default_editor_email": row[1] if len(row) > 1 else "",
                "created_at": row[2] if len(row) > 2 else "",
                "status": status,
            }
        )
    return records


def create_school_record(school_name: str, editor_email: str = "") -> bool:
    clean = school_name.strip()
    if not clean:
        return False

    rows = get_tab_rows(SCHOOLS_TAB)
    for idx, row in enumerate(rows):
        if row and row[0] == clean:
            update_row(
                SCHOOLS_TAB,
                idx,
                [clean, editor_email or (row[1] if len(row) > 1 else ""), row[2] if len(row) > 2 else now_iso(), "active"],
            )
            return True

    append_row(SCHOOLS_TAB, [clean, editor_email, now_iso(), "active"])
    return True


def deactivate_school_record(school_name: str) -> bool:
    clean = school_name.strip()
    rows = get_tab_rows(SCHOOLS_TAB)
    for idx, row in enumerate(rows):
        if row and row[0] == clean:
            editor = row[1] if len(row) > 1 else ""
            created_at = row[2] if len(row) > 2 else ""
            update_row(SCHOOLS_TAB, idx, [clean, editor, created_at, "inactive"])
            return True
    return False


# ===========================
# Session/School Mapping
# ===========================
def create_school_sheet_record(
    session_name: str,
    school_name: str,
    folder_id: str,
    sheet_url: str,
    editor_email: str,
) -> bool:
    clean_session = normalize_session_name(session_name)
    clean_school = school_name.strip()
    sheet_id = extract_sheet_id(sheet_url) or ""

    rows = get_tab_rows(SCHOOL_SHEETS_TAB)
    for idx, row in enumerate(rows):
        row_session = row[0] if len(row) > 0 else ""
        row_school = row[1] if len(row) > 1 else ""
        if row_session == clean_session and row_school == clean_school:
            created_at = row[6] if len(row) > 6 else now_iso()
            update_row(
                SCHOOL_SHEETS_TAB,
                idx,
                [clean_session, clean_school, folder_id, sheet_url, sheet_id, editor_email, created_at, "active"],
            )
            return True

    append_row(
        SCHOOL_SHEETS_TAB,
        [clean_session, clean_school, folder_id, sheet_url, sheet_id, editor_email, now_iso(), "active"],
    )
    return True


def deactivate_school_sheet_records(school_name: Optional[str] = None, session_name: Optional[str] = None) -> int:
    rows = get_tab_rows(SCHOOL_SHEETS_TAB)
    changed = 0
    normalized_filter_session = normalize_session_name(session_name) if session_name else None

    for idx, row in enumerate(rows):
        row_session = normalize_session_name(row[0] if len(row) > 0 else "")
        row_school = row[1] if len(row) > 1 else ""
        folder_id = row[2] if len(row) > 2 else ""
        sheet_url = row[3] if len(row) > 3 else ""
        sheet_id = row[4] if len(row) > 4 else ""
        editor = row[5] if len(row) > 5 else ""
        created_at = row[6] if len(row) > 6 else ""

        if school_name and row_school != school_name.strip():
            continue
        if normalized_filter_session and row_session != normalized_filter_session:
            continue

        update_row(
            SCHOOL_SHEETS_TAB,
            idx,
            [row_session, row_school, folder_id, sheet_url, sheet_id, editor, created_at, "inactive"],
        )
        changed += 1

    return changed


def list_school_sheet_records(
    session_name: Optional[str] = None,
    school_name: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, str]]:
    rows = get_tab_rows(SCHOOL_SHEETS_TAB)
    records = []
    normalized_filter_session = normalize_session_name(session_name) if session_name else None

    for row in rows:
        session = normalize_session_name(row[0] if len(row) > 0 else "")
        school = row[1] if len(row) > 1 else ""
        folder_id = row[2] if len(row) > 2 else ""
        sheet_url = row[3] if len(row) > 3 else ""
        sheet_id = row[4] if len(row) > 4 else ""
        editor_email = row[5] if len(row) > 5 else ""
        created_at = row[6] if len(row) > 6 else ""
        status = row[7] if len(row) > 7 else "active"

        if not school:
            continue
        if active_only and status != "active":
            continue
        if normalized_filter_session and session != normalized_filter_session:
            continue
        if school_name and school != school_name.strip():
            continue

        records.append(
            {
                "session_name": session,
                "school_name": school,
                "folder_id": folder_id,
                "sheet_url": sheet_url,
                "sheet_id": sheet_id,
                "editor_email": editor_email,
                "created_at": created_at,
                "status": status,
            }
        )

    return records


def get_school_sheet_record(school_name: str, session_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    records = list_school_sheet_records(session_name=session_name, school_name=school_name, active_only=True)
    if not records:
        return None
    return sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)[0]


def get_school_sheet_id(school_name: str, session_name: Optional[str] = None) -> Optional[str]:
    record = get_school_sheet_record(school_name=school_name, session_name=session_name)
    if not record:
        return None
    if record.get("sheet_id"):
        return record["sheet_id"]
    return extract_sheet_id(record.get("sheet_url", ""))


# ===========================
# Folder / Sheet Creation
# ===========================
def create_folder(folder_name: str) -> Optional[str]:
    if legacy_controller and hasattr(legacy_controller, "create_folder"):
        try:
            folder_id = legacy_controller.create_folder(folder_name)
            if folder_id:
                return folder_id
        except Exception:
            pass

    payload = {"operation": "createFolder", "folderName": folder_name}
    data = _post_webapp(payload)
    if data and data.get("success"):
        return data["result"]["id"]
    return None


def delete_folder(folder_id: str) -> bool:
    payload = {"operation": "deleteFolder", "folderId": folder_id}
    data = _post_webapp(payload)
    return bool(data and data.get("success"))


def create_sheet(sheet_name: str, folder_id: str, editor_email: str = HARDCODED_EDITOR_EMAIL) -> Optional[str]:
    resolved_editor = resolve_sheet_editor_email(editor_email)

    if legacy_controller and hasattr(legacy_controller, "create_sheet"):
        try:
            sheet_url = legacy_controller.create_sheet(sheet_name, folder_id, resolved_editor)
            if sheet_url:
                return sheet_url
        except Exception:
            pass

    payload = {
        "operation": "createSheet",
        "sheetName": sheet_name,
        "folderId": folder_id,
        "editorEmail": resolved_editor,
    }
    data = _post_webapp(payload)
    if data and data.get("success"):
        return data["result"]["url"]
    return None


def create_class_tab(school_sheet_id: str, class_name: str) -> bool:
    body = {"requests": [{"addSheet": {"properties": {"title": class_name}}}]}
    try:
        service.spreadsheets().batchUpdate(spreadsheetId=school_sheet_id, body=body).execute()
        return True
    except Exception:
        return False


refresh_all_sheets_cache()
