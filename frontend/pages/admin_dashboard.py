from __future__ import annotations

from io import BytesIO
from typing import Any, Callable, Dict, List, Tuple

import pandas as pd
import streamlit as st

from frontend.components.forms import build_option_map, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload
from frontend.ui_theme import card, controls_disabled, ensure_page_config, pill_select, render_page_header, show_loading
from system_admin import service_layer
from system_admin.google_sheets_utils import safe_sheet_read


def _safe_backend_call(api_func: Callable[[], Dict[str, Any]], spinner_text: str) -> Dict[str, Any]:
    if controls_disabled():
        return {"success": False, "message": "Please wait, loading data..."}

    try:
        with show_loading(spinner_text):
            response = safe_sheet_read(api_func, retries=3, delay_seconds=1.0)
        if isinstance(response, dict):
            return response
        return {"success": False, "message": "Unexpected server response."}
    except Exception:
        return {
            "success": False,
            "message": "Network issue while fetching data. Please wait and try again.",
        }


def _cached_read(cache_key: str, fetch_func: Callable[[], Dict[str, Any]], data_key: str, spinner_text: str) -> List[Dict[str, Any]]:
    if cache_key in st.session_state:
        return list(st.session_state.get(cache_key, []))

    response = _safe_backend_call(fetch_func, spinner_text)
    if not response.get("success"):
        st.session_state[cache_key] = []
        return []

    rows = response.get("data", {}).get(data_key, [])
    st.session_state[cache_key] = rows
    return list(rows)


def _invalidate_admin_cache() -> None:
    keys = [
        "admin_all_schools",
        "admin_sessions",
        "admin_principals",
        "admin_exam_sessions",
    ]
    for key in list(st.session_state.keys()):
        if key in keys or key.startswith("admin_schools::"):
            st.session_state.pop(key, None)


def _schools(session_id: str = "") -> List[Dict[str, Any]]:
    cache_key = "admin_all_schools" if not session_id else f"admin_schools::{session_id}"
    return _cached_read(
        cache_key=cache_key,
        fetch_func=lambda: service_layer.get_all_schools(session_id=session_id),
        data_key="schools",
        spinner_text="Loading schools...",
    )


def _principals() -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key="admin_principals",
        fetch_func=service_layer.get_principals,
        data_key="principals",
        spinner_text="Loading principals...",
    )


def _sessions() -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key="admin_sessions",
        fetch_func=service_layer.get_sessions,
        data_key="sessions",
        spinner_text="Loading sessions...",
    )


def _session_selector() -> Tuple[str, Dict[str, str]]:
    sessions = _sessions()
    session_map = build_option_map(sessions, "session_id", "session_name")

    if not session_map:
        st.warning("No sessions available.")
        st.session_state["selected_session_id"] = ""
        return "", session_map

    labels = list(session_map.keys())
    selected_session_id = str(st.session_state.get("selected_session_id", "")).strip()

    default_index = 0
    if selected_session_id:
        for idx, label in enumerate(labels):
            if get_select_value(session_map, label) == selected_session_id:
                default_index = idx
                break

    selected_label = pill_select(
        "Session Context",
        labels,
        key="admin_selected_session_label",
        default_index=default_index,
        disabled=controls_disabled(),
    )

    selected_session_id = get_select_value(session_map, selected_label)
    st.session_state["selected_session_id"] = selected_session_id
    return selected_session_id, session_map


