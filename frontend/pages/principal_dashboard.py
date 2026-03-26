from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from frontend.components.forms import build_option_map, form_heading, get_select_value, show_form_result
from frontend.components.tables import show_records, show_response_payload, show_simple_kv_table
from system_admin import service_layer


def _principal_school(principal_id: str) -> Dict[str, Any]:
    response = service_layer.get_principal_school(principal_id)
    if not response.get("success"):
        return {}
    return response.get("data", {})


def _classes(school_id: str) -> List[Dict[str, Any]]:
    response = service_layer.get_school_classes(school_id)
    return response.get("data", {}).get("classes", []) if response.get("success") else []


def _teachers(school_id: str) -> List[Dict[str, Any]]:
    response = service_layer.get_school_teachers(school_id)
    return response.get("data", {}).get("teachers", []) if response.get("success") else []


def _subjects(school_id: str) -> List[Dict[str, Any]]:
    response = service_layer.get_school_subjects(school_id)
    return response.get("data", {}).get("subjects", []) if response.get("success") else []


def _assignments(school_id: str) -> List[Dict[str, Any]]:
    response = service_layer.get_school_assignments(school_id)
    return response.get("data", {}).get("assignments", []) if response.get("success") else []


def _render_class_management(principal_id: str, school_id: str) -> None:
    form_heading("Class Management", "Create or delete classes")

    with st.form("create_class_form"):
        class_name = st.text_input("Class name")
        section = st.text_input("Section")
        submitted = st.form_submit_button("Create Class")
    if submitted:
        response = service_layer.create_class(principal_id, class_name, section)
        show_form_result(response)
        show_response_payload(response)

    classes = _classes(school_id)
    class_map = build_option_map(classes, "class_id", "class_name")
    if class_map:
        with st.form("delete_class_form"):
            selected_class = st.selectbox("Class", list(class_map.keys()))
            submitted = st.form_submit_button("Delete Class")
        if submitted:
            class_id = get_select_value(class_map, selected_class)
            response = service_layer.delete_class(principal_id, class_id)
            show_form_result(response)
            show_response_payload(response)
    else:
        st.info("No classes available.")

    show_records("Classes", classes)


def _render_teacher_management(principal_id: str, school_id: str) -> None:
    form_heading("Teacher Management", "Create and deactivate teachers")

    with st.form("create_teacher_form"):
        username = st.text_input("Teacher username")
        submitted = st.form_submit_button("Create Teacher")
    if submitted:
        if not username.strip():
            st.error("Username cannot be empty")
            st.stop()
        response = service_layer.create_teacher(principal_id, username)
        show_form_result(response)
        show_response_payload(response)

    teachers = _teachers(school_id)
    teacher_map = build_option_map(teachers, "teacher_id", "username")
    if teacher_map:
        with st.form("deactivate_teacher_form"):
            selected_teacher = st.selectbox("Teacher", list(teacher_map.keys()))
            submitted = st.form_submit_button("Deactivate Teacher")
        if submitted:
            teacher_id = get_select_value(teacher_map, selected_teacher)
            response = service_layer.delete_teacher(principal_id, teacher_id)
            show_form_result(response)
            show_response_payload(response)
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
        selected_class = st.selectbox("Class", list(class_map.keys()))
        subject_name = st.text_input("Subject name")
        submitted = st.form_submit_button("Create Subject")
    if submitted:
        class_id = get_select_value(class_map, selected_class)
        response = service_layer.create_subject(principal_id, class_id, subject_name)
        show_form_result(response)
        show_response_payload(response)

    subjects = _subjects(school_id)
    show_records("Subjects", subjects)


def _render_assignments(principal_id: str, school_id: str) -> None:
    form_heading("Teacher Assignments", "Assign teachers to class and subject")

    classes = _classes(school_id)
    teachers = _teachers(school_id)
    subjects = _subjects(school_id)

    class_map = build_option_map(classes, "class_id", "class_name")
    teacher_map = build_option_map(teachers, "teacher_id", "username")
    subject_map = build_option_map(subjects, "subject_id", "subject_name")

    if class_map and teacher_map and subject_map:
        with st.form("assign_teacher_form"):
            selected_teacher = st.selectbox("Teacher", list(teacher_map.keys()))
            selected_class = st.selectbox("Class", list(class_map.keys()))
            selected_subject = st.selectbox("Subject", list(subject_map.keys()))
            submitted = st.form_submit_button("Assign Teacher")
        if submitted:
            teacher_id = get_select_value(teacher_map, selected_teacher)
            class_id = get_select_value(class_map, selected_class)
            subject_id = get_select_value(subject_map, selected_subject)
            response = service_layer.assign_teacher(principal_id, teacher_id, class_id, subject_id)
            show_form_result(response)
            show_response_payload(response)
    else:
        st.info("Assignment requires teachers, classes, and subjects in this school.")

    assignments = _assignments(school_id)
    assignment_map = build_option_map(assignments, "assignment_id", "assignment_id")
    if assignment_map:
        with st.form("deassign_teacher_form"):
            selected_assignment = st.selectbox("Assignment", list(assignment_map.keys()))
            submitted = st.form_submit_button("Remove Assignment")
        if submitted:
            assignment_id = get_select_value(assignment_map, selected_assignment)
            response = service_layer.deassign_teacher(principal_id, assignment_id)
            show_form_result(response)
            show_response_payload(response)
    else:
        st.info("No assignments available.")

    show_records("Assignments", assignments)


def render_principal_page(selected_page: str, principal_id: str) -> None:
    school = _principal_school(principal_id)
    if not school:
        st.error("Access denied")
        return

    show_simple_kv_table(
        "School Context",
        {
            "school_id": school.get("school_id", ""),
            "school_name": school.get("school_name", ""),
        },
    )

    school_id = str(school.get("school_id", ""))
    if selected_page == "Class Management":
        _render_class_management(principal_id, school_id)
        return
    if selected_page == "Subject Management":
        _render_subject_management(principal_id, school_id)
        return
    if selected_page == "Teacher Management":
        _render_teacher_management(principal_id, school_id)
        return
    if selected_page == "Assignments":
        _render_assignments(principal_id, school_id)
        return

    st.error("Access denied")
