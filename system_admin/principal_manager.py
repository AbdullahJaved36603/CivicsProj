from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional, Tuple

try:
    relational_fernet_module = importlib.import_module("relational_fernet")
    relational_fernet = getattr(relational_fernet_module, "relational_fernet", None)
except Exception:  # pragma: no cover - depends on deployment environment
    relational_fernet = None

try:
    from .auth_utils import (
        USERNAME_EMPTY_MESSAGE,
        generate_unique_password,
        get_existing_plain_passwords,
        validate_and_normalize_username,
    )
    from .google_sheets_controller import GoogleSheetsController, get_controller
except ImportError:
    from auth_utils import (
        USERNAME_EMPTY_MESSAGE,
        generate_unique_password,
        get_existing_plain_passwords,
        validate_and_normalize_username,
    )
    from google_sheets_controller import GoogleSheetsController, get_controller


TAB_ACCOUNTS = "Accounts"
TAB_SCHOOLS = "Schools"
TAB_SESSIONS = "Sessions"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"
TAB_TEACHERS = "teachers"


class AccountsColumns:
    USER_ID = 0
    USERNAME = 1
    PASSWORD = 2
    ROLE = 3
    STATUS = 4


class SchoolsColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1
    SESSION_ID = 2
    SCHOOL_SHEET_URL = 3
    PRINCIPAL_ID = 4


class SessionColumns:
    SESSION_ID = 0
    IS_ACTIVE = 2


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1
    CLASS_NAME = 2
    CLASS_SECTION = 3
    CLASS_INCHARGE_TEACHER_ID = 4


class SubjectsColumns:
    SUBJECT_ID = 0
    CLASS_ID = 1
    SUBJECT_NAME = 2


