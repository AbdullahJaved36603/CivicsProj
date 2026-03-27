from __future__ import annotations

from io import StringIO
from typing import Any, Callable, Dict, List

import pandas as pd
import streamlit as st

from frontend.components.forms import build_option_map, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload
from frontend.ui_theme import card, controls_disabled, render_page_header, show_loading
from system_admin import service_layer
from system_admin.google_sheets_utils import safe_sheet_read


def _records_to_csv(records: List[Dict[str, Any]]) -> str:
    if not records:
        return ""
    frame = pd.DataFrame(records)
    csv_buffer = StringIO()
    frame.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()


def _safe_backend_call(api_func: Callable[[], Dict[str, Any]], spinner_text: str) -> Dict[str, Any]:
    if controls_disabled():
        return {"success": False, "message": "Please wait, loading data..."}

    try:
        with show_loading(spinner_text):
            response = safe_sheet_read(api_func, retries=3, delay_seconds=1.0)
        if isinstance(response, dict):
            return response
        return {"success": False, "message": "Unexpected server response."}
    except Exception:
        return {
            "success": False,
            "message": "Network issue while fetching data. Please wait and try again.",
        }


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _render_overall_metrics(title: str, metrics: Dict[str, Any]) -> None:
    st.markdown(f"#### {title}")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Students", _safe_int(metrics.get("total_students", 0)))
    with col2:
        st.metric("Appeared", _safe_int(metrics.get("appeared_students", 0)))
    with col3:
        st.metric("Passed", _safe_int(metrics.get("passed_students", 0)))
    with col4:
        st.metric("Pass %", round(_safe_float(metrics.get("pass_percentage", 0)), 2))

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Failed", _safe_int(metrics.get("failed_students", 0)))
    with col6:
        st.metric("Absent", _safe_int(metrics.get("absent_students", 0)))
    with col7:
        st.metric("Avg Marks", round(_safe_float(metrics.get("average_marks", 0)), 2))


def _render_pass_fail_chart(metrics: Dict[str, Any]) -> None:
    pass_fail_frame = pd.DataFrame(
        [
            {"Status": "Pass", "Students": _safe_int(metrics.get("passed_students", 0))},
            {"Status": "Fail", "Students": _safe_int(metrics.get("failed_students", 0))},
            {"Status": "Absent", "Students": _safe_int(metrics.get("absent_students", 0))},
        ]
    )
    st.bar_chart(pass_fail_frame, x="Status", y="Students")


def _render_gender_chart(metrics: Dict[str, Any]) -> None:
    gender_frame = pd.DataFrame(
        [
            {
                "Gender": "Male",
                "Pass": _safe_int(metrics.get("male_passed", 0)),
                "Fail": _safe_int(metrics.get("male_failed", 0)),
            },
            {
                "Gender": "Female",
                "Pass": _safe_int(metrics.get("female_passed", 0)),
                "Fail": _safe_int(metrics.get("female_failed", 0)),
            },
        ]
    )
    st.bar_chart(gender_frame, x="Gender", y=["Pass", "Fail"])


def _exam_session_selector(session_id: str, key: str) -> str:
    sessions_response = _safe_backend_call(
        lambda: service_layer.get_exam_sessions(session_id),
        "Loading exam sessions...",
    )
    sessions = sessions_response.get("data", {}).get("exam_sessions", []) if sessions_response.get("success") else []
    session_map = build_option_map(sessions, "exam_session_id", "month")
    if not session_map:
        st.warning("No exam sessions found for selected session.")
        return ""
    selected_label = st.selectbox("Exam Session", list(session_map.keys()), key=key, disabled=controls_disabled())
    return get_select_value(session_map, selected_label)


def _optional_filter_select(
    label: str,
    items: List[Dict[str, Any]],
    id_key: str,
    name_key: str,
    key: str,
    all_label: str,
) -> str:
    option_map = build_option_map(items, id_key, name_key)
    labels = [all_label] + list(option_map.keys())
    selected_label = st.selectbox(label, labels, key=key, disabled=controls_disabled())
    if selected_label == all_label:
        return ""
    return get_select_value(option_map, selected_label)


