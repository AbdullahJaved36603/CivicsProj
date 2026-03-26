from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from system_admin.principal_manager import get_principal_manager
from system_admin.school_analytics import get_school_analytics
from system_admin.session_manager import get_session_manager
from system_admin.super_user_dashboard import get_super_user_dashboard
from system_admin.google_sheets_controller import get_controller

try:
    import relational_fernet
except Exception:
    relational_fernet = None


TAB_ACCOUNTS = "Accounts"
TAB_SESSIONS = "Sessions"
TAB_SCHOOLS = "Schools"
TAB_PRINCIPAL_ASSIGNMENTS = "principal_assignments"
TAB_TEACHERS = "teachers"


class AccountsColumns:
    USER_ID = 0
    USERNAME = 1
    PASSWORD = 2
    ROLE = 3
    STATUS = 4


class SessionsColumns:
    SESSION_ID = 0
    SESSION_NAME = 1
    IS_ACTIVE = 2


class SchoolsColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1


class PrincipalAssignmentColumns:
    PRINCIPAL_ID = 0
    SCHOOL_ID = 1


class TeachersColumns:
    TEACHER_ID = 0
    SCHOOL_ID = 1


def _is_active(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "active"}


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized in {"admin", "super_user", "superuser", "super user"}:
        return "admin"
    if normalized == "principal":
        return "principal"
    if normalized == "teacher":
        return "teacher"
    return normalized


def _decrypt_password(encrypted_password: str) -> Optional[str]:
    if not encrypted_password:
        return None
    if relational_fernet is None:
        return None
    fernet = getattr(relational_fernet, "relational_fernet", None)
    if fernet is None:
        return None
    try:
        return fernet.decrypt(encrypted_password.encode()).decode()
    except Exception:
        return None


def _get_school_name(controller: Any, school_id: str) -> str:
    schools_rows = controller.read_tab(TAB_SCHOOLS)
    for row in schools_rows[1:]:
        if SchoolsColumns.SCHOOL_ID < len(row) and row[SchoolsColumns.SCHOOL_ID] == school_id:
            if SchoolsColumns.SCHOOL_NAME < len(row):
                return row[SchoolsColumns.SCHOOL_NAME]
            break
    return ""


def _get_principal_school(controller: Any, principal_id: str) -> Tuple[str, str]:
    rows = controller.read_tab(TAB_PRINCIPAL_ASSIGNMENTS)
    for row in rows[1:]:
        if PrincipalAssignmentColumns.PRINCIPAL_ID < len(row) and row[PrincipalAssignmentColumns.PRINCIPAL_ID] == principal_id:
            school_id = row[PrincipalAssignmentColumns.SCHOOL_ID] if PrincipalAssignmentColumns.SCHOOL_ID < len(row) else ""
            school_name = _get_school_name(controller, school_id) if school_id else ""
            return school_id, school_name
    return "", ""


def _get_teacher_school(controller: Any, teacher_id: str) -> Tuple[str, str]:
    rows = controller.read_tab(TAB_TEACHERS)
    for row in rows[1:]:
        if TeachersColumns.TEACHER_ID < len(row) and row[TeachersColumns.TEACHER_ID] == teacher_id:
            school_id = row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else ""
            school_name = _get_school_name(controller, school_id) if school_id else ""
            return school_id, school_name
    return "", ""


def _active_session(controller: Any) -> Dict[str, str]:
    rows = controller.read_tab(TAB_SESSIONS)
    for row in rows[1:]:
        is_active = row[SessionsColumns.IS_ACTIVE] if SessionsColumns.IS_ACTIVE < len(row) else ""
        if _is_active(is_active):
            return {
                "session_id": row[SessionsColumns.SESSION_ID] if SessionsColumns.SESSION_ID < len(row) else "",
                "session_name": row[SessionsColumns.SESSION_NAME] if SessionsColumns.SESSION_NAME < len(row) else "",
            }
    return {}


def _authenticate_user(username: str, password: str) -> Dict[str, Any]:
    controller = get_controller()

    normalized_username = username.strip().lower()
    if not normalized_username:
        return {"success": False, "message": "Username is required."}
    if not password.strip():
        return {"success": False, "message": "Password is required."}

    try:
        accounts_rows = controller.read_tab(TAB_ACCOUNTS)
    except Exception as exc:
        return {"success": False, "message": f"Unable to read Accounts sheet: {exc}"}

    for row in accounts_rows[1:]:
        row_username = row[AccountsColumns.USERNAME].strip().lower() if AccountsColumns.USERNAME < len(row) else ""
        if row_username != normalized_username:
            continue

        status = row[AccountsColumns.STATUS] if AccountsColumns.STATUS < len(row) else ""
        if not _is_active(status):
            return {"success": False, "message": "Account is not active."}

        encrypted_password = row[AccountsColumns.PASSWORD] if AccountsColumns.PASSWORD < len(row) else ""
        resolved_password = _decrypt_password(encrypted_password)
        if resolved_password is None:
            return {
                "success": False,
                "message": "Password decryption is unavailable. Check Fernet setup.",
            }

        if resolved_password != password:
            return {"success": False, "message": "Invalid username or password."}

        user_id = row[AccountsColumns.USER_ID] if AccountsColumns.USER_ID < len(row) else ""
        role = row[AccountsColumns.ROLE] if AccountsColumns.ROLE < len(row) else ""
        normalized_role = _normalize_role(role)

        school_id = ""
        school_name = ""
        if normalized_role == "principal":
            school_id, school_name = _get_principal_school(controller, user_id)
        elif normalized_role == "teacher":
            school_id, school_name = _get_teacher_school(controller, user_id)

        return {
            "success": True,
            "message": "Login successful.",
            "user": {
                "user_id": user_id,
                "username": row[AccountsColumns.USERNAME] if AccountsColumns.USERNAME < len(row) else "",
                "role": normalized_role,
                "school_id": school_id,
                "school_name": school_name,
            },
        }

    return {"success": False, "message": "Invalid username or password."}


