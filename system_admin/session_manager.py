from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller


TAB_SESSIONS = "Sessions"
TAB_SCHOOLS = "Schools"


class SessionColumns:
    SESSION_ID = 0
    SESSION_NAME = 1
    IS_ACTIVE = 2
    FOLDER_URL = 3


class SchoolColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1
    SESSION_ID = 2
    SCHOOL_SHEET_URL = 3


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class SessionManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    @staticmethod
    def _is_active(value: str) -> bool:
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "active"}

    def _set_all_sessions_inactive(self) -> None:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row_index, row in enumerate(rows[1:], start=2):
            session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
            session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
            folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
            self.controller.update_row(
                row_index=row_index,
                tab_name=TAB_SESSIONS,
                row=[session_id, session_name, "FALSE", folder_url],
            )

    def _get_active_session(self) -> Optional[Dict[str, str]]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            is_active = row[SessionColumns.IS_ACTIVE] if SessionColumns.IS_ACTIVE < len(row) else ""
            if not self._is_active(is_active):
                continue
            return {
                "session_id": row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else "",
                "session_name": row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else "",
                "folder_url": row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else "",
            }
        return None

    def _session_name_exists(self, session_name: str) -> bool:
        rows = self.controller.read_tab(TAB_SESSIONS)
        target = session_name.lower()
        for row in rows[1:]:
            if SessionColumns.SESSION_NAME < len(row) and row[SessionColumns.SESSION_NAME].lower() == target:
                return True
        return False

    def _copy_previous_session_schools(
        self,
        previous_session_id: str,
        new_session_id: str,
        new_session_folder_id: str,
    ) -> Dict[str, Any]:
        schools_rows = self.controller.read_tab(TAB_SCHOOLS)
        source_schools: List[List[str]] = [
            row
            for row in schools_rows[1:]
            if SchoolColumns.SESSION_ID < len(row) and row[SchoolColumns.SESSION_ID] == previous_session_id
        ]

        copied: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []

        for school_row in source_schools:
            school_name = school_row[SchoolColumns.SCHOOL_NAME] if SchoolColumns.SCHOOL_NAME < len(school_row) else ""
            source_sheet_url = (
                school_row[SchoolColumns.SCHOOL_SHEET_URL] if SchoolColumns.SCHOOL_SHEET_URL < len(school_row) else ""
            )
            source_sheet_id = self.controller.get_school_sheet_id_from_url(source_sheet_url)

            if not school_name:
                failed.append({"school_name": "", "reason": "Missing school_name in source session."})
                continue
            if not source_sheet_id:
                failed.append({"school_name": school_name, "reason": "Missing or invalid source school spreadsheet URL."})
                continue

            create_sheet_result = self.controller.create_sheet(school_name, new_session_folder_id)
            if not create_sheet_result.get("success"):
                failed.append({
                    "school_name": school_name,
                    "reason": create_sheet_result.get("message", "Failed to create school spreadsheet."),
                })
                continue

            sheet_data = create_sheet_result.get("data", {})
            destination_sheet_url = (
                sheet_data.get("school_sheet_url")
                or sheet_data.get("sheet_url")
                or sheet_data.get("spreadsheet_url")
                or sheet_data.get("url")
                or sheet_data.get("result")
            )
            destination_sheet_url = str(destination_sheet_url or "").strip()
            destination_sheet_id = self.controller.get_school_sheet_id_from_url(destination_sheet_url)

            if not destination_sheet_url or not destination_sheet_id:
                failed.append({"school_name": school_name, "reason": "Destination spreadsheet URL is missing or invalid."})
                continue

            clone_result = self.controller.clone_spreadsheet_structure(source_sheet_id, destination_sheet_id)
            if not clone_result.get("success"):
                failed.append({
                    "school_name": school_name,
                    "reason": clone_result.get("message", "Failed to clone spreadsheet structure."),
                })
                continue

            new_school_id = self.controller.generate_next_id("S", TAB_SCHOOLS, SchoolColumns.SCHOOL_ID)
            self.controller.append_row(TAB_SCHOOLS, [new_school_id, school_name, new_session_id, destination_sheet_url])
            copied.append(
                {
                    "source_school_name": school_name,
                    "new_school_id": new_school_id,
                    "new_school_sheet_url": destination_sheet_url,
                }
            )

        return {
            "copied": copied,
            "failed": failed,
            "source_school_count": len(source_schools),
            "copied_count": len(copied),
        }

    def create_session(self, session_name: str, copy_previous: bool = False) -> Dict[str, Any]:
        try:
            normalized_name = session_name.strip()
            if not normalized_name:
                return _response(False, "session_name is required.")
            if self._session_name_exists(normalized_name):
                return _response(False, "Session name already exists.")

            previous_active_session = self._get_active_session()
            session_id = self.controller.generate_next_id("SS", TAB_SESSIONS, SessionColumns.SESSION_ID)
            folder_result = self.controller.create_session_folder(session_id)
            if not folder_result.get("success"):
                return _response(False, folder_result.get("message", "Failed to create session folder."))

            folder_data = folder_result.get("data", {})
            folder_url = str(folder_data.get("folder_url") or "").strip()
            if not folder_url:
                return _response(False, "Session folder URL is missing.")

            folder_id = self.controller.get_folder_id_from_url(folder_url)
            if not folder_id:
                return _response(False, "Session folder ID is missing or invalid.")

            self._set_all_sessions_inactive()
            self.controller.append_row(TAB_SESSIONS, [session_id, normalized_name, "TRUE", folder_url])

            copy_summary: Dict[str, Any] = {
                "copy_previous": copy_previous,
                "source_session_id": previous_active_session.get("session_id", "") if previous_active_session else "",
                "source_session_name": previous_active_session.get("session_name", "") if previous_active_session else "",
                "copied": [],
                "failed": [],
                "source_school_count": 0,
                "copied_count": 0,
            }

            if copy_previous and previous_active_session and previous_active_session.get("session_id"):
                copy_summary = self._copy_previous_session_schools(
                    previous_session_id=str(previous_active_session.get("session_id", "")),
                    new_session_id=session_id,
                    new_session_folder_id=folder_id,
                )
                copy_summary["copy_previous"] = True
                copy_summary["source_session_id"] = previous_active_session.get("session_id", "")
                copy_summary["source_session_name"] = previous_active_session.get("session_name", "")

            return _response(
                True,
                "Session created and activated successfully.",
                {
                    "session_id": session_id,
                    "session_name": normalized_name,
                    "folder_url": folder_url,
                    "copy_summary": copy_summary,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create session: {exc}")

    def activate_session(self, session_id: str) -> Dict[str, Any]:
        try:
            target_session_id = session_id.strip()
            if not target_session_id:
                return _response(False, "session_id is required.")

            rows = self.controller.read_tab(TAB_SESSIONS)
            target_found = False

            for row_index, row in enumerate(rows[1:], start=2):
                current_session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
                session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
                folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
                if current_session_id == target_session_id:
                    target_found = True
                    self.controller.update_row(TAB_SESSIONS, row_index, [current_session_id, session_name, "TRUE", folder_url])
                else:
                    self.controller.update_row(TAB_SESSIONS, row_index, [current_session_id, session_name, "FALSE", folder_url])

            if not target_found:
                return _response(False, "session_id does not exist.")

            return _response(True, "Session activated successfully.", {"session_id": target_session_id})
        except Exception as exc:
            return _response(False, f"Failed to activate session: {exc}")


_MANAGER: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SessionManager()
    return _MANAGER


def create_session(session_name: str, copy_previous: bool = False) -> Dict[str, Any]:
    return get_session_manager().create_session(session_name, copy_previous)
