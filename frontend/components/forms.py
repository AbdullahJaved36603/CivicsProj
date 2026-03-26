from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

import streamlit as st


def build_option_map(
    items: Iterable[Dict[str, Any]],
    id_key: str,
    name_key: str,
) -> Dict[str, str]:
    option_map: Dict[str, str] = {}
    for item in items:
        item_id = str(item.get(id_key, "")).strip()
        item_name = str(item.get(name_key, "")).strip()
        if not item_id:
            continue
        label = item_name if item_name else item_id
        final_label = f"{label} [{item_id}]"
        option_map[final_label] = item_id
    return option_map


def show_form_result(response: Dict[str, Any]) -> None:
    if response.get("success"):
        st.success(response.get("message", "Operation completed successfully."))
    else:
        st.error(response.get("message", "Operation failed."))


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
