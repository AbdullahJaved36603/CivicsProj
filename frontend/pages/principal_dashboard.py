from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import streamlit as st

from frontend.components.forms import build_option_map, form_heading, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload, show_simple_kv_table
from frontend.ui_theme import card, controls_disabled, ensure_page_config, pill_select, render_page_header, show_loading
from system_admin import service_layer
from system_admin.google_sheets_utils import safe_sheet_read


def _init_ui_state() -> None:
    if "is_loading" not in st.session_state:
        st.session_state["is_loading"] = False


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


def _principal_schools(principal_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"principal_schools::{principal_id}",
        fetch_func=lambda: service_layer.get_principal_schools(principal_id),
        data_key="schools",
        spinner_text="Loading schools...",
    )


def _selected_school(principal_id: str) -> Optional[Dict[str, Any]]:
    schools = _principal_schools(principal_id)
    if not schools:
        return None

    school_map = build_option_map(schools, "school_id", "school_name")
    labels = list(school_map.keys())
    selected_school_id = str(st.session_state.get("selected_school_id", "")).strip()

    default_index = 0
    if selected_school_id:
        for index, label in enumerate(labels):
            if get_select_value(school_map, label) == selected_school_id:
                default_index = index
                break

    selected_label = pill_select(
        "School Context",
        labels,
        key="principal_selected_school_label",
        default_index=default_index,
        disabled=_loading(),
    )
    resolved_school_id = get_select_value(school_map, selected_label)
    st.session_state["selected_school_id"] = resolved_school_id

    for school in schools:
        if str(school.get("school_id", "")) == resolved_school_id:
            return school
    return schools[0]


def _classes(school_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"principal_classes::{school_id}",
        fetch_func=lambda: service_layer.get_school_classes(school_id),
        data_key="classes",
        spinner_text="Loading classes...",
    )


def _teachers(school_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"principal_teachers::{school_id}",
        fetch_func=lambda: service_layer.get_school_teachers(school_id),
        data_key="teachers",
        spinner_text="Loading teachers...",
    )


def _subjects(school_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"principal_subjects::{school_id}",
        fetch_func=lambda: service_layer.get_school_subjects(school_id),
        data_key="subjects",
        spinner_text="Loading subjects...",
    )


def _assignments(school_id: str) -> List[Dict[str, Any]]:
    return _cached_read(
        cache_key=f"principal_assignments::{school_id}",
        fetch_func=lambda: service_layer.get_school_assignments(school_id),
        data_key="assignments",
        spinner_text="Loading assignments...",
    )


