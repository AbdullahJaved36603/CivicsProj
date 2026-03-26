from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .auth_utils import USERNAME_EMPTY_MESSAGE, validate_and_normalize_username
    from .google_sheets_controller import GoogleSheetsController, get_controller
    from .principal_manager import PrincipalManager, get_principal_manager
    from .school_manager import SchoolManager, get_school_manager
    from .session_manager import SessionManager, get_session_manager
except ImportError:
    from auth_utils import USERNAME_EMPTY_MESSAGE, validate_and_normalize_username
    from google_sheets_controller import GoogleSheetsController, get_controller
    from principal_manager import PrincipalManager, get_principal_manager
    from school_manager import SchoolManager, get_school_manager
    from session_manager import SessionManager, get_session_manager


TAB_ACCOUNTS = "Accounts"
TAB_SESSIONS = "Sessions"
TAB_SCHOOLS = "Schools"
TAB_TEACHER_ASSIGNMENTS = "Teacher_Assignments"
TAB_PRINCIPAL_ASSIGNMENTS = "principal_assignments"
TAB_TEACHERS = "teachers"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"


class AccountsColumns:
    ROLE = 3


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


class TeacherAssignmentColumns:
    SCHOOL_ID = 2
    CLASS_ID = 3


class PrincipalAssignmentColumns:
    SCHOOL_ID = 1


class TeachersColumns:
    SCHOOL_ID = 1


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1


