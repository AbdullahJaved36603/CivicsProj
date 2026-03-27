from __future__ import annotations

import copy
import importlib
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

try:
    from .config import (
        ACCOUNTS_SHEET_ID,
        HARDCODED_EDITOR_EMAIL,
        RESOLVED_SERVICE_ACCOUNT_FILE,
        RESOLVED_SERVICE_ACCOUNT_INFO,
        SCOPES,
        WEB_APP_URL,
    )
except ImportError:
    from config import (
        ACCOUNTS_SHEET_ID,
        HARDCODED_EDITOR_EMAIL,
        RESOLVED_SERVICE_ACCOUNT_FILE,
        RESOLVED_SERVICE_ACCOUNT_INFO,
        SCOPES,
        WEB_APP_URL,
    )

try:
    requests = importlib.import_module("requests")
except Exception:  # pragma: no cover - optional dependency at runtime
    requests = None


ALL_SCOPES: List[str] = list(SCOPES)
_ALL_SHEET_DATA: Dict[str, List[List[str]]] = {}
_CACHE_LOCK = threading.RLock()
SESSIONS_TAB_NAME = "Sessions"
SESSIONS_FOLDER_HEADER = "folder_url"
CLASSES_TAB_NAME = "classes"
CLASSES_INCHARGE_HEADER = "class_incharge_teacher_id"
CLASSES_SESSION_HEADER = "session_id"
SUBJECTS_TAB_NAME = "subjects"
SUBJECTS_HEADERS = ["subject_id", "class_id", "subject_name", "session_id"]
EXAM_SESSIONS_TAB_NAME = "exam_sessions"
EXAM_SESSIONS_HEADERS = ["exam_session_id", "session_id", "month"]
SCHOOLS_TAB_NAME = "Schools"
SCHOOLS_PRINCIPAL_HEADER = "principal_id"
TEACHERS_TAB_NAME = "teachers"
TEACHERS_HEADERS = ["teacher_id", "teacher_name", "school_id", "session_id"]
TEACHER_SCHOOLS_TAB_NAME = "Teacher_Schools"
STUDENTS_TAB_NAME = "Students"
STUDENTS_HEADERS = ["student_id", "student_name", "gender", "parent_name", "class_id", "school_id"]
PROXY_ENV_KEYS = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
)

logger = logging.getLogger(__name__)


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _load_external_function(function_name: str) -> Optional[Callable[..., Any]]:
    """Find existing provisioning helpers if they are already available in the project."""
    module_candidates = [
        "google_apps_script_api",
        "google_apps_script_client",
        "school_setup_api",
        "sheet_provisioning",
    ]
    for module_name in module_candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        candidate = getattr(module, function_name, None)
        if callable(candidate):
            return candidate
    return None


_EXTERNAL_CREATE_FOLDER = _load_external_function("create_folder")
_EXTERNAL_CREATE_SHEET = _load_external_function("create_sheet")
_EXTERNAL_CREATE_CLASS_TAB = _load_external_function("create_class_tab")
_EXTERNAL_DELETE_FOLDER = _load_external_function("delete_folder")


