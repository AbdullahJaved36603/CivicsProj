from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller


TAB_SCHOOLS = "Schools"


class SchoolColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1
    SESSION_ID = 2
    SCHOOL_SHEET_URL = 3


DEFAULT_SCHOOL_STRUCTURE_TABS = ["Classes", "Students", "Exams", "Performance"]


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class SchoolManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    def _find_school_row(self, school_id: str) -> Optional[Tuple[int, List[str]]]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row_index, row in enumerate(rows[1:], start=2):
            if SchoolColumns.SCHOOL_ID < len(row) and row[SchoolColumns.SCHOOL_ID] == school_id:
                return row_index, row
        return None

    def school_exists(self, school_id: str) -> bool:
        return self._find_school_row(school_id) is not None

    def get_school_metadata(self, school_id: str) -> Dict[str, Any]:
        try:
            if not school_id.strip():
                return _response(False, "school_id is required.")
            found = self._find_school_row(school_id.strip())
            if found is None:
                return _response(False, "School not found.")
            _, row = found
            return _response(
                True,
                "School metadata retrieved successfully.",
                {
                    "school_id": row[SchoolColumns.SCHOOL_ID] if SchoolColumns.SCHOOL_ID < len(row) else "",
                    "school_name": row[SchoolColumns.SCHOOL_NAME] if SchoolColumns.SCHOOL_NAME < len(row) else "",
                    "session_id": row[SchoolColumns.SESSION_ID] if SchoolColumns.SESSION_ID < len(row) else "",
                    "school_sheet_url": row[SchoolColumns.SCHOOL_SHEET_URL]
                    if SchoolColumns.SCHOOL_SHEET_URL < len(row)
                    else "",
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to retrieve school metadata: {exc}")

    def initialize_school_structure(
        self,
        school_id: str,
        school_name: str,
        folder_id: str,
    ) -> Dict[str, Any]:
        """Create required school files using create_sheet(sheet_name, folder_id)."""
        try:
            school_id = school_id.strip()
            school_name = school_name.strip()
            folder_id = folder_id.strip()

            if not school_id:
                return _response(False, "school_id is required.")
            if not school_name:
                return _response(False, "school_name is required.")
            if not folder_id:
                return _response(False, "folder_id is required.")

            created: Dict[str, Dict[str, Any]] = {}
            failures: Dict[str, str] = {}

            for tab_name in DEFAULT_SCHOOL_STRUCTURE_TABS:
                resource_name = f"{school_name} - {tab_name}"
                result = self.controller.create_sheet(resource_name, folder_id)
                if result.get("success"):
                    created[tab_name] = result.get("data", {})
                else:
                    failures[tab_name] = result.get("message", "Unknown error")

            if failures:
                return _response(
                    False,
                    "School structure initialized partially.",
                    {
                        "school_id": school_id,
                        "created_resources": created,
                        "failed_resources": failures,
                    },
                )

            return _response(
                True,
                "School structure initialized successfully.",
                {"school_id": school_id, "created_resources": created},
            )
        except Exception as exc:
            return _response(False, f"Failed to initialize school structure: {exc}")


_MANAGER: Optional[SchoolManager] = None


def get_school_manager() -> SchoolManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SchoolManager()
    return _MANAGER