def _render_school_management(admin_id: str, selected_session_id: str) -> None:
    with card("School Management", "Create, delete, and review schools in the selected session"):
        if not selected_session_id:
            st.warning("Select a session to manage schools.")
            return

        with st.form("create_school_form"):
            school_name = st.text_input("School name", disabled=controls_disabled())
            submitted = st.form_submit_button("Create School", use_container_width=True, disabled=controls_disabled())
        if submitted:
            response = _safe_backend_call(
                lambda: service_layer.create_school(admin_id, school_name, selected_session_id),
                "Creating school...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_admin_cache()

        schools = _schools(selected_session_id)
        school_map = build_option_map(schools, "school_id", "school_name")
        if school_map:
            with st.form("delete_school_form"):
                selected = st.selectbox("School", list(school_map.keys()), disabled=controls_disabled())
                submitted = st.form_submit_button("Delete School", use_container_width=True, disabled=controls_disabled())
            if submitted:
                school_id = get_select_value(school_map, selected)
                response = _safe_backend_call(
                    lambda: service_layer.delete_school(admin_id, school_id, selected_session_id),
                    "Deleting school...",
                )
                show_form_result(response)
                show_response_payload(response)
                if response.get("success"):
                    _invalidate_admin_cache()
        else:
            st.info("No schools available for deletion.")

        show_records("Schools", schools)


def _render_session_management(admin_id: str, selected_session_id: str) -> None:
    with card("Session Management", "Create session cycles and exam sessions"):
        with st.form("create_session_form"):
            session_name = st.text_input("Session name", disabled=controls_disabled())
            copy_previous = st.checkbox(
                "Copy schools and teachers from previous session",
                disabled=controls_disabled(),
            )
            submitted = st.form_submit_button("Create Session", use_container_width=True, disabled=controls_disabled())
        if submitted:
            response = _safe_backend_call(
                lambda: service_layer.create_session(admin_id, session_name, copy_previous=copy_previous),
                "Creating session...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_admin_cache()

        sessions = _sessions()
        session_map = build_option_map(sessions, "session_id", "session_name")

        if session_map:
            with st.form("create_exam_session_form"):
                selected_session = st.selectbox("Parent session", list(session_map.keys()), disabled=controls_disabled())
                month = st.text_input("Exam month", disabled=controls_disabled())
                submitted = st.form_submit_button("Create Exam Session", use_container_width=True, disabled=controls_disabled())
            if submitted:
                session_id = get_select_value(session_map, selected_session)
                response = _safe_backend_call(
                    lambda: service_layer.create_exam_session(admin_id, session_id, month),
                    "Creating exam session...",
                )
                show_form_result(response)
                show_response_payload(response)
                if response.get("success"):
                    _invalidate_admin_cache()
        else:
            st.info("Create a session before creating exam sessions.")

        exam_sessions_response = _safe_backend_call(
            lambda: service_layer.get_exam_sessions(selected_session_id),
            "Loading exam sessions...",
        )
        exam_sessions = (
            exam_sessions_response.get("data", {}).get("exam_sessions", [])
            if exam_sessions_response.get("success")
            else []
        )
        show_records("Exam Sessions", exam_sessions)

        if session_map:
            col1, col2 = st.columns(2)
            with col1:
                with st.form("activate_session_form"):
                    selected = st.selectbox(
                        "Session to activate",
                        list(session_map.keys()),
                        key="activate_session_select",
                        disabled=controls_disabled(),
                    )
                    submitted = st.form_submit_button("Activate Session", use_container_width=True, disabled=controls_disabled())
                if submitted:
                    session_id = get_select_value(session_map, selected)
                    response = _safe_backend_call(
                        lambda: service_layer.activate_session(admin_id, session_id),
                        "Activating session...",
                    )
                    show_form_result(response)
                    show_response_payload(response)
                    if response.get("success"):
                        _invalidate_admin_cache()

            with col2:
                with st.form("deactivate_session_form"):
                    selected = st.selectbox(
                        "Session to deactivate",
                        list(session_map.keys()),
                        key="deactivate_session_select",
                        disabled=controls_disabled(),
                    )
                    submitted = st.form_submit_button("Deactivate Session", use_container_width=True, disabled=controls_disabled())
                if submitted:
                    session_id = get_select_value(session_map, selected)
                    response = _safe_backend_call(
                        lambda: service_layer.deactivate_session(admin_id, session_id),
                        "Deactivating session...",
                    )
                    show_form_result(response)
                    show_response_payload(response)
                    if response.get("success"):
                        _invalidate_admin_cache()
        else:
            st.info("No sessions available.")

        show_records("Sessions", sessions)


def _render_principal_management(admin_id: str, selected_session_id: str) -> None:
    with card("Principal Management", "Create, assign, deassign, and deactivate principals"):
        if not selected_session_id:
            st.warning("Select a session to manage principal assignments.")
            return

        with st.form("create_principal_form"):
            username = st.text_input("Principal username", disabled=controls_disabled())
            submitted = st.form_submit_button("Create Principal", use_container_width=True, disabled=controls_disabled())
        if submitted:
            if not username.strip():
                st.error("Username cannot be empty")
                st.stop()
            response = _safe_backend_call(
                lambda: service_layer.create_principal(admin_id, username),
                "Creating principal...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_admin_cache()

        principals = _principals()
        schools = _schools(selected_session_id)
        principal_map = build_option_map(principals, "principal_id", "username")
        school_map = build_option_map(schools, "school_id", "school_name")

        assignments: List[Dict[str, Any]] = []
        for principal in principals:
            principal_id = str(principal.get("principal_id", ""))
            principal_username = str(principal.get("username", ""))
            assigned_schools = principal.get("assigned_schools", []) or []
            for school in assigned_schools:
                session_id = str(school.get("session_id", ""))
                if selected_session_id and session_id != selected_session_id:
                    continue
                assignments.append(
                    {
                        "label": f"{principal_username} -> {school.get('school_name', '')}",
                        "principal_id": principal_id,
                        "principal_username": principal_username,
                        "school_id": school.get("school_id", ""),
                        "school_name": school.get("school_name", ""),
                        "session_id": session_id,
                    }
                )

        if principal_map and school_map:
            with st.form("assign_principal_form"):
                selected_principal = st.selectbox("Principal", list(principal_map.keys()), disabled=controls_disabled())
                selected_school = st.selectbox("School", list(school_map.keys()), disabled=controls_disabled())
                replace_existing = st.checkbox(
                    "Replace existing principal if already assigned",
                    disabled=controls_disabled(),
                )
                submitted = st.form_submit_button("Assign Principal", use_container_width=True, disabled=controls_disabled())
            if submitted:
                principal_id = get_select_value(principal_map, selected_principal)
                school_id = get_select_value(school_map, selected_school)
                response = _safe_backend_call(
                    lambda: service_layer.assign_principal(
                        admin_id,
                        principal_id,
                        school_id,
                        replace_existing=replace_existing,
                    ),
                    "Assigning principal...",
                )
                show_form_result(response)
                show_response_payload(response)
                if response.get("success"):
                    _invalidate_admin_cache()
        else:
            st.info("Principal assignment requires at least one principal and one school.")

        if principal_map:
            col1, col2 = st.columns(2)
            with col1:
                assignment_map = build_option_map(assignments, "label", "label")
                if assignment_map:
                    with st.form("deassign_principal_form"):
                        selected_assignment = st.selectbox(
                            "Assignment to deassign",
                            list(assignment_map.keys()),
                            key="deassign_principal_select",
                            disabled=controls_disabled(),
                        )
                        submitted = st.form_submit_button("Deassign Principal", use_container_width=True, disabled=controls_disabled())
                    if submitted:
                        selected_label = get_select_value(assignment_map, selected_assignment)
                        selected_row = next(
                            (item for item in assignments if str(item.get("label", "")) == selected_label),
                            {},
                        )
                        principal_id = str(selected_row.get("principal_id", ""))
                        school_id = str(selected_row.get("school_id", ""))
                        response = _safe_backend_call(
                            lambda: service_layer.deassign_principal(admin_id, principal_id, school_id),
                            "Deassigning principal...",
                        )
                        show_form_result(response)
                        show_response_payload(response)
                        if response.get("success"):
                            _invalidate_admin_cache()
                else:
                    st.info("No principal assignments found in selected session.")

            with col2:
                with st.form("deactivate_principal_form"):
                    selected_principal = st.selectbox(
                        "Principal to deactivate",
                        list(principal_map.keys()),
                        key="deactivate_principal_select",
                        disabled=controls_disabled(),
                    )
                    submitted = st.form_submit_button("Deactivate Principal", use_container_width=True, disabled=controls_disabled())
                if submitted:
                    principal_id = get_select_value(principal_map, selected_principal)
                    response = _safe_backend_call(
                        lambda: service_layer.deactivate_principal(admin_id, principal_id),
                        "Deactivating principal...",
                    )
                    show_form_result(response)
                    show_response_payload(response)
                    if response.get("success"):
                        _invalidate_admin_cache()
        else:
            st.info("No principals available.")

        show_records("Principal Assignments", assignments)
        show_records("Principals", principals)


def _safe_excel_sheet_name(base_name: str, used: set[str]) -> str:
    sanitized = "".join(ch for ch in str(base_name) if ch not in "[]:*?/\\").strip()
    if not sanitized:
        sanitized = "Sheet"

    candidate = sanitized[:31]
    counter = 1
    while candidate in used:
        suffix = f"_{counter}"
        candidate = f"{sanitized[: max(1, 31 - len(suffix))]}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def _build_admin_analytics_workbook(sections: List[str], export_sheets: Dict[str, List[Dict[str, Any]]]) -> Tuple[bytes | None, str | None]:
    engine_candidates = ["xlsxwriter", "openpyxl", None]
    last_error: str | None = None

    for engine in engine_candidates:
        try:
            buffer = BytesIO()
            used_sheet_names: set[str] = set()
            writer_kwargs = {"engine": engine} if engine else {}
            with pd.ExcelWriter(buffer, **writer_kwargs) as writer:
                for section in sections:
                    section_rows = export_sheets.get(section, [])
                    if section_rows:
                        section_df = pd.DataFrame(section_rows)
                    else:
                        section_df = pd.DataFrame(
                            [
                                {
                                    "School": "No data available",
                                    "Subject": "No data available",
                                    "Teacher": "-",
                                    "Total": 0,
                                    "Appeared": 0,
                                    "Absent": 0,
                                    "Passed": 0,
                                    "Failed": 0,
                                    "Pass %": 0.0,
                                    "Fail %": 0.0,
                                }
                            ]
                        )

                    ordered_export_cols = [
                        "School",
                        "Subject",
                        "Teacher",
                        "Total",
                        "Appeared",
                        "Absent",
                        "Passed",
                        "Failed",
                        "Pass %",
                        "Fail %",
                    ]
                    export_columns = [col for col in ordered_export_cols if col in section_df.columns]
                    section_df = section_df[export_columns] if export_columns else section_df

                    sheet_name = _safe_excel_sheet_name(str(section), used_sheet_names)
                    section_df.to_excel(writer, sheet_name=sheet_name, index=False)

            return buffer.getvalue(), None
        except (ImportError, ModuleNotFoundError, ValueError) as exc:
            last_error = str(exc)

    return None, last_error


def _render_global_analytics(admin_id: str, selected_session_id: str) -> None:
    with card("Global Analytics", "Hierarchical class-section analytics grouped by school"):
        if not selected_session_id:
            st.warning("Select a session to view analytics.")
            return

        exam_sessions_response = _safe_backend_call(
            lambda: service_layer.get_exam_sessions(selected_session_id),
            "Loading exam sessions...",
        )
        if not exam_sessions_response.get("success"):
            show_form_result(exam_sessions_response)
            return

        exam_sessions = exam_sessions_response.get("data", {}).get("exam_sessions", [])
        exam_session_map = build_option_map(exam_sessions, "exam_session_id", "month")
        if not exam_session_map:
            st.info("No exam sessions found for selected session.")
            return

        exam_labels = list(exam_session_map.keys())
        selected_exam_label = st.selectbox(
            "Exam Session",
            exam_labels,
            key="admin_hier_exam_session",
            disabled=controls_disabled(),
        )
        selected_exam_session_id = get_select_value(exam_session_map, selected_exam_label)

        class_options_response = _safe_backend_call(
            lambda: service_layer.get_admin_class_hierarchical_analytics(
                admin_id,
                selected_session_id,
                selected_exam_session_id,
                "",
            ),
            "Loading classes...",
        )
        if not class_options_response.get("success"):
            show_form_result(class_options_response)
            return

        class_names = class_options_response.get("data", {}).get("class_names", [])
        if not class_names:
            st.info("No classes available for selected exam session.")
            return

        selected_class_name = st.selectbox(
            "Class",
            class_names,
            key="admin_hier_class_name",
            disabled=controls_disabled(),
        )

        analytics_response = _safe_backend_call(
            lambda: service_layer.get_admin_class_hierarchical_analytics(
                admin_id,
                selected_session_id,
                selected_exam_session_id,
                selected_class_name,
            ),
            "Loading hierarchical analytics...",
        )
        show_form_result(analytics_response)
        if not analytics_response.get("success"):
            return

        payload = analytics_response.get("data", {})
        summary = payload.get("summary", {})

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Students", int(summary.get("total_students", 0)))
        with col2:
            st.metric("Passed", int(summary.get("passed_students", 0)))
        with col3:
            st.metric("Failed", int(summary.get("failed_students", 0)))
        with col4:
            st.metric("Absent", int(summary.get("absent_students", 0)))

        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Appeared", int(summary.get("appeared_students", 0)))
        with col6:
            st.metric("Pass %", float(summary.get("pass_percentage", 0.0)))
        with col7:
            st.metric("Fail %", float(summary.get("fail_percentage", 0.0)))

        grouped_rows = payload.get("grouped_rows", [])
        if grouped_rows:
            grouped_df = pd.DataFrame(grouped_rows)
            ordered_columns = [
                "School",
                "Class",
                "Section",
                "Subject",
                "Teacher",
                "Total Students",
                "Appeared",
                "Absent",
                "Passed",
                "Failed",
                "Pass %",
                "Fail %",
            ]
            available_columns = [column for column in ordered_columns if column in grouped_df.columns]
            grouped_df = grouped_df[available_columns] if available_columns else grouped_df
            st.dataframe(grouped_df, use_container_width=True)
        else:
            st.info("No analytics rows found for selected filters.")

        export_sheets = payload.get("export_sheets", {})
        sections = payload.get("sections", [])
        if not sections:
            sections = sorted(export_sheets.keys())

        if sections:
            workbook_bytes, error_message = _build_admin_analytics_workbook(sections, export_sheets)
            if workbook_bytes is None:
                st.error("Unable to generate Excel report. Please install 'xlsxwriter' or 'openpyxl' in deployment.")
                if error_message:
                    st.caption(f"Export engine error: {error_message}")
                return

            st.download_button(
                label="Download Analytics Report",
                data=workbook_bytes,
                file_name="admin_class_analytics.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=controls_disabled(),
            )


def render_admin_page(selected_page: str, admin_id: str) -> None:
    ensure_page_config()

    if controls_disabled():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Admin Dashboard", "Manage sessions, schools, principals, and system structure")

    with card("Session Context", "Choose which session your admin actions should target"):
        selected_session_id, _ = _session_selector()

    normalized_page = str(selected_page).strip().casefold()

    if normalized_page == "school management":
        _render_school_management(admin_id, selected_session_id)
        return
    if normalized_page == "session management":
        _render_session_management(admin_id, selected_session_id)
        return
    if normalized_page == "principal management":
        _render_principal_management(admin_id, selected_session_id)
        return
    if normalized_page in {"global analytics", "analytics"}:
        _render_global_analytics(admin_id, selected_session_id)
        return

    st.error("Access denied")
