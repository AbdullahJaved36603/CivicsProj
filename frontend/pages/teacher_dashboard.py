from __future__ import annotations

import time
from io import StringIO
from typing import Any, Callable, Dict, List

import altair as alt
import pandas as pd
import streamlit as st

from frontend.components.forms import build_option_map, form_heading, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload
from frontend.ui_theme import card, controls_disabled, ensure_page_config, pill_select, render_page_header, show_loading
from system_admin import service_layer
from system_admin.google_sheets_utils import parse_marks, safe_sheet_read


def _init_ui_state() -> None:
    if "is_loading" not in st.session_state:
        st.session_state["is_loading"] = False
    if "grid_ready" not in st.session_state:
        st.session_state["grid_ready"] = False
    if "marks_dataframe" not in st.session_state:
        st.session_state["marks_dataframe"] = pd.DataFrame()
    if "marks_total_marks" not in st.session_state:
        st.session_state["marks_total_marks"] = "100"
    if "marks_grid_key" not in st.session_state:
        st.session_state["marks_grid_key"] = ""
    if "last_class" not in st.session_state:
        st.session_state["last_class"] = ""
    if "last_subject" not in st.session_state:
        st.session_state["last_subject"] = ""
    if "last_exam_session" not in st.session_state:
        st.session_state["last_exam_session"] = ""
    if "last_save_time" not in st.session_state:
        st.session_state["last_save_time"] = 0.0


def _reset_grid_state() -> None:
    st.session_state["grid_ready"] = False
    st.session_state["marks_dataframe"] = pd.DataFrame()
    st.session_state["marks_total_marks"] = "100"


def _loading() -> bool:
    return controls_disabled()


def _safe_backend_call(api_func: Callable[[], Dict[str, Any]], spinner_text: str) -> Dict[str, Any]:
    if _loading():
        return {"success": False, "message": "Please wait, loading data..."}

    try:
        with show_loading(spinner_text):
            response = safe_sheet_read(api_func, retries=3, delay_seconds=1.0)
        if not isinstance(response, dict):
            return {"success": False, "message": "Unexpected server response."}
        return response
    except Exception:
        return {
            "success": False,
            "message": "Network issue while fetching data. Please wait and try again.",
        }
    finally:
        pass


def _cached_read(cache_key: str, fetch_func: Callable[[], Dict[str, Any]], data_key: str, spinner_text: str) -> List[Dict[str, Any]]:
    if cache_key in st.session_state:
        return list(st.session_state.get(cache_key, []))

    response = _safe_backend_call(fetch_func, spinner_text)
    if not response.get("success"):
        st.session_state[cache_key] = []
        return []

    rows = response.get("data", {}).get(data_key, [])
    st.session_state[cache_key] = rows
    return list(rows)


def _teacher_classes(teacher_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"teacher_classes::{teacher_id}",
        fetch_func=lambda: service_layer.get_teacher_classes(teacher_id),
        data_key="classes",
        spinner_text="Loading classes...",
    )


def _teacher_exam_sessions(teacher_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"teacher_exam_sessions::{teacher_id}",
        fetch_func=lambda: service_layer.get_teacher_exam_sessions(teacher_id),
        data_key="exam_sessions",
        spinner_text="Loading exam sessions...",
    )


def _teacher_subjects(teacher_id: str, class_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"teacher_subjects::{teacher_id}::{class_id}",
        fetch_func=lambda: service_layer.get_teacher_subjects(teacher_id, class_id),
        data_key="subjects",
        spinner_text="Loading subjects...",
    )


def _teacher_students(teacher_id: str, class_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"teacher_students::{teacher_id}::{class_id}",
        fetch_func=lambda: service_layer.get_teacher_students(teacher_id, class_id),
        data_key="students",
        spinner_text="Loading students...",
    )


def _teacher_schools(teacher_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"teacher_schools::{teacher_id}",
        fetch_func=lambda: service_layer.get_teacher_schools(teacher_id),
        data_key="schools",
        spinner_text="Loading school context...",
    )


def _records_to_csv(records: List[Dict[str, Any]]) -> str:
    if not records:
        return ""
    frame = pd.DataFrame(records)
    id_columns = [column for column in frame.columns if str(column).endswith("_id")]
    if id_columns:
        frame = frame.drop(columns=id_columns, errors="ignore")
    csv_buffer = StringIO()
    frame.to_csv(csv_buffer, index=False)
    return csv_buffer.getvalue()