class TeachersColumns:
    TEACHER_ID = 0
    TEACHER_NAME = 1
    SCHOOL_ID = 2
    SESSION_ID = 3


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class PrincipalManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    @staticmethod
    def _safe_get(row: List[str], index: int) -> str:
        return row[index] if index < len(row) else ""

    def _school_exists(self, school_id: str) -> bool:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row in rows[1:]:
            if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
                return True
        return False

    @staticmethod
    def _is_active(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "active"}

    def _get_active_session_id(self) -> Optional[str]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
            is_active = row[SessionColumns.IS_ACTIVE] if SessionColumns.IS_ACTIVE < len(row) else ""
            if session_id and self._is_active(is_active):
                return session_id
        return None

    def _school_is_in_active_session(self, school_id: str) -> bool:
        school_row = self._get_school_row(school_id)
        if school_row is None:
            return False
        school_session_id = school_row[SchoolsColumns.SESSION_ID] if SchoolsColumns.SESSION_ID < len(school_row) else ""
        active_session_id = self._get_active_session_id()
        if not active_session_id:
            return False
        return school_session_id == active_session_id

    def _username_exists(self, username: str) -> bool:
        rows = self.controller.read_tab(TAB_ACCOUNTS)
        target = username.strip().lower()
        for row in rows[1:]:
            if AccountsColumns.USERNAME < len(row) and row[AccountsColumns.USERNAME].strip().lower() == target:
                return True
        return False

    def _get_account_row_by_user_id(self, user_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_ACCOUNTS)
        for row in rows[1:]:
            if AccountsColumns.USER_ID < len(row) and row[AccountsColumns.USER_ID] == user_id:
                return row
        return None

    def _is_principal_user(self, user_id: str) -> bool:
        account_row = self._get_account_row_by_user_id(user_id)
        if account_row is None:
            return False
        if AccountsColumns.ROLE >= len(account_row):
            return False
        return account_row[AccountsColumns.ROLE].strip().lower() == "principal"

    def _get_principal_school_ids(self, principal_id: str, active_only: bool = True) -> List[str]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        active_session_id = self._get_active_session_id() if active_only else ""
        school_ids: List[str] = []
        for row in rows[1:]:
            row_principal_id = self._safe_get(row, SchoolsColumns.PRINCIPAL_ID)
            if row_principal_id != principal_id:
                continue
            if active_only:
                row_session_id = self._safe_get(row, SchoolsColumns.SESSION_ID)
                if not active_session_id or row_session_id != active_session_id:
                    continue
            school_id = self._safe_get(row, SchoolsColumns.SCHOOL_ID)
            if school_id:
                school_ids.append(school_id)
        return school_ids

    def _principal_has_school_access(self, principal_id: str, school_id: str) -> bool:
        assigned_school_ids = set(self._get_principal_school_ids(principal_id, active_only=True))
        return school_id in assigned_school_ids

    def _get_school_row(self, school_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row in rows[1:]:
            if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
                return row
        return None

    def _build_school_row(self, school_row: List[str], principal_id: str) -> List[str]:
        school_id = self._safe_get(school_row, SchoolsColumns.SCHOOL_ID)
        school_name = self._safe_get(school_row, SchoolsColumns.SCHOOL_NAME)
        session_id = self._safe_get(school_row, SchoolsColumns.SESSION_ID)
        school_sheet_url = self._safe_get(school_row, SchoolsColumns.SCHOOL_SHEET_URL)
        updated_row = [school_id, school_name, session_id, school_sheet_url, principal_id]
        if len(school_row) > len(updated_row):
            updated_row.extend(school_row[len(updated_row) :])
        return updated_row

    def _find_class_row(self, class_id: str) -> Optional[Tuple[int, List[str]]]:
        rows = self.controller.read_tab(TAB_CLASSES)
        for row_index, row in enumerate(rows[1:], start=2):
            if ClassesColumns.CLASS_ID < len(row) and row[ClassesColumns.CLASS_ID] == class_id:
                return row_index, row
        return None

    def _class_exists_in_school(self, school_id: str, class_name: str, section: str) -> bool:
        rows = self.controller.read_tab(TAB_CLASSES)
        target_name = class_name.strip().lower()
        target_section = section.strip().lower()
        for row in rows[1:]:
            row_school_id = row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(row) else ""
            row_class_name = row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(row) else ""
            row_section = row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(row) else ""
            if row_school_id != school_id:
                continue
            if row_class_name.strip().lower() == target_name and row_section.strip().lower() == target_section:
                return True
        return False

    def _subject_exists_in_class(self, class_id: str, subject_name: str) -> bool:
        rows = self.controller.read_tab(TAB_SUBJECTS)
        target_name = subject_name.strip().lower()
        for row in rows[1:]:
            row_class_id = row[SubjectsColumns.CLASS_ID] if SubjectsColumns.CLASS_ID < len(row) else ""
            row_subject_name = row[SubjectsColumns.SUBJECT_NAME] if SubjectsColumns.SUBJECT_NAME < len(row) else ""
            if row_class_id != class_id:
                continue
            if row_subject_name.strip().lower() == target_name:
                return True
        return False

    def _teacher_belongs_to_school(self, teacher_id: str, school_id: str) -> bool:
        active_session_id = self._get_active_session_id()
        if not active_session_id:
            return False

        rows = self.controller.read_tab(TAB_TEACHERS)
        for row in rows[1:]:
            row_teacher_id = row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else ""
            row_school_id = row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else ""
            row_session_id = row[TeachersColumns.SESSION_ID] if TeachersColumns.SESSION_ID < len(row) else ""
            if row_teacher_id == teacher_id and row_school_id == school_id and row_session_id == active_session_id:
                return True
        return False

    @staticmethod
    def _serialize_class_row(
        class_id: str,
        school_id: str,
        class_name: str,
        class_section: str,
        class_incharge_teacher_id: str,
    ) -> List[str]:
        return [class_id, school_id, class_name, class_section, class_incharge_teacher_id]

    def _encrypt_password(self, plain_password: str) -> str:
        if relational_fernet is None:
            raise RuntimeError("relational_fernet is not available for password encryption.")
        encrypted = relational_fernet.encrypt(plain_password.encode())
        if isinstance(encrypted, bytes):
            return encrypted.decode()
        return str(encrypted)

    def create_principal(self, username: str) -> Dict[str, Any]:
        try:
            username_validation = validate_and_normalize_username(username)
            if not username_validation.get("success"):
                return _response(False, USERNAME_EMPTY_MESSAGE)
            normalized_username = str(username_validation.get("data", {}).get("username", "")).strip()

            if self._username_exists(normalized_username):
                return _response(False, "Username already exists")

            accounts_rows = self.controller.read_tab(TAB_ACCOUNTS)
            existing_plain_passwords = get_existing_plain_passwords(
                accounts_rows[1:],
                AccountsColumns.PASSWORD,
            )

            user_id = self.controller.generate_next_id("U", TAB_ACCOUNTS, AccountsColumns.USER_ID)
            plain_password = generate_unique_password(existing_plain_passwords)
            encrypted_password = self._encrypt_password(plain_password)

            self.controller.append_row(
                TAB_ACCOUNTS,
                [user_id, normalized_username, encrypted_password, "principal", "active"],
            )

            return _response(
                True,
                "Principal account created successfully.",
                {
                    "principal_id": user_id,
                    "username": normalized_username,
                    "generated_password": plain_password,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create principal: {exc}")

    def assign_principal_to_school(self, principal_id: str, school_id: str, replace_existing: bool = False) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")
            if not self._school_exists(normalized_school_id):
                return _response(False, "Invalid school_id. School does not exist.")

            school_row_index: Optional[int] = None
            school_row: Optional[List[str]] = None
            schools_rows = self.controller.read_tab(TAB_SCHOOLS)
            for row_index, row in enumerate(schools_rows[1:], start=2):
                row_school_id = self._safe_get(row, SchoolsColumns.SCHOOL_ID)
                if row_school_id == normalized_school_id:
                    school_row_index = row_index
                    school_row = row
                    break

            if school_row_index is None or school_row is None:
                return _response(False, "Invalid school_id. School does not exist.")

            existing_principal_id = self._safe_get(school_row, SchoolsColumns.PRINCIPAL_ID)
            if existing_principal_id and existing_principal_id != normalized_principal_id and not replace_existing:
                return _response(False, "This school already has an assigned principal.")

            if existing_principal_id == normalized_principal_id:
                return _response(
                    True,
                    "Principal already assigned to this school.",
                    {
                        "principal_id": normalized_principal_id,
                        "school_id": normalized_school_id,
                    },
                )

            self.controller.update_row(
                TAB_SCHOOLS,
                school_row_index,
                self._build_school_row(school_row, normalized_principal_id),
            )

            return _response(
                True,
                "Principal assigned to school successfully.",
                {
                    "principal_id": normalized_principal_id,
                    "school_id": normalized_school_id,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to assign principal to school: {exc}")

    def create_class(self, principal_id: str, school_id: str, class_name: str, section: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_name = class_name.strip()
            normalized_section = section.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_class_name:
                return _response(False, "class_name is required.")
            if not normalized_section:
                return _response(False, "section is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            if not self._principal_has_school_access(normalized_principal_id, normalized_school_id):
                return _response(False, "Access denied")

            if self._class_exists_in_school(normalized_school_id, normalized_class_name, normalized_section):
                return _response(False, "Class with the same name and section already exists in this school.")

            school_row = self._get_school_row(normalized_school_id)
            if school_row is None:
                return _response(False, "Principal school does not exist.")

            school_sheet_url = (
                school_row[SchoolsColumns.SCHOOL_SHEET_URL] if SchoolsColumns.SCHOOL_SHEET_URL < len(school_row) else ""
            )
            spreadsheet_id = self.controller.get_school_sheet_id_from_url(school_sheet_url)
            if not spreadsheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            class_id = self.controller.generate_next_id("C", TAB_CLASSES, ClassesColumns.CLASS_ID)
            self.controller.append_row(
                TAB_CLASSES,
                self._serialize_class_row(class_id, normalized_school_id, normalized_class_name, normalized_section, ""),
            )

            tab_name = f"{normalized_class_name}-{normalized_section}"
            tab_result = self.controller.create_class_tab(spreadsheet_id, tab_name)
            if not tab_result.get("success"):
                class_row = self._find_class_row(class_id)
                if class_row is not None:
                    self.controller.delete_row(TAB_CLASSES, class_row[0])
                return _response(False, tab_result.get("message", "Failed to create class worksheet tab."))

            return _response(
                True,
                "Class created successfully.",
                {
                    "class_id": class_id,
                    "school_id": normalized_school_id,
                    "tab_name": tab_name,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create class: {exc}")

    def delete_class(self, principal_id: str, school_id: str, class_id: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_id = class_id.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            if not self._principal_has_school_access(normalized_principal_id, normalized_school_id):
                return _response(False, "Access denied")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class not found.")

            row_index, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != normalized_school_id:
                return _response(False, "Class not found in your school.")

            class_name = class_row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(class_row) else ""
            class_section = class_row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(class_row) else ""
            tab_name = f"{class_name}-{class_section}"

            school_row = self._get_school_row(normalized_school_id)
            if school_row is None:
                return _response(False, "Principal school does not exist.")

            school_sheet_url = (
                school_row[SchoolsColumns.SCHOOL_SHEET_URL] if SchoolsColumns.SCHOOL_SHEET_URL < len(school_row) else ""
            )
            spreadsheet_id = self.controller.get_school_sheet_id_from_url(school_sheet_url)
            if not spreadsheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            self.controller.delete_row(TAB_CLASSES, row_index)
            tab_result = self.controller.delete_class_tab(spreadsheet_id, tab_name)
            if not tab_result.get("success"):
                return _response(
                    False,
                    "Class row deleted, but worksheet tab deletion failed.",
                    {"class_id": normalized_class_id, "tab_name": tab_name},
                )

            return _response(
                True,
                "Class deleted successfully.",
                {
                    "class_id": normalized_class_id,
                    "tab_name": tab_name,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to delete class: {exc}")

    def create_subject(self, principal_id: str, school_id: str, class_id: str, subject_name: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_id = class_id.strip()
            normalized_subject_name = subject_name.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_subject_name:
                return _response(False, "subject_name is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            if not self._principal_has_school_access(normalized_principal_id, normalized_school_id):
                return _response(False, "Access denied")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class does not exist.")

            _, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != normalized_school_id:
                return _response(False, "Class does not belong to your school.")

            if self._subject_exists_in_class(normalized_class_id, normalized_subject_name):
                return _response(False, "Subject already exists in this class.")

            subject_id = self.controller.generate_next_id("SUB", TAB_SUBJECTS, SubjectsColumns.SUBJECT_ID)
            self.controller.append_row(TAB_SUBJECTS, [subject_id, normalized_class_id, normalized_subject_name])

            return _response(
                True,
                "Subject created successfully.",
                {
                    "subject_id": subject_id,
                    "class_id": normalized_class_id,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create subject: {exc}")

    def assign_class_incharge(self, principal_id: str, school_id: str, class_id: str, teacher_id: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_id = class_id.strip()
            normalized_teacher_id = teacher_id.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            if not self._principal_has_school_access(normalized_principal_id, normalized_school_id):
                return _response(False, "Access denied")
            if not self._teacher_belongs_to_school(normalized_teacher_id, normalized_school_id):
                return _response(False, "Teacher not found in your school.")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class does not exist.")

            class_row_index, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != normalized_school_id:
                return _response(False, "Class does not belong to your school.")

            all_classes = self.controller.read_tab(TAB_CLASSES)
            for row in all_classes[1:]:
                existing_class_id = row[ClassesColumns.CLASS_ID] if ClassesColumns.CLASS_ID < len(row) else ""
                existing_school_id = row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(row) else ""
                existing_incharge = (
                    row[ClassesColumns.CLASS_INCHARGE_TEACHER_ID]
                    if ClassesColumns.CLASS_INCHARGE_TEACHER_ID < len(row)
                    else ""
                )
                if existing_class_id == normalized_class_id:
                    continue
                if existing_school_id != normalized_school_id:
                    continue
                if existing_incharge == normalized_teacher_id:
                    return _response(False, "Teacher is already class incharge for another class.")

            class_name = class_row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(class_row) else ""
            class_section = class_row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(class_row) else ""

            self.controller.update_row(
                TAB_CLASSES,
                class_row_index,
                self._serialize_class_row(
                    normalized_class_id,
                    normalized_school_id,
                    class_name,
                    class_section,
                    normalized_teacher_id,
                ),
            )

            return _response(
                True,
                "Class incharge assigned successfully.",
                {
                    "class_id": normalized_class_id,
                    "teacher_id": normalized_teacher_id,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to assign class incharge: {exc}")

    def deassign_class_incharge(self, principal_id: str, school_id: str, class_id: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_id = class_id.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            if not self._principal_has_school_access(normalized_principal_id, normalized_school_id):
                return _response(False, "Access denied")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class does not exist.")

            class_row_index, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != normalized_school_id:
                return _response(False, "Class does not belong to your school.")

            class_name = class_row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(class_row) else ""
            class_section = class_row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(class_row) else ""
            current_incharge = (
                class_row[ClassesColumns.CLASS_INCHARGE_TEACHER_ID]
                if ClassesColumns.CLASS_INCHARGE_TEACHER_ID < len(class_row)
                else ""
            )
            if not current_incharge:
                return _response(False, "Class does not have an assigned incharge.")

            self.controller.update_row(
                TAB_CLASSES,
                class_row_index,
                self._serialize_class_row(
                    normalized_class_id,
                    normalized_school_id,
                    class_name,
                    class_section,
                    "",
                ),
            )
            return _response(
                True,
                "Class incharge removed successfully.",
                {
                    "class_id": normalized_class_id,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to remove class incharge: {exc}")


_MANAGER: Optional[PrincipalManager] = None


def get_principal_manager() -> PrincipalManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PrincipalManager()
    return _MANAGER


def create_principal(username: str) -> Dict[str, Any]:
    return get_principal_manager().create_principal(username)


def assign_principal_to_school(principal_id: str, school_id: str, replace_existing: bool = False) -> Dict[str, Any]:
    return get_principal_manager().assign_principal_to_school(principal_id, school_id, replace_existing=replace_existing)


def create_class(principal_id: str, school_id: str, class_name: str, section: str) -> Dict[str, Any]:
    return get_principal_manager().create_class(principal_id, school_id, class_name, section)


def delete_class(principal_id: str, school_id: str, class_id: str) -> Dict[str, Any]:
    return get_principal_manager().delete_class(principal_id, school_id, class_id)


def create_subject(principal_id: str, school_id: str, class_id: str, subject_name: str) -> Dict[str, Any]:
    return get_principal_manager().create_subject(principal_id, school_id, class_id, subject_name)


def assign_class_incharge(principal_id: str, school_id: str, class_id: str, teacher_id: str) -> Dict[str, Any]:
    return get_principal_manager().assign_class_incharge(principal_id, school_id, class_id, teacher_id)


def deassign_class_incharge(principal_id: str, school_id: str, class_id: str) -> Dict[str, Any]:
    return get_principal_manager().deassign_class_incharge(principal_id, school_id, class_id)
