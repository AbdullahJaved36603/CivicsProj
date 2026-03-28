from __future__ import annotations

from typing import List, Optional

import streamlit as st

from frontend.ui_theme import controls_disabled, render_theme_toggle


ADMIN_PAGES: List[str] = [
    "School Management",
    "Session Management",
    "Principal Management",
    "Global Analytics",
    "Profile Settings",
]

PRINCIPAL_PAGES: List[str] = [
    "Class Management",
    "Subject Management",
    "Teacher Management",
    "Assignments",
    "Class Incharge",
    "School Analytics",
    "Profile Settings",
]

TEACHER_PAGES: List[str] = ["Student Enrollment", "Results Entry", "School Analytics", "Profile Settings"]


def pages_for_role(role: str) -> List[str]:
    normalized_role = role.strip().lower()
    if normalized_role in {"admin", "super_user", "superuser"}:
        return ADMIN_PAGES
    if normalized_role == "principal":
        return PRINCIPAL_PAGES
    if normalized_role == "teacher":
        return TEACHER_PAGES
    return []


def render_sidebar(role: str, username: str) -> Optional[str]:
    available_pages = pages_for_role(role)
    if not available_pages:
        with st.sidebar:
            st.error("Access denied")
        return None

    role_key = str(role).strip().lower()
    if st.session_state.get("nav_role") != role_key:
        st.session_state["nav_role"] = role_key
        st.session_state["nav_page"] = available_pages[0]

    if "nav_page" not in st.session_state or st.session_state.get("nav_page") not in available_pages:
        st.session_state["nav_page"] = available_pages[0]

    is_loading = controls_disabled()

    with st.sidebar:
        st.markdown("### School Management")
        st.caption(f"User: {username}")
        st.caption(f"Role: {role}")
        render_theme_toggle()

        st.markdown("<div class='sms-sidebar-section'>Navigation</div>", unsafe_allow_html=True)
        selected_page = str(st.session_state.get("nav_page", available_pages[0]))
        for index, page in enumerate(available_pages):
            is_active = selected_page == page
            clicked = st.button(
                page,
                key=f"sidebar_nav_{role}_{index}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
                disabled=is_loading,
            )
            if clicked and not is_loading:
                st.session_state["nav_page"] = page
                st.rerun()

        selected_page = str(st.session_state.get("nav_page", available_pages[0]))

        st.markdown("<div class='sms-sidebar-section'>Session</div>", unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True, disabled=is_loading):
            for key in [
                "is_logged_in",
                "user_id",
                "role",
                "username",
                "nav_page",
                "selected_session_id",
                "admin_selected_session_label",
                "theme",
                "is_loading",
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    return selected_page
