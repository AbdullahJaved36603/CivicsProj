from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

try:
    from .auth_utils import (
        USERNAME_EMPTY_MESSAGE,
        authenticate,
        generate_unique_password,
        get_existing_plain_passwords,
        validate_and_normalize_username,
    )
    from .google_sheets_controller import get_controller
    from .principal_manager import get_principal_manager
    from .school_analytics import get_school_analytics as get_school_analytics_service
    from .session_manager import get_session_manager
    from .super_user_dashboard import get_super_user_dashboard
except ImportError:
    from auth_utils import (
        USERNAME_EMPTY_MESSAGE,
        authenticate,
        generate_unique_password,
        get_existing_plain_passwords,
        validate_and_normalize_username,
    )
    from google_sheets_controller import get_controller
    from principal_manager import get_principal_manager
    from school_analytics import get_school_analytics as get_school_analytics_service
    from session_manager import get_session_manager
    from super_user_dashboard import get_super_user_dashboard


TAB_ACCOUNTS = "Accounts"
TAB_SCHOOLS = "Schools"
TAB_SESSIONS = "Sessions"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"
TAB_TEACHERS = "teachers"
TAB_PRINCIPAL_ASSIGNMENTS = "principal_assignments"
TAB_TEACHER_ASSIGNMENTS = "Teacher_Assignments"

try:
    relational_fernet_module = importlib.import_module("relational_fernet")
    relational_fernet = getattr(relational_fernet_module, "relational_fernet", None)
except Exception:
    relational_fernet = None


class AccountsColumns:
    USER_ID = 0
    USERNAME = 1
    PASSWORD = 2
    ROLE = 3
    STATUS = 4


class SchoolsColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1


class SessionsColumns:
    SESSION_ID = 0
    SESSION_NAME = 1
    IS_ACTIVE = 2
    FOLDER_URL = 3


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1
    CLASS_NAME = 2
    CLASS_SECTION = 3


class SubjectsColumns:
    SUBJECT_ID = 0
    CLASS_ID = 1
    SUBJECT_NAME = 2


class TeachersColumns:
    TEACHER_ID = 0
    SCHOOL_ID = 1


class PrincipalAssignmentsColumns:
    PRINCIPAL_ID = 0
    SCHOOL_ID = 1


class TeacherAssignmentsColumns:
    ASSIGNMENT_ID = 0
    TEACHER_ID = 1
    SCHOOL_ID = 2
    CLASS_ID = 3
    SUBJECT_ID = 4


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _is_active(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "active"}


def _get_account(user_id: str) -> Optional[List[str]]:
    controller = get_controller()
    rows = controller.read_tab(TAB_ACCOUNTS)
    for row in rows[1:]:
        if AccountsColumns.USER_ID < len(row) and row[AccountsColumns.USER_ID] == user_id:
            return row
    return None


def _require_role(user_id: str, role: str) -> Dict[str, Any]:
    account = _get_account(user_id)
    if account is None:
        return _response(False, "User does not exist.")
    row_role = account[AccountsColumns.ROLE].strip().lower() if AccountsColumns.ROLE < len(account) else ""
    if row_role not in {role.strip().lower(), "super_user" if role == "admin" else role.strip().lower()}:
        if role == "admin" and row_role in {"admin", "super_user"}:
            return _response(True, "ok")
        return _response(False, "Access denied")
    return _response(True, "ok")


def _school_exists(school_id: str) -> bool:
    controller = get_controller()
    rows = controller.read_tab(TAB_SCHOOLS)
    for row in rows[1:]:
        if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
            return True
    return False


def _get_principal_school_id(principal_id: str) -> Optional[str]:
    controller = get_controller()
    rows = controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
    for row in rows[1:]:
        if PrincipalAssignmentsColumns.PRINCIPAL_ID < len(row) and row[PrincipalAssignmentsColumns.PRINCIPAL_ID] == principal_id:
            if PrincipalAssignmentsColumns.SCHOOL_ID < len(row):
                return row[PrincipalAssignmentsColumns.SCHOOL_ID]
    return None


def _get_teacher_school_id(teacher_id: str) -> Optional[str]:
    controller = get_controller()
    rows = controller.read_tab(TAB_TEACHERS)
    for row in rows[1:]:
        tid = row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else ""
        if tid == teacher_id:
            if TeachersColumns.SCHOOL_ID < len(row):
                return row[TeachersColumns.SCHOOL_ID]
    return None