def render_admin_analytics(admin_id: str) -> None:
    if controls_disabled():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Admin Analytics", "Cross-school performance insights for the selected session")

    selected_session_id = str(st.session_state.get("selected_session_id", "")).strip()
    if not selected_session_id:
        st.warning("Select a session from admin pages to view analytics.")
        return

    selected_exam_session_id = _exam_session_selector(selected_session_id, "admin_exam_session_filter")
    if not selected_exam_session_id:
        return

    schools_response = _safe_backend_call(
        lambda: service_layer.get_all_schools(session_id=selected_session_id),
        "Loading schools...",
    )
    schools = schools_response.get("data", {}).get("schools", []) if schools_response.get("success") else []

    selected_school_id = _optional_filter_select(
        "School Filter",
        schools,
        "school_id",
        "school_name",
        "admin_school_filter",
        "All Schools",
    )

    class_candidates: List[Dict[str, Any]] = []
    subject_candidates: List[Dict[str, Any]] = []
    if selected_school_id:
        class_response = _safe_backend_call(
            lambda: service_layer.get_school_classes(selected_school_id, selected_session_id),
            "Loading classes...",
        )
        class_candidates = class_response.get("data", {}).get("classes", []) if class_response.get("success") else []

        subject_response = _safe_backend_call(
            lambda: service_layer.get_school_subjects(selected_school_id, selected_session_id),
            "Loading subjects...",
        )
        subject_candidates = subject_response.get("data", {}).get("subjects", []) if subject_response.get("success") else []

    selected_class_id = _optional_filter_select(
        "Class Filter",
        class_candidates,
        "class_id",
        "class_name",
        "admin_class_filter",
        "All Classes",
    )

    if selected_class_id:
        subject_candidates = [
            item for item in subject_candidates if str(item.get("class_id", "")) == selected_class_id
        ]

    selected_subject_id = _optional_filter_select(
        "Subject Filter",
        subject_candidates,
        "subject_id",
        "subject_name",
        "admin_subject_filter",
        "All Subjects",
    )

    response = _safe_backend_call(
        lambda: service_layer.get_all_school_analytics(
            admin_id,
            selected_session_id,
            selected_exam_session_id,
            school_id=selected_school_id,
            class_id=selected_class_id,
            subject_id=selected_subject_id,
        ),
        "Loading analytics...",
    )
    show_form_result(response)
    if not response.get("success"):
        return

    payload = response.get("data", {})
    schools = payload.get("schools", [])
    class_section_rows = payload.get("class_section_analytics", [])
    school_comparison = payload.get("school_comparison", [])

    total_students = sum(_safe_int(item.get("total_students", 0)) for item in schools)
    appeared_students = sum(_safe_int(item.get("appeared_students", 0)) for item in schools)
    passed_students = sum(_safe_int(item.get("passed_students", 0)) for item in schools)
    failed_students = sum(_safe_int(item.get("failed_students", 0)) for item in schools)
    pass_percentage = round((passed_students / appeared_students) * 100, 2) if appeared_students else 0.0
    average_marks = round(
        sum(_safe_float(item.get("average_marks", 0)) for item in schools) / len(schools),
        2,
    ) if schools else 0.0

    with card("Session Overview", "Top metrics and benchmark trends"):
        _render_overall_metrics(
            "Session Overview",
            {
                "total_students": total_students,
                "appeared_students": appeared_students,
                "passed_students": passed_students,
                "failed_students": failed_students,
                "pass_percentage": pass_percentage,
                "absent_students": max(total_students - appeared_students, 0),
                "average_marks": average_marks,
            },
        )

    if school_comparison:
        with card("School Comparison", "Pass percentage and average marks by school"):
            comparison_frame = pd.DataFrame(school_comparison)
            st.dataframe(comparison_frame, use_container_width=True)
            st.bar_chart(comparison_frame, x="school_name", y="pass_percentage")
            st.bar_chart(comparison_frame, x="school_name", y="average_marks")

            comparison_csv = _records_to_csv(school_comparison)
            if comparison_csv:
                st.download_button(
                    "Download School Comparison CSV",
                    data=comparison_csv,
                    file_name=f"school_comparison_{selected_session_id}_{selected_exam_session_id}.csv",
                    mime="text/csv",
                    key="download_admin_school_comparison",
                    disabled=controls_disabled(),
                )

    if class_section_rows:
        with card("Class and Section Analytics", "Deep dive into class-level trends"):
            class_frame = pd.DataFrame(class_section_rows)
            class_frame["school_class"] = class_frame["school_name"].astype(str) + " - " + class_frame["class_label"].astype(str)
            st.dataframe(class_frame, use_container_width=True)
            st.line_chart(class_frame, x="school_class", y="pass_percentage")

            class_csv = _records_to_csv(class_section_rows)
            if class_csv:
                st.download_button(
                    "Download Class Section CSV",
                    data=class_csv,
                    file_name=f"class_section_analytics_{selected_session_id}_{selected_exam_session_id}.csv",
                    mime="text/csv",
                    key="download_admin_class_section",
                    disabled=controls_disabled(),
                )

    show_records("Session School Analytics", schools)


