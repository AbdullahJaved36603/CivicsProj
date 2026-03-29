from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, Tuple

import streamlit as st


def _sanitize_error_message(message: str) -> str:
    lowered = str(message).lower()
    hidden_tokens = [
        "quota",
        "traceback",
        "exception",
        "invalid jwt",
        "service account",
        "googleapis",
        "httperror",
        "failed:",
    ]
    if any(token in lowered for token in hidden_tokens):
        return "Service is temporarily busy. Please wait a moment and try again."
    return message


def build_option_map(
    items: Iterable[Dict[str, Any]],
    id_key: str,
    name_key: str,
) -> Dict[str, str]:
    option_map: Dict[str, str] = {}
    duplicate_counter: defaultdict[str, int] = defaultdict(int)

    for item in items:
        item_id = str(item.get(id_key, "")).strip()
        item_name = str(item.get(name_key, "")).strip()
        if not item_id:
            continue

        label = item_name if item_name else "Unnamed"
        duplicate_counter[label] += 1
        occurrence = duplicate_counter[label]

        # Keep labels human-readable while preserving uniqueness without exposing IDs.
        final_label = label if occurrence == 1 else f"{label} ({occurrence})"
        option_map[final_label] = item_id
    return option_map


def show_form_result(response: Dict[str, Any]) -> None:
    message = str(response.get("message", "")).strip()
    friendly = (
        message.replace("student_id", "student")
        .replace("teacher_id", "teacher")
        .replace("class_id", "class")
        .replace("school_id", "school")
        .replace("subject_id", "subject")
        .replace("exam_session_id", "exam session")
        .replace("session_id", "session")
    )
    friendly = _sanitize_error_message(friendly)

    if response.get("success"):
        st.success(friendly or "Operation completed successfully.")
    else:
        st.error(friendly or "Operation failed.")


def get_select_value(option_map: Dict[str, str], selected_label: str) -> str:
    return option_map.get(selected_label, "")


def form_heading(title: str, caption: str = "") -> None:
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)


def two_col_text_inputs(label_left: str, label_right: str, key_left: str, key_right: str) -> Tuple[str, str]:
    col1, col2 = st.columns(2)
    with col1:
        left = st.text_input(label_left, key=key_left)
    with col2:
        right = st.text_input(label_right, key=key_right)
    return left, right