def _get_school_name(school_id: str) -> str:
    controller = get_controller()
    rows = controller.read_tab(TAB_SCHOOLS)
    for row in rows[1:]:
        if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
            return row[SchoolsColumns.SCHOOL_NAME] if SchoolsColumns.SCHOOL_NAME < len(row) else ""
    return ""


def login(username: str, password: str) -> Dict[str, Any]:
    return authenticate(username, password)


def create_school(admin_id: str, school_name: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_super_user_dashboard().create_school(school_name)


def delete_school(admin_id: str, school_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_super_user_dashboard().delete_school(school_id)


def create_session(admin_id: str, session_name: str, copy_previous: bool = False) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_session_manager().create_session(session_name, copy_previous)


def activate_session(admin_id: str, session_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_session_manager().activate_session(session_id)


def deactivate_session(admin_id: str, session_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check

    controller = get_controller()
    rows = controller.read_tab(TAB_SESSIONS)
    for idx, row in enumerate(rows[1:], start=2):
        current_id = row[SessionsColumns.SESSION_ID] if SessionsColumns.SESSION_ID < len(row) else ""
        current_name = row[SessionsColumns.SESSION_NAME] if SessionsColumns.SESSION_NAME < len(row) else ""
        folder_url = row[SessionsColumns.FOLDER_URL] if SessionsColumns.FOLDER_URL < len(row) else ""
        if current_id == session_id:
            controller.update_row(TAB_SESSIONS, idx, [current_id, current_name, "FALSE", folder_url])
            return _response(True, "Session deactivated successfully.", {"session_id": session_id})
    return _response(False, "session_id does not exist.")


def create_principal(admin_id: str, username: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_principal_manager().create_principal(username)


def assign_principal(admin_id: str, principal_id: str, school_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    return get_principal_manager().assign_principal_to_school(principal_id, school_id)


def deassign_principal(admin_id: str, principal_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check

    controller = get_controller()
    rows = controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
    for idx, row in enumerate(rows[1:], start=2):
        pid = row[PrincipalAssignmentsColumns.PRINCIPAL_ID] if PrincipalAssignmentsColumns.PRINCIPAL_ID < len(row) else ""
        if pid == principal_id:
            controller.delete_row(TAB_PRINCIPAL_ASSIGNMENTS, idx)
            return _response(True, "Principal deassigned successfully.", {"principal_id": principal_id})
    return _response(False, "Principal assignment not found.")


def deactivate_principal(admin_id: str, principal_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check

    controller = get_controller()
    rows = controller.read_tab(TAB_ACCOUNTS)
    for idx, row in enumerate(rows[1:], start=2):
        uid = row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else ""
        role = row[AccountsColumns.ROLE] if AccountsColumns.ROLE < len(row) else ""
        if uid == principal_id and role.strip().lower() == "principal":
            username = row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else ""
            password = row[AccountsColumns.PASSWORD] if AccountsColumns.PASSWORD < len(row) else ""
            controller.update_row(TAB_ACCOUNTS, idx, [uid, username, password, "principal", "inactive"])
            return _response(True, "Principal deactivated successfully.", {"principal_id": principal_id})
    return _response(False, "Principal account not found.")


def create_class(principal_id: str, class_name: str, section: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check
    return get_principal_manager().create_class(principal_id, class_name, section)


def delete_class(principal_id: str, class_id: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check
    return get_principal_manager().delete_class(principal_id, class_id)


def create_subject(principal_id: str, class_id: str, subject_name: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check
    return get_principal_manager().create_subject(principal_id, class_id, subject_name)


def create_teacher(principal_id: str, username: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check

    username_validation = validate_and_normalize_username(username)
    if not username_validation.get("success"):
        return _response(False, USERNAME_EMPTY_MESSAGE)
    normalized_username = str(username_validation.get("data", {}).get("username", "")).strip()

    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")

    controller = get_controller()
    accounts_rows = controller.read_tab(TAB_ACCOUNTS)
    for row in accounts_rows[1:]:
        existing_username = row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else ""
        if existing_username.strip().lower() == normalized_username.lower():
            return _response(False, "Username already exists")

    if relational_fernet is None:
        return _response(False, "Encryption service is unavailable.")

    existing_plain_passwords = get_existing_plain_passwords(accounts_rows[1:], AccountsColumns.PASSWORD)
    plain_password = generate_unique_password(existing_plain_passwords)
    encrypted_password_raw = relational_fernet.encrypt(plain_password.encode())
    encrypted_password = (
        encrypted_password_raw.decode() if isinstance(encrypted_password_raw, bytes) else str(encrypted_password_raw)
    )

    user_id = controller.generate_next_id("U", TAB_ACCOUNTS, AccountsColumns.USER_ID)
    controller.append_row(TAB_ACCOUNTS, [user_id, normalized_username, encrypted_password, "teacher", "active"])
    controller.append_row(TAB_TEACHERS, [user_id, school_id])
    return _response(
        True,
        "Teacher created successfully.",
        {"teacher_id": user_id, "school_id": school_id, "generated_password": plain_password},
    )


def delete_teacher(principal_id: str, teacher_id: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check

    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")

    controller = get_controller()
    teacher_rows = controller.read_tab(TAB_TEACHERS)
    teacher_found = False
    for idx, row in enumerate(teacher_rows[1:], start=2):
        tid = row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else ""
        sid = row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else ""
        if tid == teacher_id and sid == school_id:
            controller.delete_row(TAB_TEACHERS, idx)
            teacher_found = True
            break

    if not teacher_found:
        return _response(False, "Teacher not found in your school.")

    accounts_rows = controller.read_tab(TAB_ACCOUNTS)
    for idx, row in enumerate(accounts_rows[1:], start=2):
        uid = row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else ""
        if uid == teacher_id:
            username = row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else ""
            password = row[AccountsColumns.PASSWORD] if AccountsColumns.PASSWORD < len(row) else ""
            controller.update_row(TAB_ACCOUNTS, idx, [uid, username, password, "teacher", "inactive"])
            break

    return _response(True, "Teacher deactivated successfully.", {"teacher_id": teacher_id})


def assign_teacher(principal_id: str, teacher_id: str, class_id: str, subject_id: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check

    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")

    controller = get_controller()

    teacher_valid = any(
        (TeachersColumns.TEACHER_ID < len(row) and row[TeachersColumns.TEACHER_ID] == teacher_id)
        and (TeachersColumns.SCHOOL_ID < len(row) and row[TeachersColumns.SCHOOL_ID] == school_id)
        for row in controller.read_tab(TAB_TEACHERS)[1:]
    )
    if not teacher_valid:
        return _response(False, "Teacher not found in your school.")

    class_valid = any(
        (ClassesColumns.CLASS_ID < len(row) and row[ClassesColumns.CLASS_ID] == class_id)
        and (ClassesColumns.SCHOOL_ID < len(row) and row[ClassesColumns.SCHOOL_ID] == school_id)
        for row in controller.read_tab(TAB_CLASSES)[1:]
    )
    if not class_valid:
        return _response(False, "Class not found in your school.")

    subject_valid = any(
        (SubjectsColumns.SUBJECT_ID < len(row) and row[SubjectsColumns.SUBJECT_ID] == subject_id)
        and (SubjectsColumns.CLASS_ID < len(row) and row[SubjectsColumns.CLASS_ID] == class_id)
        for row in controller.read_tab(TAB_SUBJECTS)[1:]
    )
    if not subject_valid:
        return _response(False, "Subject not found for the selected class.")

    assignment_id = controller.generate_next_id("A", TAB_TEACHER_ASSIGNMENTS, TeacherAssignmentsColumns.ASSIGNMENT_ID)
    controller.append_row(TAB_TEACHER_ASSIGNMENTS, [assignment_id, teacher_id, school_id, class_id, subject_id])
    return _response(True, "Teacher assigned successfully.", {"assignment_id": assignment_id})


def deassign_teacher(principal_id: str, assignment_id: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check

    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")

    controller = get_controller()
    rows = controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
    for idx, row in enumerate(rows[1:], start=2):
        aid = row[TeacherAssignmentsColumns.ASSIGNMENT_ID] if TeacherAssignmentsColumns.ASSIGNMENT_ID < len(row) else ""
        sid = row[TeacherAssignmentsColumns.SCHOOL_ID] if TeacherAssignmentsColumns.SCHOOL_ID < len(row) else ""
        if aid == assignment_id and sid == school_id:
            controller.delete_row(TAB_TEACHER_ASSIGNMENTS, idx)
            return _response(True, "Assignment removed successfully.", {"assignment_id": assignment_id})
    return _response(False, "Assignment not found in your school.")


def get_all_schools() -> Dict[str, Any]:
    controller = get_controller()
    rows = controller.read_tab(TAB_SCHOOLS)
    schools = []
    for row in rows[1:]:
        schools.append(
            {
                "school_id": row[SchoolsColumns.SCHOOL_ID] if SchoolsColumns.SCHOOL_ID < len(row) else "",
                "school_name": row[SchoolsColumns.SCHOOL_NAME] if SchoolsColumns.SCHOOL_NAME < len(row) else "",
            }
        )
    return _response(True, "Schools fetched successfully.", {"schools": schools})


def get_principal_school(principal_id: str) -> Dict[str, Any]:
    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")
    return _response(
        True,
        "Principal school fetched successfully.",
        {"school_id": school_id, "school_name": _get_school_name(school_id)},
    )


def get_school_classes(school_id: str) -> Dict[str, Any]:
    controller = get_controller()
    rows = controller.read_tab(TAB_CLASSES)
    classes = []
    for row in rows[1:]:
        sid = row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(row) else ""
        if sid != school_id:
            continue
        classes.append(
            {
                "class_id": row[ClassesColumns.CLASS_ID] if ClassesColumns.CLASS_ID < len(row) else "",
                "class_name": row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(row) else "",
                "class_section": row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(row) else "",
            }
        )
    return _response(True, "Classes fetched successfully.", {"classes": classes})


def get_school_teachers(school_id: str) -> Dict[str, Any]:
    controller = get_controller()
    teachers_rows = controller.read_tab(TAB_TEACHERS)
    accounts_rows = controller.read_tab(TAB_ACCOUNTS)
    username_by_id = {
        row[AccountsColumns.USER_ID]: row[AccountsColumns.USERNAME]
        for row in accounts_rows[1:]
        if AccountsColumns.USER_ID < len(row) and AccountsColumns.USERNAME < len(row)
    }

    teachers = []
    for row in teachers_rows[1:]:
        sid = row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else ""
        if sid != school_id:
            continue
        teacher_id = row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else ""
        teachers.append({"teacher_id": teacher_id, "username": username_by_id.get(teacher_id, "")})
    return _response(True, "Teachers fetched successfully.", {"teachers": teachers})


def get_school_subjects(school_id: str) -> Dict[str, Any]:
    controller = get_controller()
    class_rows = controller.read_tab(TAB_CLASSES)
    class_ids = {
        row[ClassesColumns.CLASS_ID]
        for row in class_rows[1:]
        if ClassesColumns.CLASS_ID < len(row)
        and ClassesColumns.SCHOOL_ID < len(row)
        and row[ClassesColumns.SCHOOL_ID] == school_id
    }

    subject_rows = controller.read_tab(TAB_SUBJECTS)
    subjects = []
    for row in subject_rows[1:]:
        class_id = row[SubjectsColumns.CLASS_ID] if SubjectsColumns.CLASS_ID < len(row) else ""
        if class_id not in class_ids:
            continue
        subjects.append(
            {
                "subject_id": row[SubjectsColumns.SUBJECT_ID] if SubjectsColumns.SUBJECT_ID < len(row) else "",
                "class_id": class_id,
                "subject_name": row[SubjectsColumns.SUBJECT_NAME] if SubjectsColumns.SUBJECT_NAME < len(row) else "",
            }
        )
    return _response(True, "Subjects fetched successfully.", {"subjects": subjects})


def get_school_assignments(school_id: str) -> Dict[str, Any]:
    controller = get_controller()
    rows = controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
    assignments = []
    for row in rows[1:]:
        sid = row[TeacherAssignmentsColumns.SCHOOL_ID] if TeacherAssignmentsColumns.SCHOOL_ID < len(row) else ""
        if sid != school_id:
            continue
        assignments.append(
            {
                "assignment_id": row[TeacherAssignmentsColumns.ASSIGNMENT_ID] if TeacherAssignmentsColumns.ASSIGNMENT_ID < len(row) else "",
                "teacher_id": row[TeacherAssignmentsColumns.TEACHER_ID] if TeacherAssignmentsColumns.TEACHER_ID < len(row) else "",
                "class_id": row[TeacherAssignmentsColumns.CLASS_ID] if TeacherAssignmentsColumns.CLASS_ID < len(row) else "",
                "subject_id": row[TeacherAssignmentsColumns.SUBJECT_ID] if TeacherAssignmentsColumns.SUBJECT_ID < len(row) else "",
            }
        )
    return _response(True, "Assignments fetched successfully.", {"assignments": assignments})


def get_principals() -> Dict[str, Any]:
    controller = get_controller()
    rows = controller.read_tab(TAB_ACCOUNTS)
    principals = []
    for row in rows[1:]:
        role = row[AccountsColumns.ROLE] if AccountsColumns.ROLE < len(row) else ""
        if role.strip().lower() != "principal":
            continue
        principals.append(
            {
                "principal_id": row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else "",
                "username": row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else "",
                "status": row[AccountsColumns.STATUS] if AccountsColumns.STATUS < len(row) else "",
            }
        )
    return _response(True, "Principals fetched successfully.", {"principals": principals})


def get_sessions() -> Dict[str, Any]:
    controller = get_controller()
    rows = controller.read_tab(TAB_SESSIONS)
    sessions = []
    for row in rows[1:]:
        sessions.append(
            {
                "session_id": row[SessionsColumns.SESSION_ID] if SessionsColumns.SESSION_ID < len(row) else "",
                "session_name": row[SessionsColumns.SESSION_NAME] if SessionsColumns.SESSION_NAME < len(row) else "",
                "is_active": row[SessionsColumns.IS_ACTIVE] if SessionsColumns.IS_ACTIVE < len(row) else "",
                "folder_url": row[SessionsColumns.FOLDER_URL] if SessionsColumns.FOLDER_URL < len(row) else "",
            }
        )
    return _response(True, "Sessions fetched successfully.", {"sessions": sessions})


def get_active_session() -> Dict[str, Any]:
    sessions_response = get_sessions()
    if not sessions_response.get("success"):
        return sessions_response

    sessions = sessions_response.get("data", {}).get("sessions", [])
    for session in sessions:
        if _is_active(str(session.get("is_active", ""))):
            return _response(True, "Active session fetched successfully.", {"session": session})
    return _response(False, "No active session found.")


def get_all_school_analytics(admin_id: str) -> Dict[str, Any]:
    auth_check = _require_role(admin_id, "admin")
    if not auth_check.get("success"):
        return auth_check
    analytics = get_school_analytics_service().get_dashboard_analytics(tab_name="Performance")
    return analytics


def get_school_analytics_for_principal(principal_id: str) -> Dict[str, Any]:
    auth_check = _require_role(principal_id, "principal")
    if not auth_check.get("success"):
        return auth_check
    school_id = _get_principal_school_id(principal_id)
    if not school_id:
        return _response(False, "Principal is not assigned to any school.")
    analytics = get_school_analytics_service().get_dashboard_analytics(tab_name="Performance")
    if not analytics.get("success"):
        return analytics
    payload = analytics.get("data", {})
    return _response(
        True,
        "School analytics fetched successfully.",
        {
            "school_id": school_id,
            "school_name": _get_school_name(school_id),
            **payload,
        },
    )


def get_school_analytics(principal_id: str) -> Dict[str, Any]:
    return get_school_analytics_for_principal(principal_id)


def get_school_analytics_for_teacher(teacher_id: str) -> Dict[str, Any]:
    auth_check = _require_role(teacher_id, "teacher")
    if not auth_check.get("success"):
        return auth_check

    school_id = _get_teacher_school_id(teacher_id)
    if not school_id:
        return _response(False, "Teacher is not assigned to any school.")

    analytics = get_school_analytics_service().get_dashboard_analytics(tab_name="Performance")
    if not analytics.get("success"):
        return analytics

    payload = analytics.get("data", {})
    return _response(
        True,
        "School analytics fetched successfully.",
        {
            "school_id": school_id,
            "school_name": _get_school_name(school_id),
            **payload,
        },
    )
