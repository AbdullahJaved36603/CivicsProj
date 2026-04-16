from __future__ import annotations

from typing import Any, Callable, Dict

import streamlit as st

from frontend.components.forms import show_form_result
from frontend.components.tables import show_response_payload
from frontend.ui_theme import (
    card,
    controls_disabled,
    ensure_page_config,
    render_page_header,
    safe_backend_call_with_quota_guard,
)
from system_admin import service_layer


def _safe_backend_call(api_func: Callable[[], Dict[str, Any]], spinner_text: str) -> Dict[str, Any]:
    return safe_backend_call_with_quota_guard(api_func, spinner_text)


def render_profile_settings(user_id: str, current_username: str) -> None:
    ensure_page_config()

    if controls_disabled():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Profile Settings", "Manage your account details and credentials")

    with card("Account", "User profile overview"):
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown("### 👤")
        with col2:
            role_label = str(st.session_state.get("role", "")).strip().title() or "User"
            full_name = current_username
            st.markdown(f"**Username:** {current_username}")
            st.markdown(f"**Full Name:** {full_name}")
            st.markdown(f"**Role:** {role_label}")
            st.caption("Keep your credentials secure and unique.")

    with card("Update Credentials", "Change username and password in a single secure action"):
        with st.form("profile_settings_form"):
            col1, col2 = st.columns(2)
            with col1:
                entered_current_username = st.text_input(
                    "Current username",
                    value=current_username,
                    disabled=controls_disabled(),
                )
                current_password = st.text_input(
                    "Current password",
                    type="password",
                    disabled=controls_disabled(),
                )
            with col2:
                new_username = st.text_input("New username", disabled=controls_disabled())
                new_password = st.text_input(
                    "New password",
                    type="password",
                    disabled=controls_disabled(),
                )

            button_label = "⏳ Updating..." if controls_disabled() else "Update Credentials"
            submitted = st.form_submit_button(
                button_label,
                use_container_width=True,
                disabled=controls_disabled(),
            )

        if not submitted:
            return

        response = _safe_backend_call(
            lambda: service_layer.change_credentials(
                user_id=user_id,
                current_username=entered_current_username,
                current_password=current_password,
                new_username=new_username,
                new_password=new_password,
            ),
            "Updating credentials...",
        )
        show_form_result(response)
        show_response_payload(response)

        if response.get("success"):
            resolved_username = response.get("data", {}).get("username", "")
            if resolved_username:
                st.session_state["username"] = resolved_username