def _validate_marks_rows(rows: List[Dict[str, Any]], total_marks: str) -> str:
    for row in rows:
        marks_value = row.get("marks", "")
        parsed = parse_marks(marks_value, total_marks)
        if parsed.get("is_valid", False):
            continue
        error_code = str(parsed.get("error", "")).strip()
        if error_code == "marks_not_numeric":
            return "Invalid marks entered: use numeric value or A/Absent."
        if error_code == "marks_negative":
            return "Invalid marks entered: marks cannot be negative."
        if error_code == "marks_exceed_total":
            return "Invalid marks entered: marks cannot exceed total marks."
        if error_code == "total_marks_invalid":
            return "Total Marks must be greater than zero."
        return "Invalid marks entered."
    return ""


def _altair_bar(data: pd.DataFrame, x_field: str, y_field: str, color_field: str = "") -> alt.Chart:
    encode_args: Dict[str, Any] = {
        "x": alt.X(f"{x_field}:N", sort="-y"),
        "y": alt.Y(f"{y_field}:Q"),
        "tooltip": [x_field, y_field],
    }
    if color_field:
        encode_args["color"] = alt.Color(f"{color_field}:N")
    return alt.Chart(data).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(**encode_args)


def _altair_line(data: pd.DataFrame, x_field: str, y_field: str, color_field: str = "") -> alt.Chart:
    encode_args: Dict[str, Any] = {
        "x": alt.X(f"{x_field}:N"),
        "y": alt.Y(f"{y_field}:Q"),
        "tooltip": [x_field, y_field],
    }
    if color_field:
        encode_args["color"] = alt.Color(f"{color_field}:N")
    return alt.Chart(data).mark_line(point=True).encode(**encode_args)


def _render_summary_metrics(title: str, metrics: Dict[str, Any]) -> None:
    st.markdown(f"##### {title}")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Students", int(metrics.get("total_students", 0)))
    with col2:
        st.metric("Appeared", int(metrics.get("appeared_students", 0)))
    with col3:
        st.metric("Passed", int(metrics.get("passed_students", 0)))
    with col4:
        st.metric("Pass %", metrics.get("pass_percentage", 0.0))

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Failed", int(metrics.get("failed_students", 0)))
    with col6:
        st.metric("Absent", int(metrics.get("absent_students", 0)))
    with col7:
        st.metric("Avg Marks", metrics.get("average_marks", 0.0))


def _render_pass_fail_and_gender_charts(metrics: Dict[str, Any], key_prefix: str) -> None:
    pass_fail_frame = pd.DataFrame(
        [
            {"Status": "Pass", "Students": int(metrics.get("passed_students", 0))},
            {"Status": "Fail", "Students": int(metrics.get("failed_students", 0))},
            {"Status": "Absent", "Students": int(metrics.get("absent_students", 0))},
        ]
    )
    with st.container(border=True):
        st.markdown("##### Pass/Fail Distribution")
        st.altair_chart(_altair_bar(pass_fail_frame, "Status", "Students", "Status"), use_container_width=True)

    gender_frame = pd.DataFrame(
        [
            {
                "Gender": "Male",
                "Pass": int(metrics.get("male_passed", 0)),
                "Fail": int(metrics.get("male_failed", 0)),
            },
            {
                "Gender": "Female",
                "Pass": int(metrics.get("female_passed", 0)),
                "Fail": int(metrics.get("female_failed", 0)),
            },
        ]
    )
    with st.container(border=True):
        st.markdown("##### Gender Breakdown")
        gender_long = gender_frame.melt(id_vars=["Gender"], var_name="Outcome", value_name="Students")
        st.altair_chart(
            _altair_bar(gender_long, "Gender", "Students", "Outcome"),
            use_container_width=True,
        )

    csv_data = _records_to_csv(gender_frame.to_dict("records"))
    if csv_data:
        st.download_button(
            "Download Gender Breakdown CSV",
            data=csv_data,
            file_name=f"{key_prefix}_gender_breakdown.csv",
            mime="text/csv",
            key=f"download_gender_{key_prefix}",
            disabled=_loading(),
        )


