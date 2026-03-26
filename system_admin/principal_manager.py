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
TAB_PRINCIPAL_ASSIGNMENTS = "principal_assignments"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"


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


class PrincipalAssignmentColumns:
    PRINCIPAL_ID = 0
    SCHOOL_ID = 1


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1
    CLASS_NAME = 2
    CLASS_SECTION = 3


class SubjectsColumns:
    SUBJECT_ID = 0
    CLASS_ID = 1
    SUBJECT_NAME = 2


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class PrincipalManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    def _school_exists(self, school_id: str) -> bool:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row in rows[1:]:
            if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
                return True
        return False

    def _username_exists(self, username: str) -> bool:
        rows = self.controller.read_tab(TAB_ACCOUNTS)
        target = username.strip().lower()
        for row in rows[1:]:
            if AccountsColumns.USERNAME < len(row) and row[AccountsColumns.USERNAME].strip().lower() == target:
                return True
        return False

    def _school_has_principal(self, school_id: str) -> bool:
        rows = self.controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
        for row in rows[1:]:
            if PrincipalAssignmentColumns.SCHOOL_ID < len(row) and row[PrincipalAssignmentColumns.SCHOOL_ID] == school_id:
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

    def _principal_already_assigned(self, principal_id: str) -> bool:
        rows = self.controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
        for row in rows[1:]:
            if PrincipalAssignmentColumns.PRINCIPAL_ID < len(row) and row[PrincipalAssignmentColumns.PRINCIPAL_ID] == principal_id:
                return True
        return False

    def _get_principal_school_id(self, principal_id: str) -> Optional[str]:
        rows = self.controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
        for row in rows[1:]:
            if PrincipalAssignmentColumns.PRINCIPAL_ID < len(row) and row[PrincipalAssignmentColumns.PRINCIPAL_ID] == principal_id:
                if PrincipalAssignmentColumns.SCHOOL_ID < len(row):
                    return row[PrincipalAssignmentColumns.SCHOOL_ID]
        return None

    def _get_school_row(self, school_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row in rows[1:]:
            if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
                return row
        return None

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

    def assign_principal_to_school(self, principal_id: str, school_id: str) -> Dict[str, Any]:
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
            if self._school_has_principal(normalized_school_id):
                return _response(False, "This school already has an assigned principal.")
            if self._principal_already_assigned(normalized_principal_id):
                return _response(False, "This principal is already assigned to a school.")

            self.controller.append_row(
                TAB_PRINCIPAL_ASSIGNMENTS,
                [normalized_principal_id, normalized_school_id],
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

    def create_class(self, principal_id: str, class_name: str, section: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_class_name = class_name.strip()
            normalized_section = section.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_class_name:
                return _response(False, "class_name is required.")
            if not normalized_section:
                return _response(False, "section is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            school_id = self._get_principal_school_id(normalized_principal_id)
            if not school_id:
                return _response(False, "Principal is not assigned to any school.")

            if self._class_exists_in_school(school_id, normalized_class_name, normalized_section):
                return _response(False, "Class with the same name and section already exists in this school.")

            school_row = self._get_school_row(school_id)
            if school_row is None:
                return _response(False, "Principal school does not exist.")

            school_sheet_url = (
                school_row[SchoolsColumns.SCHOOL_SHEET_URL] if SchoolsColumns.SCHOOL_SHEET_URL < len(school_row) else ""
            )
            spreadsheet_id = self.controller.get_school_sheet_id_from_url(school_sheet_url)
            if not spreadsheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            class_id = self.controller.generate_next_id("C", TAB_CLASSES, ClassesColumns.CLASS_ID)
            self.controller.append_row(TAB_CLASSES, [class_id, school_id, normalized_class_name, normalized_section])

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
                    "school_id": school_id,
                    "tab_name": tab_name,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create class: {exc}")

    def delete_class(self, principal_id: str, class_id: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_class_id = class_id.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            school_id = self._get_principal_school_id(normalized_principal_id)
            if not school_id:
                return _response(False, "Principal is not assigned to any school.")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class not found.")

            row_index, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != school_id:
                return _response(False, "Class not found in your school.")

            class_name = class_row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(class_row) else ""
            class_section = class_row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(class_row) else ""
            tab_name = f"{class_name}-{class_section}"

            school_row = self._get_school_row(school_id)
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

    def create_subject(self, principal_id: str, class_id: str, subject_name: str) -> Dict[str, Any]:
        try:
            normalized_principal_id = principal_id.strip()
            normalized_class_id = class_id.strip()
            normalized_subject_name = subject_name.strip()

            if not normalized_principal_id:
                return _response(False, "principal_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_subject_name:
                return _response(False, "subject_name is required.")
            if not self._is_principal_user(normalized_principal_id):
                return _response(False, "Invalid principal_id. Principal account does not exist.")

            school_id = self._get_principal_school_id(normalized_principal_id)
            if not school_id:
                return _response(False, "Principal is not assigned to any school.")

            class_found = self._find_class_row(normalized_class_id)
            if class_found is None:
                return _response(False, "Class does not exist.")

            _, class_row = class_found
            class_school_id = class_row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(class_row) else ""
            if class_school_id != school_id:
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


_MANAGER: Optional[PrincipalManager] = None


def get_principal_manager() -> PrincipalManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PrincipalManager()
    return _MANAGER


def create_principal(username: str) -> Dict[str, Any]:
    return get_principal_manager().create_principal(username)


def assign_principal_to_school(principal_id: str, school_id: str) -> Dict[str, Any]:
    return get_principal_manager().assign_principal_to_school(principal_id, school_id)


def create_class(principal_id: str, class_name: str, section: str) -> Dict[str, Any]:
    return get_principal_manager().create_class(principal_id, class_name, section)


def delete_class(principal_id: str, class_id: str) -> Dict[str, Any]:
    return get_principal_manager().delete_class(principal_id, class_id)


def create_subject(principal_id: str, class_id: str, subject_name: str) -> Dict[str, Any]:
    return get_principal_manager().create_subject(principal_id, class_id, subject_name)
