from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from frontend.components.forms import show_form_result
from frontend.components.tables import show_response_payload
from system_admin import service_layer


def _render_bar_chart(title: str, data_map: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    if not data_map:
        st.info("No chart data available.")
        return

    chart_rows = []
    for label, value in data_map.items():
        try:
            numeric_value = float(value)
        except Exception:
            continue
        chart_rows.append({"label": str(label), "value": numeric_value})

    if not chart_rows:
        st.info("No numeric chart data available.")
        return

    st.bar_chart(chart_rows, x="label", y="value")


def _render_line_chart_monthly_vs_final(monthly_vs_final: Dict[str, Any]) -> None:
    st.markdown("#### Monthly vs Final Comparison")
    if not monthly_vs_final:
        st.info("No chart data available.")
        return

    monthly = monthly_vs_final.get("monthly_average", 0)
    final = monthly_vs_final.get("final_average", 0)
    try:
        monthly_value = float(monthly)
        final_value = float(final)
    except Exception:
        st.info("No numeric chart data available.")
        return

    chart_rows = [
        {"exam": "Monthly", "average": monthly_value},
        {"exam": "Final", "average": final_value},
    ]
    st.line_chart(chart_rows, x="exam", y="average")


def _render_analytics_payload(payload: Dict[str, Any]) -> None:
    class_map = payload.get("average_marks_per_class", {})
    subject_map = payload.get("average_marks_per_subject", {})
    monthly_final = payload.get("monthly_vs_final", {})

    _render_bar_chart("Average Marks by Class", class_map)
    _render_bar_chart("Average Marks by Subject", subject_map)
    _render_line_chart_monthly_vs_final(monthly_final)


def render_admin_analytics(admin_id: str) -> None:
    st.markdown("### Global Analytics")
    response = service_layer.get_all_school_analytics(admin_id)
    show_form_result(response)
    if not response.get("success"):
        return

    payload = response.get("data", {})
    _render_analytics_payload(payload)
    show_response_payload(response)


def render_principal_analytics(principal_id: str) -> None:
    st.markdown("### School Analytics")
    response = service_layer.get_school_analytics_for_principal(principal_id)
    show_form_result(response)
    if not response.get("success"):
        return

    payload = response.get("data", {})
    _render_analytics_payload(payload)
    show_response_payload(response)


def render_teacher_analytics(teacher_id: str) -> None:
    st.markdown("### School Analytics")
    response = service_layer.get_school_analytics_for_teacher(teacher_id)
    show_form_result(response)
    if not response.get("success"):
        return
    payload = response.get("data", {})
    _render_analytics_payload(payload)
    show_response_payload(response)