def render_principal_analytics(principal_id: str) -> None:
    if controls_disabled():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Principal Analytics", "School-wide performance trends by class and subject")

    schools_response = _safe_backend_call(
        lambda: service_layer.get_principal_schools(principal_id),
        "Loading school context...",
    )
    if not schools_response.get("success"):
        show_form_result(schools_response)
        return

    schools = schools_response.get("data", {}).get("schools", [])
    school_map = build_option_map(schools, "school_id", "school_name")
    if not school_map:
        st.warning("No accessible schools found in active session.")
        return

    labels = list(school_map.keys())
    selected_school_id = str(st.session_state.get("selected_school_id", "")).strip()
    default_index = 0
    if selected_school_id:
        for index, label in enumerate(labels):
            if get_select_value(school_map, label) == selected_school_id:
                default_index = index
                break

    selected_label = st.selectbox(
        "School Context",
        labels,
        index=default_index,
        key="principal_analytics_school_label",
        disabled=controls_disabled(),
    )
    selected_school_id = get_select_value(school_map, selected_label)
    st.session_state["selected_school_id"] = selected_school_id

    selected_school = next(
        (item for item in schools if str(item.get("school_id", "")) == selected_school_id),
        {},
    )
    session_id = str(selected_school.get("session_id", "")).strip()
    selected_exam_session_id = _exam_session_selector(session_id, "principal_exam_session_filter")
    if not selected_exam_session_id:
        return

    class_response = _safe_backend_call(
        lambda: service_layer.get_school_classes(selected_school_id, session_id),
        "Loading classes...",
    )
    class_candidates = class_response.get("data", {}).get("classes", []) if class_response.get("success") else []
    selected_class_id = _optional_filter_select(
        "Class Filter",
        class_candidates,
        "class_id",
        "class_name",
        "principal_class_filter",
        "All Classes",
    )

    subject_response = _safe_backend_call(
        lambda: service_layer.get_school_subjects(selected_school_id, session_id),
        "Loading subjects...",
    )
    subject_candidates = subject_response.get("data", {}).get("subjects", []) if subject_response.get("success") else []
    if selected_class_id:
        subject_candidates = [
            item for item in subject_candidates if str(item.get("class_id", "")) == selected_class_id
        ]
    selected_subject_id = _optional_filter_select(
        "Subject Filter",
        subject_candidates,
        "subject_id",
        "subject_name",
        "principal_subject_filter",
        "All Subjects",
    )

    response = _safe_backend_call(
        lambda: service_layer.get_school_analytics_for_principal(
            principal_id,
            selected_school_id,
            selected_exam_session_id,
            class_id=selected_class_id,
            subject_id=selected_subject_id,
        ),
        "Loading analytics...",
    )
    show_form_result(response)
    if not response.get("success"):
        return

    payload = response.get("data", {})
    overall = payload.get("overall", {})
    with card("School Overview", "Top metrics and pass/fail distribution"):
        _render_overall_metrics("School Overview", overall)
        _render_pass_fail_chart(overall)
        _render_gender_chart(overall)

    class_rows = payload.get("class_wise", [])
    if class_rows:
        with card("Class-wise Analytics", "Class performance overview"):
            class_frame = pd.DataFrame(class_rows)
            st.dataframe(class_frame, use_container_width=True)
            st.bar_chart(class_frame, x="class_label", y="pass_percentage")

    subject_rows = payload.get("subject_wise", [])
    if subject_rows:
        with card("Subject-wise Analytics", "Subject trend comparison"):
            subject_frame = pd.DataFrame(subject_rows)
            st.dataframe(subject_frame, use_container_width=True)
            st.bar_chart(subject_frame, x="subject_name", y="average_marks")

    downloadable_rows = subject_rows if subject_rows else class_rows
    csv_data = _records_to_csv(downloadable_rows)
    if csv_data:
        st.download_button(
            "Download Filtered Analytics CSV",
            data=csv_data,
            file_name=f"principal_school_analytics_{selected_school_id}_{selected_exam_session_id}.csv",
            mime="text/csv",
            key="download_principal_filtered_analytics",
            disabled=controls_disabled(),
        )


