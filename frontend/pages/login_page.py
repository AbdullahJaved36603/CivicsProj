from __future__ import annotations

import time
from typing import Any, Dict

import streamlit as st

from system_admin import auth_utils


def _normalize_role(raw_role: str) -> str:
    role = raw_role.strip().lower()
    if role in {"super_user", "superuser"}:
        return "admin"
    return role


def _friendly_login_message(raw_message: str) -> str:
    message = str(raw_message or "").strip()
    if not message:
        return "Login failed. Please try again."

    safe_messages = {
        "username is required.",
        "password is required.",
        "invalid username or password.",
        "account is not active.",
    }
    if message.lower() in safe_messages:
        return message

    lowered = message.lower()
    hidden_tokens = [
        "quota",
        "rate",
        "jwt",
        "traceback",
        "google",
        "sheets",
        "service account",
        "failed:",
        "exception",
    ]
    if any(token in lowered for token in hidden_tokens):
        return "Login is temporarily unavailable. Please wait a moment and try again."

    return "Login failed. Please try again."


def render_login_page() -> None:
    st.title("School Management System")
    st.subheader("Login")

    if "login_in_progress" not in st.session_state:
        st.session_state["login_in_progress"] = False
    if "last_login_attempt_at" not in st.session_state:
        st.session_state["last_login_attempt_at"] = 0.0
    if "last_login_attempt_signature" not in st.session_state:
        st.session_state["last_login_attempt_signature"] = ""

    is_login_in_progress = bool(st.session_state.get("login_in_progress", False))

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", disabled=is_login_in_progress)

    if not submitted:
        return

    now_ts = time.time()
    attempt_signature = f"{username.strip().lower()}|{password}"
    last_attempt_ts = float(st.session_state.get("last_login_attempt_at", 0.0) or 0.0)
    last_attempt_signature = str(st.session_state.get("last_login_attempt_signature", ""))

    if is_login_in_progress:
        st.info("Login already in progress. Please wait.")
        return

    if attempt_signature == last_attempt_signature and (now_ts - last_attempt_ts) < 2.0:
        st.info("Please wait before trying again.")
        return

    st.session_state["login_in_progress"] = True
    st.session_state["last_login_attempt_at"] = now_ts
    st.session_state["last_login_attempt_signature"] = attempt_signature

    try:
        response: Dict[str, Any] = auth_utils.authenticate(username, password)
    except Exception:
        response = {"success": False, "message": "Login failed."}
    finally:
        st.session_state["login_in_progress"] = False

    if not response.get("success"):
        st.error(_friendly_login_message(response.get("message", "Login failed.")))
        return

    data = response.get("data", {})
    user_id = str(data.get("user_id", "")).strip()
    role = _normalize_role(str(data.get("role", "")))
    resolved_username = str(data.get("username", username)).strip()

    if not user_id or not role:
        st.error("Login failed. Please try again.")
        return

    st.session_state["is_logged_in"] = True
    st.session_state["user_id"] = user_id
    st.session_state["role"] = role
    st.session_state["username"] = resolved_username
    st.success("Login successful.")
    st.rerun()
