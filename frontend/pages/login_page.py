from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from system_admin import auth_utils


def _normalize_role(raw_role: str) -> str:
    role = raw_role.strip().lower()
    if role in {"super_user", "superuser"}:
        return "admin"
    return role


def render_login_page() -> None:
    st.title("School Management System")
    st.subheader("Login")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if not submitted:
        return

    response: Dict[str, Any] = auth_utils.authenticate(username, password)
    if not response.get("success"):
        st.error(response.get("message", "Login failed."))
        return

    data = response.get("data", {})
    user_id = str(data.get("user_id", "")).strip()
    role = _normalize_role(str(data.get("role", "")))
    resolved_username = str(data.get("username", username)).strip()

    if not user_id or not role:
        st.error("Login response is missing user details.")
        return

    st.session_state["is_logged_in"] = True
    st.session_state["user_id"] = user_id
    st.session_state["role"] = role
    st.session_state["username"] = resolved_username
    st.success("Login successful.")
    st.rerun()
