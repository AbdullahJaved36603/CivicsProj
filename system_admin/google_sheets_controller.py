from __future__ import annotations

import copy
import importlib
import os
import re
import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    from .config import (
        ACCOUNTS_SHEET_ID,
        HARDCODED_EDITOR_EMAIL,
        RESOLVED_SERVICE_ACCOUNT_FILE,
        SCOPES,
        WEB_APP_URL,
    )
except ImportError:
    from config import (
        ACCOUNTS_SHEET_ID,
        HARDCODED_EDITOR_EMAIL,
        RESOLVED_SERVICE_ACCOUNT_FILE,
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
        web_app_url: Optional[str] = None,
    ) -> None:
        self.master_spreadsheet_id = master_spreadsheet_id or os.getenv("MASTER_SPREADSHEET_ID", ACCOUNTS_SHEET_ID)
        self.service_account_file = service_account_file or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            RESOLVED_SERVICE_ACCOUNT_FILE,
        )
        self.web_app_url = web_app_url or os.getenv("GOOGLE_APPS_SCRIPT_WEB_APP_URL", WEB_APP_URL)
        self.editor_email = HARDCODED_EDITOR_EMAIL
        self._service: Any = None
        self._sessions_schema_checked = False
        self._ensure_sessions_schema()

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

    def _build_service(self) -> Any:
        if self._service is not None:
            return self._service
        if not self.master_spreadsheet_id:
            raise RuntimeError("MASTER_SPREADSHEET_ID is not configured.")
        if not self.service_account_file:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is not configured.")

        try:
            credentials_module = importlib.import_module("google.oauth2.service_account")
            discovery_module = importlib.import_module("googleapiclient.discovery")
            Credentials = getattr(credentials_module, "Credentials")
            build = getattr(discovery_module, "build")
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            raise RuntimeError("Google API dependencies are missing.") from exc

        credentials = Credentials.from_service_account_file(
            self.service_account_file,
            scopes=ALL_SCOPES,
        )
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service

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

    def generate_next_id(self, prefix: str, sheet_tab: str, column_index: int) -> str:
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