def _render_response(response: Dict[str, Any]) -> None:
    if response.get("success"):
        st.success(response.get("message", "Operation completed."))
        if response.get("data") is not None:
            st.json(response["data"])
    else:
        st.error(response.get("message", "Operation failed."))
        if response.get("data") is not None:
            st.json(response["data"])


def _render_admin_dashboard() -> None:
    controller = get_controller()
    super_user = get_super_user_dashboard()
    principal_manager = get_principal_manager()
    session_manager = get_session_manager()

    st.subheader("Admin Dashboard")
    stats = super_user.get_global_stats()
    _render_response(stats)

    st.divider()
    st.markdown("### School Management")
    create_school_name = st.text_input("School name", key="admin_create_school_name")
    if st.button("Create School", key="admin_create_school_btn"):
        result = super_user.create_school(create_school_name)
        _render_response(result)

    delete_school_id = st.text_input("School ID to delete", key="admin_delete_school_id")
    if st.button("Delete School", key="admin_delete_school_btn"):
        result = super_user.delete_school(delete_school_id)
        _render_response(result)

    st.divider()
    st.markdown("### Session Management")
    session_name = st.text_input("New session name", key="admin_session_name")
    if st.button("Create Session", key="admin_create_session_btn"):
        result = super_user.create_session(session_name)
        _render_response(result)

    session_id_to_activate = st.text_input("Session ID to activate", key="admin_activate_session_id")
    if st.button("Activate Session", key="admin_activate_session_btn"):
        result = session_manager.activate_session(session_id_to_activate)
        _render_response(result)

    st.divider()
    st.markdown("### Principal Management")
    principal_username = st.text_input("Principal username", key="admin_principal_username")
    if st.button("Create Principal Account", key="admin_create_principal_btn"):
        result = principal_manager.create_principal(principal_username)
        _render_response(result)

    principal_id = st.text_input("Principal ID", key="admin_assign_principal_id")
    principal_school_id = st.text_input("School ID", key="admin_assign_principal_school")
    if st.button("Assign Principal to School", key="admin_assign_principal_btn"):
        result = principal_manager.assign_principal_to_school(principal_id, principal_school_id)
        _render_response(result)

    st.divider()
    st.markdown("### Quick Data Preview")
    preview_tab = st.selectbox(
        "Select tab",
        [TAB_ACCOUNTS, TAB_SESSIONS, TAB_SCHOOLS, TAB_PRINCIPAL_ASSIGNMENTS, TAB_TEACHERS],
        key="admin_preview_tab",
    )
    if st.button("Refresh Tab Data", key="admin_refresh_tab_btn"):
        rows = controller.read_tab(preview_tab, force_refresh=True)
        st.write(rows)
    else:
        rows = controller.read_tab(preview_tab)
        st.write(rows)


def _render_principal_dashboard(user: Dict[str, Any]) -> None:
    controller = get_controller()
    analytics = get_school_analytics()

    st.subheader("Principal Dashboard")
    st.info(f"Principal: {user.get('username', '')}")
    st.write(
        {
            "school_id": user.get("school_id", ""),
            "school_name": user.get("school_name", ""),
            "active_session": _active_session(controller),
        }
    )

    analytics_result = analytics.get_dashboard_analytics(tab_name="Performance")
    _render_response(analytics_result)


def _render_teacher_dashboard(user: Dict[str, Any]) -> None:
    controller = get_controller()
    analytics = get_school_analytics()

    st.subheader("Teacher Dashboard")
    st.info(f"Teacher: {user.get('username', '')}")
    st.write(
        {
            "school_id": user.get("school_id", ""),
            "school_name": user.get("school_name", ""),
            "active_session": _active_session(controller),
        }
    )

    class_avg = analytics.get_average_marks_per_class(tab_name="Performance")
    subject_avg = analytics.get_average_marks_per_subject(tab_name="Performance")
    _render_response(class_avg)
    _render_response(subject_avg)


def _render_role_dashboard(user: Dict[str, Any]) -> None:
    role = user.get("role", "")
    if role == "admin":
        _render_admin_dashboard()
        return
    if role == "principal":
        _render_principal_dashboard(user)
        return
    if role == "teacher":
        _render_teacher_dashboard(user)
        return

    st.warning(f"Role '{role}' is not supported in this dashboard yet.")


def _render_login() -> None:
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In")

    if submitted:
        result = _authenticate_user(username, password)
        if result.get("success"):
            st.session_state["authenticated"] = True
            st.session_state["user"] = result["user"]
            st.success("Login successful.")
            st.rerun()
        else:
            st.error(result.get("message", "Login failed."))


def _render_app() -> None:
    st.set_page_config(page_title="School Management Dashboard", layout="wide")
    st.title("School Management System")

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if "user" not in st.session_state:
        st.session_state["user"] = {}

    if not st.session_state["authenticated"]:
        _render_login()
        return

    user: Dict[str, Any] = st.session_state["user"]
    with st.sidebar:
        st.write("Logged in as:")
        st.write(user.get("username", ""))
        st.write(f"Role: {user.get('role', '')}")
        if st.button("Logout"):
            st.session_state["authenticated"] = False
            st.session_state["user"] = {}
            st.rerun()

    _render_role_dashboard(user)


if __name__ == "__main__":
    _render_app()