def render_teacher_analytics(teacher_id: str) -> None:
    if controls_disabled():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Teacher Analytics", "Track school and class outcomes for your assigned context")

    schools_response = _safe_backend_call(
        lambda: service_layer.get_teacher_schools(teacher_id),
        "Loading school context...",
    )
    if not schools_response.get("success"):
        show_form_result(schools_response)
        return

    schools = schools_response.get("data", {}).get("schools", [])
    school_map = build_option_map(schools, "school_id", "school_name")
    if not school_map:
        st.warning("No school context found for teacher.")
        return

    selected_label = st.selectbox(
        "School Context",
        list(school_map.keys()),
        key="teacher_analytics_school_label",
        disabled=controls_disabled(),
    )
    selected_school_id = get_select_value(school_map, selected_label)
    selected_school = next(
        (item for item in schools if str(item.get("school_id", "")) == selected_school_id),
        {},
    )
    session_id = str(selected_school.get("session_id", "")).strip()

    selected_exam_session_id = _exam_session_selector(session_id, "teacher_page_exam_session_filter")
    if not selected_exam_session_id:
        return

    class_response = _safe_backend_call(
        lambda: service_layer.get_school_classes(selected_school_id, session_id),
        "Loading classes...",
    )
    class_candidates = class_response.get("data", {}).get("classes", []) if class_response.get("success") else []
    selected_class_id = _optional_filter_select(
        "Class Filter",
        class_candidates,
        "class_id",
        "class_name",
        "teacher_page_class_filter",
        "All Classes",
    )

    subject_response = _safe_backend_call(
        lambda: service_layer.get_school_subjects(selected_school_id, session_id),
        "Loading subjects...",
    )
    subject_candidates = subject_response.get("data", {}).get("subjects", []) if subject_response.get("success") else []
    if selected_class_id:
        subject_candidates = [
            item for item in subject_candidates if str(item.get("class_id", "")) == selected_class_id
        ]
    selected_subject_id = _optional_filter_select(
        "Subject Filter",
        subject_candidates,
        "subject_id",
        "subject_name",
        "teacher_page_subject_filter",
        "All Subjects",
    )

    response = _safe_backend_call(
        lambda: service_layer.get_school_analytics_for_teacher(
            teacher_id,
            selected_school_id,
            selected_exam_session_id,
            class_id=selected_class_id,
            subject_id=selected_subject_id,
        ),
        "Loading analytics...",
    )
    show_form_result(response)
    if not response.get("success"):
        return

    payload = response.get("data", {})
    overall = payload.get("overall", {})
    with card("School Overview", "Top metrics and pass/fail distribution"):
        _render_overall_metrics("School Overview", overall)
        _render_pass_fail_chart(overall)
        _render_gender_chart(overall)

    class_rows = payload.get("class_wise", [])
    if class_rows:
        with card("Class-wise Analytics", "Class-level trend view"):
            class_frame = pd.DataFrame(class_rows)
            st.dataframe(class_frame, use_container_width=True)
            st.line_chart(class_frame, x="class_label", y="pass_percentage")

    subject_rows = payload.get("subject_wise", [])
    if subject_rows:
        with card("Subject-wise Analytics", "Subject trend view"):
            subject_frame = pd.DataFrame(subject_rows)
            st.dataframe(subject_frame, use_container_width=True)
            st.bar_chart(subject_frame, x="subject_name", y="average_marks")

    csv_data = _records_to_csv(subject_rows if subject_rows else class_rows)
    if csv_data:
        st.download_button(
            "Download Filtered Analytics CSV",
            data=csv_data,
            file_name=f"teacher_school_analytics_{selected_school_id}_{selected_exam_session_id}.csv",
            mime="text/csv",
            key="download_teacher_filtered_analytics",
            disabled=controls_disabled(),
        )

    show_response_payload(response)
