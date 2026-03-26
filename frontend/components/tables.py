from __future__ import annotations

from typing import Any, Dict, Iterable, List

import streamlit as st


def show_response_payload(response: Dict[str, Any]) -> None:
    data = response.get("data")
    if isinstance(data, dict) and data:
        st.json(data)


def show_records(title: str, records: Iterable[Dict[str, Any]]) -> None:
    records_list: List[Dict[str, Any]] = list(records)
    st.markdown(f"#### {title}")
    if not records_list:
        st.info("No data available.")
        return
    st.dataframe(records_list, use_container_width=True)


def show_simple_kv_table(title: str, payload: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    if not payload:
        st.info("No data available.")
        return
    st.table(payload)