class GoogleSheetsController:
    """Centralized database and provisioning controller for Google Sheets-backed storage."""

    def __init__(
        self,
        master_spreadsheet_id: Optional[str] = None,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        web_app_url: Optional[str] = None,
    ) -> None:
        self.master_spreadsheet_id = master_spreadsheet_id or os.getenv("MASTER_SPREADSHEET_ID", ACCOUNTS_SHEET_ID)
        self.service_account_file = service_account_file or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            RESOLVED_SERVICE_ACCOUNT_FILE,
        )
        self.service_account_info = service_account_info or RESOLVED_SERVICE_ACCOUNT_INFO
        self.web_app_url = web_app_url or os.getenv("GOOGLE_APPS_SCRIPT_WEB_APP_URL", WEB_APP_URL)
        self.editor_email = HARDCODED_EDITOR_EMAIL
        self._service: Any = None
        self._sessions_schema_checked = False
        self._classes_schema_checked = False
        self._subjects_schema_checked = False
        self._exam_sessions_checked = False
        self._schools_schema_checked = False
        self._teachers_schema_checked = False
        self._students_schema_checked = False
        self._run_startup_migrations()

    @staticmethod
    def _is_wrong_version_ssl_error(exc: Exception) -> bool:
        text = str(exc).strip().lower()
        return "ssl" in text and "wrong version number" in text

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        text = str(exc).strip().lower()
        return "timed out" in text or "timeout" in text

    def _clear_proxy_environment(self) -> Dict[str, str]:
        removed: Dict[str, str] = {}
        for key in PROXY_ENV_KEYS:
            value = os.environ.pop(key, None)
            if value is not None:
                removed[key] = value
        return removed

    def _run_with_ssl_proxy_fallback(self, action: Callable[[], Any]) -> Any:
        max_attempts = 3
        ssl_fallback_used = False
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return action()
            except Exception as exc:
                last_error = exc

                if self._is_wrong_version_ssl_error(exc) and not ssl_fallback_used:
                    removed = self._clear_proxy_environment()
                    self._service = None
                    ssl_fallback_used = True
                    if removed:
                        logger.warning(
                            "Detected SSL wrong version error; retrying Google Sheets call without proxy env vars: %s",
                            ", ".join(sorted(removed.keys())),
                        )
                    else:
                        logger.warning(
                            "Detected SSL wrong version error; retrying Google Sheets call with rebuilt service.",
                        )
                    continue

                if self._is_timeout_error(exc) and attempt < max_attempts:
                    self._service = None
                    delay_seconds = min(6.0, 1.5 * (2 ** (attempt - 1)))
                    logger.warning(
                        "Google Sheets call timed out on attempt %s/%s; retrying in %.1f seconds.",
                        attempt,
                        max_attempts,
                        delay_seconds,
                    )
                    time.sleep(delay_seconds)
                    continue

                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Google Sheets call failed unexpectedly.")

    def _run_startup_migrations(self) -> None:
        self._ensure_sessions_schema()
        self._ensure_classes_schema()
        self._ensure_subjects_schema()
        self._ensure_exam_sessions_sheet()
        self._ensure_schools_schema()
        self._ensure_teachers_schema()
        self._ensure_students_schema_for_all_schools()

    def _replace_master_tab_values(self, tab_name: str, values: List[List[str]]) -> Dict[str, Any]:
        service = self._build_service()
        service.spreadsheets().values().clear(
            spreadsheetId=self.master_spreadsheet_id,
            range=f"{tab_name}!A:ZZ",
            body={},
        ).execute()
        response = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.master_spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )
        self._refresh_cache(tab_name)
        return response

    def _ensure_schools_schema(self) -> None:
        if self._schools_schema_checked:
            return
        try:
            rows = self.read_tab(SCHOOLS_TAB_NAME, force_refresh=True)
            if not rows:
                self._schools_schema_checked = True
                return

            header = rows[0]
            normalized_header = [str(value).strip().lower() for value in header]
            if len(header) == 4 and SCHOOLS_PRINCIPAL_HEADER not in normalized_header:
                self.update_row(SCHOOLS_TAB_NAME, 1, list(header) + [SCHOOLS_PRINCIPAL_HEADER])
            elif len(header) >= 5 and SCHOOLS_PRINCIPAL_HEADER not in normalized_header:
                migrated_header = list(header)
                migrated_header[4] = SCHOOLS_PRINCIPAL_HEADER
                self.update_row(SCHOOLS_TAB_NAME, 1, migrated_header)

            self._schools_schema_checked = True
        except Exception:
            return

    def _ensure_teachers_schema(self) -> None:
        if self._teachers_schema_checked:
            return

        try:
            if not self._tab_exists(self.master_spreadsheet_id, TEACHERS_TAB_NAME):
                self._create_tab(self.master_spreadsheet_id, TEACHERS_TAB_NAME)
                self.append_row(TEACHERS_TAB_NAME, TEACHERS_HEADERS)

            teachers_rows = self.read_tab(TEACHERS_TAB_NAME, force_refresh=True)
            if not teachers_rows:
                teachers_rows = [TEACHERS_HEADERS]

            expected_header = self._normalized_header_values(TEACHERS_HEADERS)
            header = teachers_rows[0]
            normalized_header = self._normalized_header_values(header)

            schools_rows = self.read_tab(SCHOOLS_TAB_NAME)
            school_session_by_id: Dict[str, str] = {}
            for school_row in schools_rows[1:]:
                school_id = school_row[0].strip() if len(school_row) > 0 else ""
                session_id = school_row[2].strip() if len(school_row) > 2 else ""
                if school_id:
                    school_session_by_id[school_id] = session_id

            accounts_rows = self.read_tab("Accounts")
            teacher_name_by_id: Dict[str, str] = {
                row[0].strip(): row[1].strip()
                for row in accounts_rows[1:]
                if len(row) > 1 and row[0].strip()
            }

            migrated_rows: List[List[str]] = [TEACHERS_HEADERS]
            seen_keys: Set[str] = set()

            if normalized_header == expected_header:
                source_rows = teachers_rows[1:]
                teacher_id_index = 0
                teacher_name_index = 1
                school_id_index = 2
                session_id_index = 3
            else:
                source_rows = teachers_rows[1:]
                teacher_id_index = self._header_index(header, ["teacher_id", "teacher"])
                teacher_name_index = self._header_index(header, ["teacher_name", "teacher", "name"])
                school_id_index = self._header_index(header, ["school_id", "school"])
                session_id_index = self._header_index(header, ["session_id", "session"])

            for row in source_rows:
                teacher_id = row[teacher_id_index].strip() if isinstance(teacher_id_index, int) and teacher_id_index < len(row) else ""
                teacher_name = (
                    row[teacher_name_index].strip()
                    if isinstance(teacher_name_index, int) and teacher_name_index < len(row)
                    else ""
                )
                school_id = row[school_id_index].strip() if isinstance(school_id_index, int) and school_id_index < len(row) else ""
                session_id = row[session_id_index].strip() if isinstance(session_id_index, int) and session_id_index < len(row) else ""
                if not teacher_id or not school_id:
                    continue
                resolved_session_id = session_id or school_session_by_id.get(school_id, "")
                if not resolved_session_id:
                    continue
                key = f"{teacher_id}|{school_id}|{resolved_session_id}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                resolved_teacher_name = teacher_name or teacher_name_by_id.get(teacher_id, "")
                migrated_rows.append([teacher_id, resolved_teacher_name, school_id, resolved_session_id])

            if self._tab_exists(self.master_spreadsheet_id, TEACHER_SCHOOLS_TAB_NAME):
                teacher_school_rows = self.read_tab(TEACHER_SCHOOLS_TAB_NAME, force_refresh=True)
                ts_header = teacher_school_rows[0] if teacher_school_rows else []
                ts_teacher_id_index = self._header_index(ts_header, ["teacher_id", "teacher"])
                ts_school_id_index = self._header_index(ts_header, ["school_id", "school"])
                ts_session_id_index = self._header_index(ts_header, ["session_id", "session"])

                for row in teacher_school_rows[1:]:
                    teacher_id = (
                        row[ts_teacher_id_index].strip()
                        if isinstance(ts_teacher_id_index, int) and ts_teacher_id_index < len(row)
                        else ""
                    )
                    school_id = (
                        row[ts_school_id_index].strip()
                        if isinstance(ts_school_id_index, int) and ts_school_id_index < len(row)
                        else ""
                    )
                    session_id = (
                        row[ts_session_id_index].strip()
                        if isinstance(ts_session_id_index, int) and ts_session_id_index < len(row)
                        else ""
                    )
                    if not teacher_id or not school_id or not session_id:
                        continue
                    key = f"{teacher_id}|{school_id}|{session_id}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    migrated_rows.append([teacher_id, teacher_name_by_id.get(teacher_id, ""), school_id, session_id])

            should_replace = normalized_header != expected_header
            if not should_replace:
                existing_count = max(0, len(teachers_rows) - 1)
                migrated_count = max(0, len(migrated_rows) - 1)
                should_replace = existing_count != migrated_count

            if should_replace:
                self._replace_master_tab_values(TEACHERS_TAB_NAME, migrated_rows)

            self._teachers_schema_checked = True
        except Exception:
            return

    def _ensure_sessions_schema(self) -> None:
        if self._sessions_schema_checked:
            return
        try:
            rows = self.read_tab(SESSIONS_TAB_NAME, force_refresh=True)
            if not rows:
                self._sessions_schema_checked = True
                return

            header = rows[0]
            normalized_header = [str(value).strip().lower() for value in header]
            if len(header) == 3 and SESSIONS_FOLDER_HEADER not in normalized_header:
                migrated_header = list(header) + [SESSIONS_FOLDER_HEADER]
                self.update_row(SESSIONS_TAB_NAME, 1, migrated_header)
            elif len(header) >= 4 and SESSIONS_FOLDER_HEADER not in normalized_header:
                migrated_header = list(header)
                if len(migrated_header) > 3:
                    migrated_header[3] = SESSIONS_FOLDER_HEADER
                    self.update_row(SESSIONS_TAB_NAME, 1, migrated_header)
            self._sessions_schema_checked = True
        except Exception:
            # Migration should never prevent startup or read operations.
            return

    def _ensure_classes_schema(self) -> None:
        if self._classes_schema_checked:
            return
        try:
            rows = self.read_tab(CLASSES_TAB_NAME, force_refresh=True)
            if not rows:
                self._classes_schema_checked = True
                return

            header = rows[0]
            normalized_header = [str(value).strip().lower() for value in header]
            if len(header) == 4 and CLASSES_INCHARGE_HEADER not in normalized_header:
                migrated_header = list(header) + [CLASSES_INCHARGE_HEADER]
                self.update_row(CLASSES_TAB_NAME, 1, migrated_header)
                header = migrated_header
                normalized_header = [str(value).strip().lower() for value in header]
            elif len(header) >= 5 and CLASSES_INCHARGE_HEADER not in normalized_header:
                migrated_header = list(header)
                migrated_header[4] = CLASSES_INCHARGE_HEADER
                self.update_row(CLASSES_TAB_NAME, 1, migrated_header)
                header = migrated_header
                normalized_header = [str(value).strip().lower() for value in header]

            if len(header) == 5 and CLASSES_SESSION_HEADER not in normalized_header:
                migrated_header = list(header) + [CLASSES_SESSION_HEADER]
                self.update_row(CLASSES_TAB_NAME, 1, migrated_header)
            elif len(header) >= 6 and CLASSES_SESSION_HEADER not in normalized_header:
                migrated_header = list(header)
                migrated_header[5] = CLASSES_SESSION_HEADER
                self.update_row(CLASSES_TAB_NAME, 1, migrated_header)

            self._warn_duplicate_classes(rows)

            self._classes_schema_checked = True
        except Exception:
            return

    def _ensure_subjects_schema(self) -> None:
        if self._subjects_schema_checked:
            return
        try:
            if not self._tab_exists(self.master_spreadsheet_id, SUBJECTS_TAB_NAME):
                self._create_tab(self.master_spreadsheet_id, SUBJECTS_TAB_NAME)

            rows = self.read_tab(SUBJECTS_TAB_NAME, force_refresh=True)
            if not rows:
                self.append_row(SUBJECTS_TAB_NAME, SUBJECTS_HEADERS)
                self._subjects_schema_checked = True
                return

            header = rows[0]
            normalized_header = [str(value).strip().lower() for value in header]
            expected_normalized = [value.lower() for value in SUBJECTS_HEADERS]
            if normalized_header != expected_normalized:
                if len(header) == 3 and "session_id" not in normalized_header:
                    migrated_header = list(header) + ["session_id"]
                    self.update_row(SUBJECTS_TAB_NAME, 1, migrated_header)
                else:
                    migrated_header = list(header)
                    if len(migrated_header) < 4:
                        migrated_header.extend([""] * (4 - len(migrated_header)))
                    migrated_header[0] = "subject_id"
                    migrated_header[1] = "class_id"
                    migrated_header[2] = "subject_name"
                    migrated_header[3] = "session_id"
                    self.update_row(SUBJECTS_TAB_NAME, 1, migrated_header)

            self._subjects_schema_checked = True
        except Exception:
            return

    def _warn_duplicate_classes(self, rows: List[List[str]]) -> None:
        seen: Dict[str, str] = {}
        duplicates: List[str] = []
        for row in rows[1:]:
            school_id = row[1].strip() if len(row) > 1 else ""
            class_name = row[2].strip().lower() if len(row) > 2 else ""
            class_section = row[3].strip().lower() if len(row) > 3 else ""
            class_id = row[0].strip() if len(row) > 0 else ""
            if not school_id or not class_name or not class_section:
                continue
            key = f"{school_id}|{class_name}|{class_section}"
            if key in seen:
                duplicates.append(f"{seen[key]} and {class_id}")
            else:
                seen[key] = class_id
        if duplicates:
            logger.warning("Duplicate classes detected during migration: %s", ", ".join(duplicates))

    def _ensure_exam_sessions_sheet(self) -> None:
        if self._exam_sessions_checked:
            return
        try:
            if not self._tab_exists(self.master_spreadsheet_id, EXAM_SESSIONS_TAB_NAME):
                self._create_tab(self.master_spreadsheet_id, EXAM_SESSIONS_TAB_NAME)
            rows = self.read_tab(EXAM_SESSIONS_TAB_NAME, force_refresh=True)
            if not rows:
                self.append_row(EXAM_SESSIONS_TAB_NAME, EXAM_SESSIONS_HEADERS)
            else:
                header = rows[0]
                normalized_header = [str(value).strip().lower() for value in header]
                expected_normalized = [value.lower() for value in EXAM_SESSIONS_HEADERS]
                if normalized_header != expected_normalized:
                    self.update_row(EXAM_SESSIONS_TAB_NAME, 1, EXAM_SESSIONS_HEADERS)
            self._exam_sessions_checked = True
        except Exception:
            return

    @staticmethod
    def _normalized_header_values(values: List[str]) -> List[str]:
        return [str(value).strip().lower().replace(" ", "_") for value in values]

    def _header_index(self, headers: List[str], aliases: List[str]) -> Optional[int]:
        normalized_headers = self._normalized_header_values(headers)
        normalized_aliases = {str(item).strip().lower().replace(" ", "_") for item in aliases}
        for index, header in enumerate(normalized_headers):
            if header in normalized_aliases:
                return index
        return None

    def _ensure_students_schema_for_all_schools(self) -> None:
        if self._students_schema_checked:
            return
        try:
            school_rows = self.read_tab(SCHOOLS_TAB_NAME)
            for row in school_rows[1:]:
                school_id = row[0].strip() if len(row) > 0 else ""
                school_sheet_url = row[3].strip() if len(row) > 3 else ""
                school_sheet_id = self.get_school_sheet_id_from_url(school_sheet_url)
                if not school_sheet_id:
                    continue
                self._ensure_students_schema_for_school(school_sheet_id, school_id)
            self._students_schema_checked = True
        except Exception:
            return

    def _ensure_students_schema_for_school(self, spreadsheet_id: str, school_id: str) -> None:
        try:
            if not self._tab_exists(spreadsheet_id, STUDENTS_TAB_NAME):
                self._create_tab(spreadsheet_id, STUDENTS_TAB_NAME)
                self.append_row_to_spreadsheet(spreadsheet_id, STUDENTS_TAB_NAME, STUDENTS_HEADERS)
                return

            rows = self.read_tab_from_spreadsheet(spreadsheet_id, STUDENTS_TAB_NAME)
            if not rows:
                self.append_row_to_spreadsheet(spreadsheet_id, STUDENTS_TAB_NAME, STUDENTS_HEADERS)
                return

            header = rows[0]
            normalized_header = self._normalized_header_values(header)
            expected_header = self._normalized_header_values(STUDENTS_HEADERS)

            if normalized_header != expected_header:
                student_id_index = self._header_index(header, ["student_id"])
                student_name_index = self._header_index(header, ["student_name"])
                gender_index = self._header_index(header, ["gender", "sex"])
                parent_name_index = self._header_index(header, ["parent_name", "guardian_name"])
                class_id_index = self._header_index(header, ["class_id"])
                school_id_index = self._header_index(header, ["school_id"])

                migrated_rows: List[List[str]] = [STUDENTS_HEADERS]
                for row in rows[1:]:
                    student_id = row[student_id_index] if student_id_index is not None and student_id_index < len(row) else ""
                    student_name = row[student_name_index] if student_name_index is not None and student_name_index < len(row) else ""
                    gender = row[gender_index] if gender_index is not None and gender_index < len(row) else "Unknown"
                    parent_name = row[parent_name_index] if parent_name_index is not None and parent_name_index < len(row) else ""
                    class_id = row[class_id_index] if class_id_index is not None and class_id_index < len(row) else ""
                    row_school_id = row[school_id_index] if school_id_index is not None and school_id_index < len(row) else ""
                    normalized_gender = str(gender).strip() or "Unknown"
                    if normalized_gender.lower() == "m":
                        normalized_gender = "Male"
                    elif normalized_gender.lower() == "f":
                        normalized_gender = "Female"
                    migrated_rows.append(
                        [
                            student_id,
                            student_name,
                            normalized_gender,
                            parent_name,
                            class_id,
                            row_school_id or school_id,
                        ]
                    )

                self.replace_tab_values_in_spreadsheet(spreadsheet_id, STUDENTS_TAB_NAME, migrated_rows)
                rows = migrated_rows

            self._warn_duplicate_students(rows, school_id)
        except Exception:
            return

    def _warn_duplicate_students(self, rows: List[List[str]], school_id: str) -> None:
        if not rows:
            return

        header = rows[0]
        student_name_index = self._header_index(header, ["student_name"])
        parent_name_index = self._header_index(header, ["parent_name", "guardian_name"])
        class_id_index = self._header_index(header, ["class_id"])
        if student_name_index is None or class_id_index is None:
            return

        seen: Set[str] = set()
        duplicates: List[str] = []
        for row in rows[1:]:
            class_id = row[class_id_index].strip().lower() if class_id_index < len(row) else ""
            student_name = row[student_name_index].strip().lower() if student_name_index < len(row) else ""
            parent_name = row[parent_name_index].strip().lower() if parent_name_index is not None and parent_name_index < len(row) else ""
            if not class_id or not student_name:
                continue
            key = f"{class_id}|{student_name}|{parent_name}"
            if key in seen:
                duplicates.append(key)
            else:
                seen.add(key)

        if duplicates:
            logger.warning(
                "Duplicate students detected in school %s during migration; historical rows retained. Keys: %s",
                school_id,
                ", ".join(duplicates),
            )

    def _build_service(self) -> Any:
        if self._service is not None:
            return self._service
        if not self.master_spreadsheet_id:
            raise RuntimeError("MASTER_SPREADSHEET_ID is not configured.")

        try:
            credentials_module = importlib.import_module("google.oauth2.service_account")
            discovery_module = importlib.import_module("googleapiclient.discovery")
            Credentials = getattr(credentials_module, "Credentials")
            build = getattr(discovery_module, "build")
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            raise RuntimeError("Google API dependencies are missing.") from exc

        credentials = None
        if isinstance(self.service_account_info, dict) and self.service_account_info:
            credentials = Credentials.from_service_account_info(
                self.service_account_info,
                scopes=ALL_SCOPES,
            )
        elif self.service_account_file:
            credentials = Credentials.from_service_account_file(
                self.service_account_file,
                scopes=ALL_SCOPES,
            )
        else:
            raise RuntimeError(
                "Google credentials are not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SERVICE_ACCOUNT_JSON, or Streamlit [gcp_service_account] secrets."
            )

        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service

    def _tab_exists(self, spreadsheet_id: str, tab_name: str) -> bool:
        service = self._build_service()
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = metadata.get("sheets", [])
        for sheet in sheets:
            properties = sheet.get("properties", {})
            if properties.get("title") == tab_name:
                return True
        return False

    def _create_tab(self, spreadsheet_id: str, tab_name: str) -> Dict[str, Any]:
        service = self._build_service()
        body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
        return service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

    def _refresh_cache(self, tab_name: str) -> None:
        self.read_tab(tab_name, force_refresh=True)

    def refresh_all_sheets_cache(self) -> Dict[str, Any]:
        try:
            with _CACHE_LOCK:
                _ALL_SHEET_DATA.clear()

            service = self._build_service()
            metadata = service.spreadsheets().get(spreadsheetId=self.master_spreadsheet_id).execute()
            sheets = metadata.get("sheets", [])
            refreshed_tabs: List[str] = []

            for sheet in sheets:
                properties = sheet.get("properties", {})
                title = properties.get("title")
                if not title:
                    continue
                self.read_tab(str(title), force_refresh=True)
                refreshed_tabs.append(str(title))

            return _response(True, "All sheets cache refreshed.", {"tabs": refreshed_tabs})
        except Exception as exc:
            return _response(False, f"Failed to refresh cache: {exc}")

    def read_tab(self, tab_name: str, force_refresh: bool = False) -> List[List[str]]:
        with _CACHE_LOCK:
            if not force_refresh and tab_name in _ALL_SHEET_DATA:
                return copy.deepcopy(_ALL_SHEET_DATA[tab_name])

        service = self._build_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self.master_spreadsheet_id, range=f"{tab_name}!A:ZZ")
            .execute()
        )
        values: List[List[str]] = result.get("values", [])

        with _CACHE_LOCK:
            _ALL_SHEET_DATA[tab_name] = values
        return copy.deepcopy(values)

    def read_tab_from_spreadsheet(self, spreadsheet_id: str, tab_name: str) -> List[List[str]]:
        service = self._build_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{tab_name}!A:ZZ")
            .execute()
        )
        return result.get("values", [])

    def append_row_to_spreadsheet(self, spreadsheet_id: str, tab_name: str, row: List[str]) -> Dict[str, Any]:
        service = self._build_service()
        return (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A:ZZ",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute()
        )

    def update_row_in_spreadsheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        row_index: int,
        row: List[str],
    ) -> Dict[str, Any]:
        if row_index < 1:
            raise ValueError("row_index must be 1-based and greater than zero.")
        service = self._build_service()
        return (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A{row_index}:ZZ{row_index}",
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            )
            .execute()
        )

    def replace_tab_values_in_spreadsheet(
        self,
        spreadsheet_id: str,
        tab_name: str,
        values: List[List[str]],
    ) -> Dict[str, Any]:
        service = self._build_service()
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{tab_name}!A:ZZ",
            body={},
        ).execute()
        return (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )

    def ensure_tab_with_headers(self, spreadsheet_id: str, tab_name: str, headers: List[str]) -> Dict[str, Any]:
        def ensure_schema() -> None:
            if not self._tab_exists(spreadsheet_id, tab_name):
                self._create_tab(spreadsheet_id, tab_name)

            rows = self.read_tab_from_spreadsheet(spreadsheet_id, tab_name)
            if not rows:
                self.append_row_to_spreadsheet(spreadsheet_id, tab_name, headers)
            else:
                current_header = rows[0]
                if self._normalized_header_values(current_header) != self._normalized_header_values(headers):
                    self.update_row_in_spreadsheet(spreadsheet_id, tab_name, 1, headers)

        try:
            self._run_with_ssl_proxy_fallback(ensure_schema)

            return _response(True, "Tab schema ensured successfully.", {"tab_name": tab_name})
        except Exception as exc:
            return _response(False, f"Failed to ensure tab schema: {exc}")

    def append_row(self, tab_name: str, row: List[str]) -> Dict[str, Any]:
        service = self._build_service()
        response = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.master_spreadsheet_id,
                range=f"{tab_name}!A:ZZ",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute()
        )
        self._refresh_cache(tab_name)
        return response

    def append_rows(self, tab_name: str, rows: List[List[str]]) -> Dict[str, Any]:
        if not rows:
            return _response(True, "No rows to append.", {"updated_rows": 0})

        service = self._build_service()
        response = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.master_spreadsheet_id,
                range=f"{tab_name}!A:ZZ",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            )
            .execute()
        )
        self._refresh_cache(tab_name)
        return response

    def update_row(self, tab_name: str, row_index: int, row: List[str]) -> Dict[str, Any]:
        if row_index < 1:
            raise ValueError("row_index must be 1-based and greater than zero.")
        service = self._build_service()
        response = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.master_spreadsheet_id,
                range=f"{tab_name}!A{row_index}:ZZ{row_index}",
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            )
            .execute()
        )
        self._refresh_cache(tab_name)
        return response

    def delete_row(self, tab_name: str, row_index: int) -> Dict[str, Any]:
        if row_index < 1:
            raise ValueError("row_index must be 1-based and greater than zero.")
        service = self._build_service()
        tab_id = self._get_sheet_id(tab_name)
        request_body = {
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": tab_id,
                            "dimension": "ROWS",
                            "startIndex": row_index - 1,
                            "endIndex": row_index,
                        }
                    }
                }
            ]
        }
        response = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=self.master_spreadsheet_id, body=request_body)
            .execute()
        )
        self._refresh_cache(tab_name)
        return response

    def _get_sheet_id(self, tab_name: str) -> int:
        service = self._build_service()
        metadata = service.spreadsheets().get(spreadsheetId=self.master_spreadsheet_id).execute()
        sheets = metadata.get("sheets", [])
        for sheet in sheets:
            properties = sheet.get("properties", {})
            if properties.get("title") == tab_name:
                sheet_id = properties.get("sheetId")
                if isinstance(sheet_id, int):
                    return sheet_id
        raise ValueError(f"Tab '{tab_name}' was not found in master spreadsheet.")

    def generate_next_id(
        self,
        prefix: str,
        sheet_tab: str,
        column_index: int,
        spreadsheet_id: Optional[str] = None,
    ) -> str:
        if spreadsheet_id:
            rows = self.read_tab_from_spreadsheet(spreadsheet_id, sheet_tab)
        else:
            rows = self.read_tab(sheet_tab)
        if not rows or len(rows) == 1:
            return f"{prefix}001"

        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
        max_number = 0
        max_width = 3

        for row in rows[1:]:
            if column_index >= len(row):
                continue
            value = row[column_index].strip()
            match = pattern.match(value)
            if not match:
                continue
            numeric = match.group(1)
            max_width = max(max_width, len(numeric))
            max_number = max(max_number, int(numeric))

        next_number = max_number + 1
        return f"{prefix}{next_number:0{max_width}d}"

    @staticmethod
    def get_school_sheet_id_from_url(url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)

        query = parse_qs(urlparse(url).query)
        if "id" in query and query["id"]:
            return query["id"][0]
        return None

    @staticmethod
    def get_folder_id_from_url(url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"/folders/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)

        query = parse_qs(urlparse(url).query)
        if "id" in query and query["id"]:
            return query["id"][0]
        return None

    def _normalize_external_result(
        self,
        action_name: str,
        raw_result: Any,
        success_message: str,
    ) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", True))
            message = str(raw_result.get("message", success_message if success else f"{action_name} failed."))
            data = raw_result.get("data")
            if data is None:
                data = {k: v for k, v in raw_result.items() if k not in {"success", "message"}}
            return _response(success, message, data if isinstance(data, dict) else {"result": data})
        return _response(True, success_message, {"result": raw_result})

    def resolve_sheet_editor_email(self, editor_email: Optional[str] = None) -> str:
        return HARDCODED_EDITOR_EMAIL

    def _post_webapp(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.web_app_url:
            return None
        if requests is None:
            return None

        try:
            response = requests.post(
                self.web_app_url,
                json=payload,
                timeout=25,
            )
            response.raise_for_status()
            body = response.json()
            if isinstance(body, dict):
                return body
            return None
        except Exception:
            return None

    def create_folder(self, folder_name: str) -> Dict[str, Any]:
        resolved_editor = self.resolve_sheet_editor_email()
        if _EXTERNAL_CREATE_FOLDER is not None:
            try:
                try:
                    result = _EXTERNAL_CREATE_FOLDER(folder_name, editor_email=resolved_editor)
                except TypeError:
                    result = _EXTERNAL_CREATE_FOLDER(folder_name)
                return self._normalize_external_result("create_folder", result, "Folder created successfully.")
            except Exception as exc:
                return _response(False, f"create_folder failed: {exc}")
        payload = {
            "operation": "createFolder",
            "folderName": folder_name,
            "editorEmail": resolved_editor,
        }
        data = self._post_webapp(payload)
        if data and data.get("success"):
            result = data.get("result", {})
            if isinstance(result, dict):
                folder_id = result.get("id") or result.get("folderId")
                if folder_id:
                    folder_url = (
                        result.get("url")
                        or result.get("folderUrl")
                        or f"https://drive.google.com/drive/folders/{folder_id}"
                    )
                    return _response(
                        True,
                        "Folder created successfully.",
                        {"folder_id": str(folder_id), "folder_url": str(folder_url), **result},
                    )
        return _response(False, "create_folder failed.")

    def create_session_folder(self, session_name: str) -> Dict[str, Any]:
        folder_result = self.create_folder(session_name)
        if not folder_result.get("success"):
            return folder_result

        data = folder_result.get("data", {})
        raw_result = data.get("result")
        result_folder_id = raw_result if isinstance(raw_result, str) else ""
        folder_id = str(data.get("folder_id") or data.get("id") or result_folder_id or "").strip()
        folder_url = str(data.get("folder_url") or data.get("url") or "").strip()
        if not folder_url and folder_id:
            folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

        if not folder_url:
            return _response(False, "Session folder created but folder URL was not returned.")

        return _response(
            True,
            "Session folder created successfully.",
            {
                "folder_id": folder_id,
                "folder_url": folder_url,
            },
        )

    def delete_folder(self, folder_id: str) -> Dict[str, Any]:
        if _EXTERNAL_DELETE_FOLDER is not None:
            try:
                result = _EXTERNAL_DELETE_FOLDER(folder_id)
                return self._normalize_external_result("delete_folder", result, "Folder deleted successfully.")
            except Exception as exc:
                return _response(False, f"delete_folder failed: {exc}")

        payload = {
            "operation": "deleteFolder",
            "folderId": folder_id,
        }
        data = self._post_webapp(payload)
        if data and data.get("success"):
            return _response(True, "Folder deleted successfully.", {"folder_id": folder_id})
        return _response(False, "delete_folder failed.")

    def create_sheet(self, sheet_name: str, folder_id: str, editor_email: Optional[str] = None) -> Dict[str, Any]:
        resolved_editor = self.resolve_sheet_editor_email(editor_email)
        if _EXTERNAL_CREATE_SHEET is not None:
            try:
                try:
                    result = _EXTERNAL_CREATE_SHEET(sheet_name, folder_id, editor_email=resolved_editor)
                except TypeError:
                    result = _EXTERNAL_CREATE_SHEET(sheet_name, folder_id)
                return self._normalize_external_result("create_sheet", result, "Sheet created successfully.")
            except Exception as exc:
                return _response(False, f"create_sheet failed: {exc}")
        payload = {
            "operation": "createSheet",
            "sheetName": sheet_name,
            "folderId": folder_id,
            "editorEmail": resolved_editor,
        }
        data = self._post_webapp(payload)
        if data and data.get("success"):
            result = data.get("result", {})
            if isinstance(result, dict):
                sheet_url = (
                    result.get("url")
                    or result.get("sheetUrl")
                    or result.get("spreadsheetUrl")
                )
                if sheet_url:
                    return _response(True, "Sheet created successfully.", {"sheet_url": str(sheet_url), **result})
        return _response(False, "create_sheet failed.")

    def create_class_tab(self, spreadsheet_id: str, tab_name: str) -> Dict[str, Any]:
        if _EXTERNAL_CREATE_CLASS_TAB is not None:
            try:
                result = _EXTERNAL_CREATE_CLASS_TAB(spreadsheet_id, tab_name)
                return self._normalize_external_result("create_class_tab", result, "Class tab created successfully.")
            except Exception as exc:
                return _response(False, f"create_class_tab failed: {exc}")

        body = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
        try:
            service = self._build_service()
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
            return _response(
                True,
                "Class tab created successfully.",
                {"spreadsheet_id": spreadsheet_id, "tab_name": tab_name},
            )
        except Exception as exc:
            return _response(False, f"create_class_tab failed: {exc}")

    def delete_class_tab(self, spreadsheet_id: str, tab_name: str) -> Dict[str, Any]:
        try:
            service = self._build_service()
            metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = metadata.get("sheets", [])

            target_sheet_id: Optional[int] = None
            for sheet in sheets:
                properties = sheet.get("properties", {})
                if properties.get("title") == tab_name:
                    candidate_id = properties.get("sheetId")
                    if isinstance(candidate_id, int):
                        target_sheet_id = candidate_id
                        break

            if target_sheet_id is None:
                return _response(False, "Class tab not found.")

            body = {"requests": [{"deleteSheet": {"sheetId": target_sheet_id}}]}
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
            return _response(
                True,
                "Class tab deleted successfully.",
                {"spreadsheet_id": spreadsheet_id, "tab_name": tab_name},
            )
        except Exception as exc:
            return _response(False, f"delete_class_tab failed: {exc}")

    def clone_spreadsheet_structure(self, source_id: str, destination_id: str) -> Dict[str, Any]:
        try:
            service = self._build_service()

            source_meta = service.spreadsheets().get(spreadsheetId=source_id).execute()
            source_sheets = [
                sheet
                for sheet in source_meta.get("sheets", [])
                if not bool(sheet.get("properties", {}).get("hidden", False))
            ]
            source_titles = [str(sheet.get("properties", {}).get("title", "")).strip() for sheet in source_sheets]
            source_titles = [title for title in source_titles if title]
            if not source_titles:
                return _response(False, "Source spreadsheet does not have visible sheets to clone.")

            source_headers: Dict[str, List[str]] = {}
            for title in source_titles:
                escaped_title = title.replace("'", "''")
                values = (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=source_id, range=f"'{escaped_title}'!1:1")
                    .execute()
                    .get("values", [])
                )
                source_headers[title] = values[0] if values else []

            destination_meta = service.spreadsheets().get(spreadsheetId=destination_id).execute()
            destination_sheets = [
                sheet
                for sheet in destination_meta.get("sheets", [])
                if not bool(sheet.get("properties", {}).get("hidden", False))
            ]
            destination_titles = [str(sheet.get("properties", {}).get("title", "")).strip() for sheet in destination_sheets]

            add_requests: List[Dict[str, Any]] = []
            for title in source_titles:
                if title not in destination_titles:
                    add_requests.append({"addSheet": {"properties": {"title": title}}})

            if add_requests:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=destination_id,
                    body={"requests": add_requests},
                ).execute()

            destination_meta = service.spreadsheets().get(spreadsheetId=destination_id).execute()
            destination_sheets = [
                sheet
                for sheet in destination_meta.get("sheets", [])
                if not bool(sheet.get("properties", {}).get("hidden", False))
            ]

            removable_sheet_ids: List[int] = []
            for sheet in destination_sheets:
                properties = sheet.get("properties", {})
                title = str(properties.get("title", "")).strip()
                sheet_id = properties.get("sheetId")
                if title and title not in source_titles and isinstance(sheet_id, int):
                    removable_sheet_ids.append(sheet_id)

            if removable_sheet_ids and len(destination_sheets) - len(removable_sheet_ids) >= 1:
                delete_requests = [{"deleteSheet": {"sheetId": sheet_id}} for sheet_id in removable_sheet_ids]
                service.spreadsheets().batchUpdate(
                    spreadsheetId=destination_id,
                    body={"requests": delete_requests},
                ).execute()

            for title in source_titles:
                escaped_title = title.replace("'", "''")
                service.spreadsheets().values().clear(
                    spreadsheetId=destination_id,
                    range=f"'{escaped_title}'!A:ZZ",
                    body={},
                ).execute()

                header = source_headers.get(title, [])
                if header:
                    service.spreadsheets().values().update(
                        spreadsheetId=destination_id,
                        range=f"'{escaped_title}'!A1",
                        valueInputOption="RAW",
                        body={"values": [header]},
                    ).execute()

            return _response(
                True,
                "Spreadsheet structure cloned successfully.",
                {
                    "source_id": source_id,
                    "destination_id": destination_id,
                    "tabs": source_titles,
                },
            )
        except Exception as exc:
            return _response(False, f"clone_spreadsheet_structure failed: {exc}")


_CONTROLLER: Optional[GoogleSheetsController] = None


def get_controller() -> GoogleSheetsController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = GoogleSheetsController()
    return _CONTROLLER


def delete_folder(folder_id: str) -> Dict[str, Any]:
    return get_controller().delete_folder(folder_id)


def refresh_all_sheets_cache() -> Dict[str, Any]:
    return get_controller().refresh_all_sheets_cache()


def create_session_folder(session_name: str) -> Dict[str, Any]:
    return get_controller().create_session_folder(session_name)
