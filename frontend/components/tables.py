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
    def _display_value(value: Any) -> Any:
        if isinstance(value, list):
            if not value:
                return ""
            if all(isinstance(item, dict) for item in value):
                extracted: List[str] = []
                for item in value:
                    school_name = str(item.get("school_name", "")).strip()
                    class_label = str(item.get("class_label", "")).strip()
                    subject_name = str(item.get("subject_name", "")).strip()
                    username = str(item.get("username", "")).strip()
                    principal_name = str(item.get("principal_username", "")).strip()
                    teacher_name = str(item.get("teacher_name", "")).strip()

                    preferred = (
                        school_name
                        or class_label
                        or subject_name
                        or username
                        or principal_name
                        or teacher_name
                    )
                    if preferred:
                        extracted.append(preferred)
                    else:
                        extracted.append(
                            ", ".join(
                                f"{k}: {v}" for k, v in item.items() if not str(k).endswith("_id") and str(v).strip()
                            )
                        )
                extracted = [entry for entry in extracted if entry]
                return ", ".join(extracted)
            return ", ".join(str(item) for item in value)

        if isinstance(value, dict):
            parts = [
                f"{key.replace('_', ' ').title()}: {val}"
                for key, val in value.items()
                if not str(key).endswith("_id") and str(val).strip()
            ]
            return " | ".join(parts)

        return value

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

        for key, value in list(cleaned.items()):
            cleaned[key] = _display_value(value)

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
