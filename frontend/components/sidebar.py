from __future__ import annotations

from typing import List, Optional

import streamlit as st


ADMIN_PAGES: List[str] = [
    "School Management",
    "Session Management",
    "Principal Management",
    "Global Analytics",
]

PRINCIPAL_PAGES: List[str] = [
    "Class Management",
    "Subject Management",
    "Teacher Management",
    "Assignments",
    "School Analytics",
]

TEACHER_PAGES: List[str] = ["School Analytics"]


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

    with st.sidebar:
        st.markdown("### Navigation")
        st.caption(f"User: {username}")
        st.caption(f"Role: {role}")
        selected_page = st.radio("Go to", options=available_pages, key="nav_page")

        if st.button("Logout", use_container_width=True):
            for key in ["is_logged_in", "user_id", "role", "username", "nav_page"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    return selected_page