def _invalidate_school_cache(school_id: str) -> None:
    keys_to_clear = [
        f"principal_classes::{school_id}",
        f"principal_teachers::{school_id}",
        f"principal_subjects::{school_id}",
        f"principal_assignments::{school_id}",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


def _render_class_management(principal_id: str, school_id: str) -> None:
    form_heading("Class Management", "Create or delete classes")

    with st.form("create_class_form"):
        class_name = st.text_input("Class name", disabled=_loading())
        section = st.text_input("Section", disabled=_loading())
        submitted = st.form_submit_button("Create Class", disabled=_loading())
    if submitted:
        response = _safe_backend_call(
            lambda: service_layer.create_class(principal_id, school_id, class_name, section),
            "Creating class...",
        )
        show_form_result(response)
        show_response_payload(response)
        if response.get("success"):
            _invalidate_school_cache(school_id)

    classes = _classes(school_id)
    class_map = build_option_map(classes, "class_id", "class_name")
    if class_map:
        with st.form("delete_class_form"):
            selected_class = pill_select(
                "Class",
                list(class_map.keys()),
                key="principal_delete_class",
                disabled=_loading(),
            )
            submitted = st.form_submit_button("Delete Class", disabled=_loading())
        if submitted:
            class_id = get_select_value(class_map, selected_class)
            response = _safe_backend_call(
                lambda: service_layer.delete_class(principal_id, school_id, class_id),
                "Deleting class...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_school_cache(school_id)
    else:
        st.info("No classes available.")

    show_records("Classes", classes)


def _render_teacher_management(principal_id: str, school_id: str) -> None:
    form_heading("Teacher Management", "Create and deactivate teachers")

    with st.form("create_teacher_form"):
        username = st.text_input("Teacher username", disabled=_loading())
        submitted = st.form_submit_button("Create Teacher", disabled=_loading())
    if submitted:
        if not username.strip():
            st.error("Username cannot be empty")
            st.stop()
        response = _safe_backend_call(
            lambda: service_layer.create_teacher(principal_id, school_id, username),
            "Creating teacher...",
        )
        show_form_result(response)
        show_response_payload(response)
        if response.get("success"):
            _invalidate_school_cache(school_id)

    teachers = _teachers(school_id)
    teacher_map = build_option_map(teachers, "teacher_id", "username")
    if teacher_map:
        with st.form("deactivate_teacher_form"):
            selected_teacher = st.selectbox("Teacher", list(teacher_map.keys()), disabled=_loading())
            submitted = st.form_submit_button("Deactivate Teacher", disabled=_loading())
        if submitted:
            teacher_id = get_select_value(teacher_map, selected_teacher)
            response = _safe_backend_call(
                lambda: service_layer.delete_teacher(principal_id, school_id, teacher_id),
                "Deactivating teacher...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_school_cache(school_id)
    else:
        st.info("No teachers available.")

    show_records("Teachers", teachers)


def _render_subject_management(principal_id: str, school_id: str) -> None:
    form_heading("Subject Management", "Create subjects for classes")

    classes = _classes(school_id)
    class_map = build_option_map(classes, "class_id", "class_name")
    if not class_map:
        st.info("Create at least one class before adding subjects.")
        return

    with st.form("create_subject_form"):
        selected_class = pill_select(
            "Class",
            list(class_map.keys()),
            key="principal_create_subject_class",
            disabled=_loading(),
        )
        subject_name = st.text_input("Subject name", disabled=_loading())
        submitted = st.form_submit_button("Create Subject", disabled=_loading())
    if submitted:
        class_id = get_select_value(class_map, selected_class)
        response = _safe_backend_call(
            lambda: service_layer.create_subject(principal_id, school_id, class_id, subject_name),
            "Creating subject...",
        )
        show_form_result(response)
        show_response_payload(response)
        if response.get("success"):
            _invalidate_school_cache(school_id)

    subjects = _subjects(school_id)
    show_records("Subjects", subjects)


def _render_assignments(principal_id: str, school_id: str) -> None:
    form_heading("Teacher Assignments", "Assign teachers to class and subject")

    classes = _classes(school_id)
    teachers = _teachers(school_id)
    subjects = _subjects(school_id)

    class_map = build_option_map(classes, "class_id", "class_name")
    teacher_map = build_option_map(teachers, "teacher_id", "username")

    if class_map and teacher_map:
        selected_class_label = pill_select(
            "Class",
            list(class_map.keys()),
            key="principal_assign_class",
            disabled=_loading(),
        )
        selected_class_id = get_select_value(class_map, selected_class_label)
        filtered_subjects = [item for item in subjects if str(item.get("class_id", "")) == selected_class_id]
        subject_map = build_option_map(filtered_subjects, "subject_id", "subject_name")

        if subject_map:
            with st.form("assign_teacher_form"):
                selected_teacher = st.selectbox("Teacher", list(teacher_map.keys()), disabled=_loading())
                selected_subject = pill_select(
                    "Subject",
                    list(subject_map.keys()),
                    key="principal_assign_subject",
                    disabled=_loading(),
                )
                submitted = st.form_submit_button("Assign Teacher", disabled=_loading())
            if submitted:
                teacher_id = get_select_value(teacher_map, selected_teacher)
                subject_id = get_select_value(subject_map, selected_subject)
                response = _safe_backend_call(
                    lambda: service_layer.assign_teacher(principal_id, school_id, teacher_id, selected_class_id, subject_id),
                    "Assigning teacher...",
                )
                show_form_result(response)
                show_response_payload(response)
                if response.get("success"):
                    _invalidate_school_cache(school_id)
        else:
            st.info("No subjects available for the selected class.")
    else:
        st.info("Assignment requires teachers, classes, and subjects in this school.")

    assignments = _assignments(school_id)

    class_name_by_id = {
        str(item.get("class_id", "")): str(item.get("class_name", "")).strip()
        for item in classes
    }
    teacher_name_by_id = {
        str(item.get("teacher_id", "")): str(item.get("username", "")).strip()
        for item in teachers
    }
    subject_name_by_id = {
        str(item.get("subject_id", "")): str(item.get("subject_name", "")).strip()
        for item in subjects
    }

    display_assignments: List[Dict[str, Any]] = []
    for item in assignments:
        assignment_id = str(item.get("assignment_id", "")).strip()
        teacher_name = teacher_name_by_id.get(str(item.get("teacher_id", "")).strip(), "Teacher")
        class_name = class_name_by_id.get(str(item.get("class_id", "")).strip(), "Class")
        subject_name = subject_name_by_id.get(str(item.get("subject_id", "")).strip(), "Subject")
        display_assignments.append(
            {
                "assignment_id": assignment_id,
                "label": f"{teacher_name} -> {class_name} / {subject_name}",
                "teacher": teacher_name,
                "class": class_name,
                "subject": subject_name,
            }
        )

    assignment_map = build_option_map(display_assignments, "assignment_id", "label")
    if assignment_map:
        with st.form("deassign_teacher_form"):
            selected_assignment = st.selectbox("Assignment", list(assignment_map.keys()), disabled=_loading())
            submitted = st.form_submit_button("Remove Assignment", disabled=_loading())
        if submitted:
            assignment_id = get_select_value(assignment_map, selected_assignment)
            response = _safe_backend_call(
                lambda: service_layer.deassign_teacher(principal_id, school_id, assignment_id),
                "Removing assignment...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_school_cache(school_id)
    else:
        st.info("No assignments available.")

    show_records("Assignments", display_assignments)


def _render_class_incharge_management(principal_id: str, school_id: str) -> None:
    form_heading("Class Incharge", "Assign or remove class incharge teacher")

    classes = _classes(school_id)
    teachers = _teachers(school_id)
    class_map = build_option_map(classes, "class_id", "class_name")
    teacher_map = build_option_map(teachers, "teacher_id", "username")

    if class_map and teacher_map:
        with st.form("assign_class_incharge_form"):
            selected_class = pill_select(
                "Class",
                list(class_map.keys()),
                key="principal_incharge_class",
                disabled=_loading(),
            )
            selected_teacher = st.selectbox("Teacher", list(teacher_map.keys()), disabled=_loading())
            submitted = st.form_submit_button("Assign Incharge", disabled=_loading())
        if submitted:
            class_id = get_select_value(class_map, selected_class)
            teacher_id = get_select_value(teacher_map, selected_teacher)
            response = _safe_backend_call(
                lambda: service_layer.assign_class_incharge(principal_id, school_id, class_id, teacher_id),
                "Assigning class incharge...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_school_cache(school_id)
    else:
        st.info("Class incharge assignment requires classes and teachers in this school.")

    if class_map:
        with st.form("deassign_class_incharge_form"):
            selected_class = pill_select(
                "Class to clear incharge",
                list(class_map.keys()),
                key="principal_clear_incharge_class",
                disabled=_loading(),
            )
            submitted = st.form_submit_button("Remove Incharge", disabled=_loading())
        if submitted:
            class_id = get_select_value(class_map, selected_class)
            response = _safe_backend_call(
                lambda: service_layer.deassign_class_incharge(principal_id, school_id, class_id),
                "Removing class incharge...",
            )
            show_form_result(response)
            show_response_payload(response)
            if response.get("success"):
                _invalidate_school_cache(school_id)

    show_records("Classes", classes)


def render_principal_page(selected_page: str, principal_id: str) -> None:
    ensure_page_config()
    _init_ui_state()

    if _loading():
        st.warning("Please wait, loading data...")
        st.stop()

    render_page_header("Principal Dashboard", "Manage classes, teachers, assignments, and incharge mapping")

    school = _selected_school(principal_id)
    if not school:
        st.error("Access denied")
        return

    with card("School Context", "Selected school applies to all actions below"):
        session_label = str(school.get("session_name", "")).strip() or "Active Session"
        show_simple_kv_table(
            "School Context",
            {
                "school": school.get("school_name", ""),
                "session": session_label,
            },
        )

    school_id = str(school.get("school_id", ""))
    if selected_page == "Class Management":
        with card("Class Management", "Create and remove class records"):
            _render_class_management(principal_id, school_id)
        return
    if selected_page == "Subject Management":
        with card("Subject Management", "Assign subjects to classes"):
            _render_subject_management(principal_id, school_id)
        return
    if selected_page == "Teacher Management":
        with card("Teacher Management", "Create and deactivate teacher accounts"):
            _render_teacher_management(principal_id, school_id)
        return
    if selected_page == "Assignments":
        with card("Teacher Assignments", "Map teachers to classes and subjects"):
            _render_assignments(principal_id, school_id)
        return
    if selected_page == "Class Incharge":
        with card("Class Incharge", "Assign class incharge ownership"):
            _render_class_incharge_management(principal_id, school_id)
        return

    st.error("Access denied")