class SubjectsColumns:
    CLASS_ID = 1


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class SuperUserDashboard:
    def __init__(
        self,
        controller: Optional[GoogleSheetsController] = None,
        school_manager: Optional[SchoolManager] = None,
        principal_manager: Optional[PrincipalManager] = None,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.controller = controller or get_controller()
        self.school_manager = school_manager or get_school_manager()
        self.principal_manager = principal_manager or get_principal_manager()
        self.session_manager = session_manager or get_session_manager()

    @staticmethod
    def _is_active(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "active"}

    def _get_active_session(self) -> Optional[Tuple[str, str, str]]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            if SessionColumns.IS_ACTIVE < len(row) and self._is_active(row[SessionColumns.IS_ACTIVE]):
                session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
                session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
                folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
                return session_id, session_name, folder_url
        return None

    def _find_school_row(self, school_id: str) -> Optional[Tuple[int, List[str]]]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row_index, row in enumerate(rows[1:], start=2):
            if SchoolColumns.SCHOOL_ID < len(row) and row[SchoolColumns.SCHOOL_ID] == school_id:
                return row_index, row
        return None

    def _has_dependent_records(self, school_id: str) -> Dict[str, int]:
        dependencies: Dict[str, int] = {}

        teacher_assignments = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
        assignment_count = sum(
            1
            for row in teacher_assignments[1:]
            if TeacherAssignmentColumns.SCHOOL_ID < len(row) and row[TeacherAssignmentColumns.SCHOOL_ID] == school_id
        )
        if assignment_count:
            dependencies[TAB_TEACHER_ASSIGNMENTS] = assignment_count

        principal_assignments = self.controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
        principal_count = sum(
            1
            for row in principal_assignments[1:]
            if PrincipalAssignmentColumns.SCHOOL_ID < len(row)
            and row[PrincipalAssignmentColumns.SCHOOL_ID] == school_id
        )
        if principal_count:
            dependencies[TAB_PRINCIPAL_ASSIGNMENTS] = principal_count

        teachers = self.controller.read_tab(TAB_TEACHERS)
        teacher_count = sum(
            1
            for row in teachers[1:]
            if TeachersColumns.SCHOOL_ID < len(row) and row[TeachersColumns.SCHOOL_ID] == school_id
        )
        if teacher_count:
            dependencies[TAB_TEACHERS] = teacher_count

        classes_rows = self.controller.read_tab(TAB_CLASSES)
        class_rows = [
            row
            for row in classes_rows[1:]
            if ClassesColumns.SCHOOL_ID < len(row) and row[ClassesColumns.SCHOOL_ID] == school_id
        ]
        if class_rows:
            dependencies[TAB_CLASSES] = len(class_rows)

        class_ids: Set[str] = {
            row[ClassesColumns.CLASS_ID]
            for row in class_rows
            if ClassesColumns.CLASS_ID < len(row) and row[ClassesColumns.CLASS_ID]
        }
        if class_ids:
            subjects_rows = self.controller.read_tab(TAB_SUBJECTS)
            subject_count = sum(
                1
                for row in subjects_rows[1:]
                if SubjectsColumns.CLASS_ID < len(row) and row[SubjectsColumns.CLASS_ID] in class_ids
            )
            if subject_count:
                dependencies[TAB_SUBJECTS] = subject_count

        return dependencies

    def create_school(self, name: str) -> Dict[str, Any]:
        try:
            school_name = name.strip()
            if not school_name:
                return _response(False, "School name is required.")

            school_id = self.controller.generate_next_id("S", TAB_SCHOOLS, SchoolColumns.SCHOOL_ID)
            active_session = self._get_active_session()
            if not active_session:
                return _response(False, "Cannot create school without an active session")

            session_id, session_name, session_folder_url = active_session
            folder_id = self.controller.get_folder_id_from_url(session_folder_url)
            if not folder_id:
                return _response(False, "Active session folder URL is missing or invalid.")

            school_sheet_result = self.controller.create_sheet(f"{school_name} Master", str(folder_id))
            if not school_sheet_result.get("success"):
                return _response(False, school_sheet_result.get("message", "Failed to create school spreadsheet."))

            sheet_data = school_sheet_result.get("data", {})
            school_sheet_url = (
                sheet_data.get("school_sheet_url")
                or sheet_data.get("sheet_url")
                or sheet_data.get("spreadsheet_url")
                or sheet_data.get("url")
                or sheet_data.get("result")
            )
            if not school_sheet_url:
                spreadsheet_id = sheet_data.get("spreadsheet_id") or sheet_data.get("id")
                if spreadsheet_id:
                    school_sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

            if not school_sheet_url:
                return _response(False, "School spreadsheet URL was not returned by create_sheet.")

            self.controller.append_row(TAB_SCHOOLS, [school_id, school_name, session_id, school_sheet_url])
            structure_result = self.school_manager.initialize_school_structure(
                school_id=school_id,
                school_name=school_name,
                folder_id=str(folder_id),
            )

            if not structure_result.get("success"):
                return _response(
                    False,
                    "School created but structure initialization was partial.",
                    {
                        "school_id": school_id,
                        "school_name": school_name,
                        "session_id": session_id,
                        "session_name": session_name,
                        "school_sheet_url": school_sheet_url,
                        "session_folder_url": session_folder_url,
                        "structure_result": structure_result,
                    },
                )

            return _response(
                True,
                "School created successfully.",
                {
                    "school_id": school_id,
                    "school_name": school_name,
                    "session_id": session_id,
                    "session_name": session_name,
                    "school_sheet_url": school_sheet_url,
                    "session_folder_url": session_folder_url,
                    "structure_result": structure_result.get("data", {}),
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create school: {exc}")

    def delete_school(self, school_id: str) -> Dict[str, Any]:
        try:
            normalized_school_id = school_id.strip()
            if not normalized_school_id:
                return _response(False, "school_id is required.")

            found_school = self._find_school_row(normalized_school_id)
            if found_school is None:
                return _response(False, "School not found.")

            row_index, school_row = found_school
            school_session_id = (
                school_row[SchoolColumns.SESSION_ID] if SchoolColumns.SESSION_ID < len(school_row) else ""
            )

            if school_session_id:
                sessions_rows = self.controller.read_tab(TAB_SESSIONS)
                for row in sessions_rows[1:]:
                    current_session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
                    if current_session_id != school_session_id:
                        continue
                    if SessionColumns.IS_ACTIVE < len(row) and self._is_active(row[SessionColumns.IS_ACTIVE]):
                        return _response(False, "Cannot delete school with active session data.")

            dependencies = self._has_dependent_records(normalized_school_id)
            if dependencies:
                return _response(
                    False,
                    "Cannot delete school because dependent records exist.",
                    {"dependencies": dependencies},
                )

            self.controller.delete_row(TAB_SCHOOLS, row_index)
            return _response(True, "School deleted successfully.", {"school_id": normalized_school_id})
        except Exception as exc:
            return _response(False, f"Failed to delete school: {exc}")

    def create_session(self, name: str, copy_previous: bool = False) -> Dict[str, Any]:
        return self.session_manager.create_session(name, copy_previous)

    def create_principal(self, username: str) -> Dict[str, Any]:
        username_validation = validate_and_normalize_username(username)
        if not username_validation.get("success"):
            return _response(False, USERNAME_EMPTY_MESSAGE)

        normalized_username = str(username_validation.get("data", {}).get("username", "")).strip()
        return self.principal_manager.create_principal(normalized_username)

    def get_global_stats(self) -> Dict[str, Any]:
        try:
            accounts_rows = self.controller.read_tab(TAB_ACCOUNTS)
            schools_rows = self.controller.read_tab(TAB_SCHOOLS)
            sessions_rows = self.controller.read_tab(TAB_SESSIONS)
            principal_rows = self.controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)

            role_counts: Dict[str, int] = {}
            for row in accounts_rows[1:]:
                role = row[AccountsColumns.ROLE].strip().lower() if AccountsColumns.ROLE < len(row) else "unknown"
                role_counts[role] = role_counts.get(role, 0) + 1

            active_session: Dict[str, str] = {}
            for row in sessions_rows[1:]:
                if SessionColumns.IS_ACTIVE < len(row) and self._is_active(row[SessionColumns.IS_ACTIVE]):
                    active_session = {
                        "session_id": row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else "",
                        "session_name": row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else "",
                    }
                    break

            return _response(
                True,
                "Global stats fetched successfully.",
                {
                    "total_users": max(0, len(accounts_rows) - 1),
                    "total_schools": max(0, len(schools_rows) - 1),
                    "total_sessions": max(0, len(sessions_rows) - 1),
                    "active_session": active_session,
                    "principals_assigned": max(0, len(principal_rows) - 1),
                    "user_roles": role_counts,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to get global stats: {exc}")


_DASHBOARD: Optional[SuperUserDashboard] = None


def get_super_user_dashboard() -> SuperUserDashboard:
    global _DASHBOARD
    if _DASHBOARD is None:
        _DASHBOARD = SuperUserDashboard()
    return _DASHBOARD


def create_school(name: str) -> Dict[str, Any]:
    return get_super_user_dashboard().create_school(name)


def delete_school(school_id: str) -> Dict[str, Any]:
    return get_super_user_dashboard().delete_school(school_id)


def create_session(name: str, copy_previous: bool = False) -> Dict[str, Any]:
    return get_super_user_dashboard().create_session(name, copy_previous)


def get_global_stats() -> Dict[str, Any]:
    return get_super_user_dashboard().get_global_stats()
