from __future__ import annotations

from typing import Any, Dict, Iterable, List

import pandas as pd
import streamlit as st


def _class_label(record: Dict[str, Any]) -> str:
    class_name = str(record.get("class_name", "")).strip()
    class_section = str(record.get("class_section", "")).strip()
    if class_name and class_section:
        return f"{class_name}{class_section}"
    return class_name


def _sanitize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for row in records:
        cleaned = dict(row)

        if "class_label" not in cleaned and ("class_name" in cleaned or "class_section" in cleaned):
            cleaned["class_label"] = _class_label(cleaned)

        # Hide all internal ID keys from end-user tables.
        id_keys = [key for key in list(cleaned.keys()) if key.endswith("_id")]
        for key in id_keys:
            cleaned.pop(key, None)

        # Avoid exposing raw sheet URLs in UI tables.
        cleaned.pop("school_sheet_url", None)

        sanitized.append(cleaned)
    return sanitized


def _sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            if str(key).endswith("_id"):
                continue
            if key == "school_sheet_url":
                continue
            sanitized[key] = _sanitize_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload]
    return payload


def show_response_payload(response: Dict[str, Any]) -> None:
    data = response.get("data")
    if isinstance(data, dict) and data:
        st.json(_sanitize_payload(data))


def show_records(title: str, records: Iterable[Dict[str, Any]]) -> None:
    records_list: List[Dict[str, Any]] = list(records)
    st.markdown(f"#### {title}")
    if not records_list:
        st.info("No data available.")
        return

    sanitized_rows = _sanitize_records(records_list)
    if not sanitized_rows:
        st.info("No data available.")
        return

    frame = pd.DataFrame(sanitized_rows)
    st.dataframe(frame, use_container_width=True)


def show_simple_kv_table(title: str, payload: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    if not payload:
        st.info("No data available.")
        return

    sanitized_payload = _sanitize_payload(payload)
    if not isinstance(sanitized_payload, dict) or not sanitized_payload:
        st.info("No data available.")
        return

    frame = pd.DataFrame(
        [{"Field": key.replace("_", " ").title(), "Value": value} for key, value in sanitized_payload.items()]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)