def _render_student_enrollment(teacher_id: str) -> None:
    form_heading("Student Enrollment", "Enroll students in classes where you are incharge")

    classes = _teacher_classes(teacher_id)
    incharge_classes = [item for item in classes if "incharge" in str(item.get("access", ""))]
    class_map = build_option_map(incharge_classes, "class_id", "class_name")

    if not class_map:
        st.info("No incharge classes available.")
        return

    with st.form("enroll_student_form"):
        selected_class = pill_select(
            "Class",
            list(class_map.keys()),
            key="teacher_enroll_class",
            disabled=_loading(),
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            student_name = st.text_input("Student name", disabled=_loading())
        with col2:
            parent_name = st.text_input("Parent name", disabled=_loading())
        with col3:
            gender = pill_select(
                "Gender",
                ["Male", "Female"],
                key="teacher_enroll_gender",
                disabled=_loading(),
            )
        enroll_label = "⏳ Enrolling..." if _loading() else "Enroll Student"
        submitted = st.form_submit_button(enroll_label, disabled=_loading(), use_container_width=True)

    if submitted:
        class_id = get_select_value(class_map, selected_class)
        response = _safe_backend_call(
            lambda: service_layer.enroll_student(teacher_id, class_id, student_name, gender, parent_name),
            "Enrolling student...",
        )
        show_form_result(response)
        show_response_payload(response)
        if response.get("success"):
            st.session_state.pop(f"teacher_students::{teacher_id}::{class_id}", None)

    selected_class_id = get_select_value(class_map, selected_class)
    students = _teacher_students(teacher_id, selected_class_id)
    show_records("Students", students)


def _render_results_entry(teacher_id: str) -> None:
    form_heading("Results Entry", "Use spreadsheet-style marks entry for assigned classes and subjects")

    classes = _teacher_classes(teacher_id)
    class_map = build_option_map(classes, "class_id", "class_name")
    if not class_map:
        st.info("No accessible classes available.")
        return

    selected_class_label = pill_select(
        "Class",
        list(class_map.keys()),
        key="teacher_results_class",
        disabled=_loading(),
    )
    selected_class_id = get_select_value(class_map, selected_class_label)

    subjects = _teacher_subjects(teacher_id, selected_class_id)
    exam_sessions = _teacher_exam_sessions(teacher_id)

    subject_map = build_option_map(subjects, "subject_id", "subject_name")
    exam_session_map = build_option_map(exam_sessions, "exam_session_id", "month")

    if not subject_map:
        st.info("No assigned subjects found for the selected class.")
        return
    if not exam_session_map:
        st.info("No exam sessions available for your school's session.")
        return

    selected_exam_session = pill_select(
        "Exam Session",
        list(exam_session_map.keys()),
        key="teacher_grid_exam",
        disabled=_loading(),
    )
    selected_subject = pill_select(
        "Subject",
        list(subject_map.keys()),
        key="teacher_grid_subject",
        disabled=_loading(),
    )
    exam_session_id = get_select_value(exam_session_map, selected_exam_session)
    subject_id = get_select_value(subject_map, selected_subject)

    if selected_class_id != st.session_state.get("last_class", ""):
        st.session_state["last_class"] = selected_class_id
        _reset_grid_state()
    if subject_id != st.session_state.get("last_subject", ""):
        st.session_state["last_subject"] = subject_id
        _reset_grid_state()
    if exam_session_id != st.session_state.get("last_exam_session", ""):
        st.session_state["last_exam_session"] = exam_session_id
        _reset_grid_state()

    grid_key = f"{selected_class_id}|{subject_id}|{exam_session_id}"
    if grid_key != st.session_state.get("marks_grid_key", ""):
        st.session_state["marks_grid_key"] = grid_key
        _reset_grid_state()

    if not st.session_state.get("grid_ready", False):
        st.session_state["grid_ready"] = False

        if time.time() - float(st.session_state.get("last_save_time", 0.0)) < 2:
            st.info("Finalizing previous save. Please wait...")
            st.stop()

        grid_response = _safe_backend_call(
            lambda: service_layer.get_teacher_marks_entry_grid(
                teacher_id,
                selected_class_id,
                subject_id,
                exam_session_id,
            ),
            "Fetching marks...",
        )
        show_form_result(grid_response)

        if not grid_response.get("success"):
            st.session_state["grid_ready"] = False
            st.error("Network issue while fetching data. Please wait and try again.")
            return

        payload = grid_response.get("data", {})
        rows = payload.get("rows", [])
        if not rows:
            st.info("No students found for selected class.")
            st.session_state["grid_ready"] = False
            return

        st.session_state["marks_dataframe"] = pd.DataFrame(rows)
        st.session_state["marks_total_marks"] = str(payload.get("total_marks", "")).strip() or "100"
        st.session_state["grid_ready"] = True

    if not st.session_state.get("grid_ready", False):
        st.info("Loading student data...")
        return

    total_marks = st.text_input(
        "Total Marks",
        value=str(st.session_state.get("marks_total_marks", "100")),
        key=f"teacher_total_marks_{grid_key}",
        disabled=_loading(),
    )
    st.session_state["marks_total_marks"] = total_marks

    marks_frame = st.session_state.get("marks_dataframe", pd.DataFrame()).copy()
    if marks_frame.empty:
        st.info("Loading student data...")
        return

    editor_disabled: bool | List[str]
    if _loading():
        editor_disabled = True
    else:
        editor_disabled = ["student_id", "student_name", "parent_name", "gender"]

    edited_frame = st.data_editor(
        marks_frame,
        hide_index=True,
        use_container_width=True,
        column_config={
            "student_id": None,
            "student_name": st.column_config.TextColumn("Student Name"),
            "parent_name": st.column_config.TextColumn("Parent Name"),
            "gender": st.column_config.TextColumn("Gender"),
            "marks": st.column_config.TextColumn("Marks"),
        },
        disabled=editor_disabled,
        key=f"teacher_marks_editor_{grid_key}",
    )
    st.session_state["marks_dataframe"] = edited_frame.copy()

    csv_data = _records_to_csv(edited_frame.to_dict("records"))
    if csv_data:
        st.download_button(
            "Download Current Grid CSV",
            data=csv_data,
            file_name=f"marks_grid_{selected_class_id}_{subject_id}_{exam_session_id}.csv",
            mime="text/csv",
            key=f"download_marks_grid_{selected_class_id}_{subject_id}_{exam_session_id}",
            disabled=_loading(),
        )

    upload_label = "⏳ Uploading..." if _loading() else "Upload Marks"
    upload_clicked = st.button(
        upload_label,
        use_container_width=True,
        disabled=_loading() or (not st.session_state.get("grid_ready", False)),
    )
    if upload_clicked:
        edited_records = edited_frame[["student_id", "marks"]].to_dict("records")
        validation_error = _validate_marks_rows(edited_records, total_marks)
        if validation_error:
            st.error(validation_error)
            return

        response = _safe_backend_call(
            lambda: service_layer.save_marks(
                teacher_id,
                subject_id,
                selected_class_id,
                exam_session_id,
                total_marks,
                edited_records,
            ),
            "Saving marks...",
        )
        show_form_result(response)
        show_response_payload(response)

        if response.get("success"):
            st.success("Marks saved successfully")
            st.session_state["last_save_time"] = time.time()
            st.session_state["grid_ready"] = False


def _analytics_cached_response(cache_key: str, loader: Callable[[], Dict[str, Any]], spinner_text: str) -> Dict[str, Any]:
    if cache_key in st.session_state:
        return dict(st.session_state.get(cache_key, {}))

    response = _safe_backend_call(loader, spinner_text)
    st.session_state[cache_key] = response
    return response


def _render_analytics_sections(teacher_id: str) -> None:
    form_heading("Teacher Analytics", "Role-scoped analytics for class incharge and assigned subjects")

    exam_sessions = _teacher_exam_sessions(teacher_id)
    exam_session_map = build_option_map(exam_sessions, "exam_session_id", "month")
    if not exam_session_map:
        st.info("No exam sessions available for analytics.")
        return

    selected_exam_session_label = pill_select(
        "Exam Session",
        list(exam_session_map.keys()),
        key="teacher_analytics_exam_session",
        disabled=_loading(),
    )
    selected_exam_session_id = get_select_value(exam_session_map, selected_exam_session_label)

    classes = _teacher_classes(teacher_id)
    incharge_classes = [item for item in classes if "incharge" in str(item.get("access", ""))]
    incharge_class_map = build_option_map(incharge_classes, "class_id", "class_name")

    st.markdown("##### Class Incharge Analytics")
    if incharge_class_map:
        selected_class_label = pill_select(
            "Class",
            list(incharge_class_map.keys()),
            key="teacher_incharge_analytics_class",
            disabled=_loading(),
        )
        selected_class_id = get_select_value(incharge_class_map, selected_class_label)

        class_cache_key = f"class_analytics::{teacher_id}::{selected_class_id}::{selected_exam_session_id}"
        response = _analytics_cached_response(
            class_cache_key,
            lambda: service_layer.get_class_analytics(teacher_id, selected_class_id, selected_exam_session_id),
            "Loading class analytics...",
        )

        show_form_result(response)
        if response.get("success"):
            payload = response.get("data", {})
            overall = payload.get("overall", {})
            _render_summary_metrics("Class Overview", overall)
            _render_pass_fail_and_gender_charts(overall, f"class_{selected_class_id}_{selected_exam_session_id}")

            subject_rows = payload.get("subject_wise", [])
            if subject_rows:
                st.markdown("##### Subject-wise Performance")
                subject_frame = pd.DataFrame(subject_rows)
                st.dataframe(subject_frame, use_container_width=True)
                with st.container(border=True):
                    st.altair_chart(
                        _altair_bar(subject_frame, "subject_name", "average_marks", "subject_name"),
                        use_container_width=True,
                    )

                subject_csv = _records_to_csv(subject_rows)
                if subject_csv:
                    st.download_button(
                        "Download Subject-wise CSV",
                        data=subject_csv,
                        file_name=f"class_subject_analytics_{selected_class_id}_{selected_exam_session_id}.csv",
                        mime="text/csv",
                        key=f"download_class_subject_{selected_class_id}_{selected_exam_session_id}",
                        disabled=_loading(),
                    )
    else:
        st.info("You are not class incharge for any class.")

    st.markdown("##### Subject Analytics")
    class_map = build_option_map(classes, "class_id", "class_name")
    if class_map:
        selected_class_label = pill_select(
            "Class",
            list(class_map.keys()),
            key="teacher_subject_analytics_class",
            disabled=_loading(),
        )
        selected_class_id = get_select_value(class_map, selected_class_label)
        subjects = _teacher_subjects(teacher_id, selected_class_id)
        subject_map = build_option_map(subjects, "subject_id", "subject_name")
        if subject_map:
            selected_subject_label = pill_select(
                "Subject",
                list(subject_map.keys()),
                key="teacher_subject_analytics_subject",
                disabled=_loading(),
            )
            selected_subject_id = get_select_value(subject_map, selected_subject_label)

            subject_cache_key = (
                f"subject_analytics::{teacher_id}::{selected_subject_id}::{selected_exam_session_id}"
            )
            response = _analytics_cached_response(
                subject_cache_key,
                lambda: service_layer.get_subject_analytics(
                    teacher_id,
                    selected_subject_id,
                    selected_exam_session_id,
                ),
                "Loading subject analytics...",
            )
            show_form_result(response)
            if response.get("success"):
                payload = response.get("data", {})
                overall = payload.get("overall", {})
                _render_summary_metrics("Subject Overview", overall)
                _render_pass_fail_and_gender_charts(
                    overall,
                    f"subject_{selected_subject_id}_{selected_exam_session_id}",
                )

                by_class = payload.get("by_class", [])
                if by_class:
                    st.markdown("##### Class-wise Subject Trends")
                    by_class_frame = pd.DataFrame(by_class)
                    st.dataframe(by_class_frame, use_container_width=True)
                    with st.container(border=True):
                        st.altair_chart(
                            _altair_line(by_class_frame, "class_label", "pass_percentage"),
                            use_container_width=True,
                        )
                    with st.container(border=True):
                        st.altair_chart(
                            _altair_bar(by_class_frame, "class_label", "average_marks", "class_label"),
                            use_container_width=True,
                        )

                    class_csv = _records_to_csv(by_class)
                    if class_csv:
                        st.download_button(
                            "Download Class-wise Subject CSV",
                            data=class_csv,
                            file_name=f"subject_class_analytics_{selected_subject_id}_{selected_exam_session_id}.csv",
                            mime="text/csv",
                            key=f"download_subject_class_{selected_subject_id}_{selected_exam_session_id}",
                            disabled=_loading(),
                        )
        else:
            st.info("No assigned subjects found for the selected class.")
    else:
        st.info("No class access found for subject analytics.")


def render_teacher_page(selected_page: str, teacher_id: str) -> None:
    ensure_page_config()
    _init_ui_state()

    if _loading():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Teacher Dashboard", "Manage enrollment, marks entry, and analytics from one workspace")

    schools = _teacher_schools(teacher_id)
    if schools:
        with card("School Context", "Active school access in the current session"):
            show_records("Active Session Schools", schools)

    if selected_page == "Student Enrollment":
        with card("Student Enrollment", "Enroll students as class incharge"):
            _render_student_enrollment(teacher_id)
        return
    if selected_page == "Results Entry":
        with card("Results Entry", "Upload, validate, and save marks"):
            _render_results_entry(teacher_id)
        return
    if selected_page == "School Analytics":
        with card("School Analytics", "Track student outcomes across class and subject"):
            _render_analytics_sections(teacher_id)
        return

    st.error("Access denied")
