from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from frontend.components.forms import build_option_map, form_heading, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload
from system_admin import service_layer


def _schools() -> List[Dict[str, Any]]:
    response = service_layer.get_all_schools()
    return response.get("data", {}).get("schools", []) if response.get("success") else []


def _principals() -> List[Dict[str, Any]]:
    response = service_layer.get_principals()
    return response.get("data", {}).get("principals", []) if response.get("success") else []


def _sessions() -> List[Dict[str, Any]]:
    response = service_layer.get_sessions()
    return response.get("data", {}).get("sessions", []) if response.get("success") else []


def _active_session() -> Dict[str, Any]:
    response = service_layer.get_active_session()
    if not response.get("success"):
        return {}
    return response.get("data", {}).get("session", {})


def _render_school_management(admin_id: str) -> None:
    form_heading("School Management", "Create and remove schools")

    active_session = _active_session()
    if active_session:
        session_name = str(active_session.get("session_name", ""))
        st.info(f"Active session: {session_name}")
    else:
        st.warning("No active session found. School creation is disabled.")

    with st.form("create_school_form"):
        school_name = st.text_input("School name")
        submitted = st.form_submit_button("Create School", disabled=not bool(active_session))
    if submitted:
        response = service_layer.create_school(admin_id, school_name)
        show_form_result(response)
        show_response_payload(response)

    schools = _schools()
    school_map = build_option_map(schools, "school_id", "school_name")
    if school_map:
        with st.form("delete_school_form"):
            selected = st.selectbox("School", list(school_map.keys()))
            submitted = st.form_submit_button("Delete School")
        if submitted:
            school_id = get_select_value(school_map, selected)
            response = service_layer.delete_school(admin_id, school_id)
            show_form_result(response)
            show_response_payload(response)
    else:
        st.info("No schools available for deletion.")

    show_records("Schools", schools)


def _render_session_management(admin_id: str) -> None:
    form_heading("Session Management", "Create, activate, or deactivate sessions")

    with st.form("create_session_form"):
        session_name = st.text_input("Session name")
        copy_previous = st.checkbox("Copy previous session structure")
        submitted = st.form_submit_button("Create Session")
    if submitted:
        response = service_layer.create_session(admin_id, session_name, copy_previous=copy_previous)
        show_form_result(response)
        show_response_payload(response)

    sessions = _sessions()
    session_map = build_option_map(sessions, "session_id", "session_name")

    if session_map:
        col1, col2 = st.columns(2)
        with col1:
            with st.form("activate_session_form"):
                selected = st.selectbox("Session to activate", list(session_map.keys()), key="activate_session_select")
                submitted = st.form_submit_button("Activate Session")
            if submitted:
                session_id = get_select_value(session_map, selected)
                response = service_layer.activate_session(admin_id, session_id)
                show_form_result(response)
                show_response_payload(response)

        with col2:
            with st.form("deactivate_session_form"):
                selected = st.selectbox("Session to deactivate", list(session_map.keys()), key="deactivate_session_select")
                submitted = st.form_submit_button("Deactivate Session")
            if submitted:
                session_id = get_select_value(session_map, selected)
                response = service_layer.deactivate_session(admin_id, session_id)
                show_form_result(response)
                show_response_payload(response)
    else:
        st.info("No sessions available.")

    show_records("Sessions", sessions)


def _render_principal_management(admin_id: str) -> None:
    form_heading("Principal Management", "Create, assign, deassign, and deactivate principals")

    with st.form("create_principal_form"):
        username = st.text_input("Principal username")
        submitted = st.form_submit_button("Create Principal")
    if submitted:
        if not username.strip():
            st.error("Username cannot be empty")
            st.stop()
        response = service_layer.create_principal(admin_id, username)
        show_form_result(response)
        show_response_payload(response)

    principals = _principals()
    schools = _schools()
    principal_map = build_option_map(principals, "principal_id", "username")
    school_map = build_option_map(schools, "school_id", "school_name")

    if principal_map and school_map:
        with st.form("assign_principal_form"):
            selected_principal = st.selectbox("Principal", list(principal_map.keys()))
            selected_school = st.selectbox("School", list(school_map.keys()))
            submitted = st.form_submit_button("Assign Principal")
        if submitted:
            principal_id = get_select_value(principal_map, selected_principal)
            school_id = get_select_value(school_map, selected_school)
            response = service_layer.assign_principal(admin_id, principal_id, school_id)
            show_form_result(response)
            show_response_payload(response)
    else:
        st.info("Principal assignment requires at least one principal and one school.")

    if principal_map:
        col1, col2 = st.columns(2)
        with col1:
            with st.form("deassign_principal_form"):
                selected_principal = st.selectbox(
                    "Principal to deassign",
                    list(principal_map.keys()),
                    key="deassign_principal_select",
                )
                submitted = st.form_submit_button("Deassign Principal")
            if submitted:
                principal_id = get_select_value(principal_map, selected_principal)
                response = service_layer.deassign_principal(admin_id, principal_id)
                show_form_result(response)
                show_response_payload(response)

        with col2:
            with st.form("deactivate_principal_form"):
                selected_principal = st.selectbox(
                    "Principal to deactivate",
                    list(principal_map.keys()),
                    key="deactivate_principal_select",
                )
                submitted = st.form_submit_button("Deactivate Principal")
            if submitted:
                principal_id = get_select_value(principal_map, selected_principal)
                response = service_layer.deactivate_principal(admin_id, principal_id)
                show_form_result(response)
                show_response_payload(response)
    else:
        st.info("No principals available.")

    show_records("Principals", principals)


def render_admin_page(selected_page: str, admin_id: str) -> None:
    if selected_page == "School Management":
        _render_school_management(admin_id)
        return
    if selected_page == "Session Management":
        _render_session_management(admin_id)
        return
    if selected_page == "Principal Management":
        _render_principal_management(admin_id)
        return

    st.error("Access denied")
