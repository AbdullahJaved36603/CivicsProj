from __future__ import annotations

import os
import sys

import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from frontend.components.sidebar import render_sidebar
from frontend.pages import admin_dashboard, analytics_page, login_page, principal_dashboard, profile_settings, teacher_dashboard
from frontend.ui_theme import apply_theme, init_ui_state


def _init_session_state() -> None:
    defaults = {
        "is_logged_in": False,
        "user_id": "",
        "role": "",
        "username": "",
        "selected_session_id": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    init_ui_state()


def _route_authenticated_user() -> None:
    role = str(st.session_state.get("role", "")).strip().lower()
    user_id = str(st.session_state.get("user_id", "")).strip()
    username = str(st.session_state.get("username", "")).strip()

    selected_page = render_sidebar(role, username)
    if selected_page is None:
        st.error("Access denied")
        return

    normalized_page = str(selected_page).strip().casefold()

    if role in {"admin", "super_user", "superuser"}:
        if normalized_page in {
            "school management",
            "session management",
            "principal management",
            "global analytics",
            "analytics",
        }:
            admin_dashboard.render_admin_page(selected_page, user_id)
            return
        if normalized_page == "profile settings":
            profile_settings.render_profile_settings(user_id, username)
            return
        st.error("Access denied")
        return

    if role == "principal":
        if normalized_page in {
            "class management",
            "subject management",
            "teacher management",
            "assignments",
            "class incharge",
        }:
            principal_dashboard.render_principal_page(selected_page, user_id)
            return
        if normalized_page == "school analytics":
            analytics_page.render_principal_analytics(user_id)
            return
        if normalized_page == "profile settings":
            profile_settings.render_profile_settings(user_id, username)
            return
        st.error("Access denied")
        return

    if role == "teacher":
        if normalized_page in {"student enrollment", "results entry", "school analytics"}:
            teacher_dashboard.render_teacher_page(selected_page, user_id)
            return
        if normalized_page == "profile settings":
            profile_settings.render_profile_settings(user_id, username)
            return
        st.error("Access denied")
        return

    st.error("Access denied")


def main() -> None:
    st.set_page_config(
        layout="wide",
        page_title="School Management System",
        page_icon="🎓",
    )
    _init_session_state()
    apply_theme()

    if not st.session_state.get("is_logged_in", False):
        login_page.render_login_page()
        return

    _route_authenticated_user()


if __name__ == "__main__":
    main()
