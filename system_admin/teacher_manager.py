from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
    from .google_sheets_utils import (
        ABSENT_MARK_TOKEN,
        canonical_subject_name,
        classify_subject,
        evaluate_student_result,
        get_class_pass_ratio,
        is_absent_token,
        number_to_string,
        parse_marks,
        to_float,
    )
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller
    from google_sheets_utils import (
        ABSENT_MARK_TOKEN,
        canonical_subject_name,
        classify_subject,
        evaluate_student_result,
        get_class_pass_ratio,
        is_absent_token,
        number_to_string,
        parse_marks,
        to_float,
    )


TAB_SCHOOLS = "Schools"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"
TAB_TEACHERS = "teachers"
TAB_TEACHER_ASSIGNMENTS = "Teacher_Assignments"
TAB_EXAM_SESSIONS = "exam_sessions"
TAB_SESSIONS = "Sessions"
TAB_ACCOUNTS = "Accounts"

SCHOOL_STUDENTS_TAB = "Students"
SCHOOL_RESULTS_TAB = "Results"

SCHOOL_STUDENTS_HEADERS = ["student_id", "student_name", "gender", "parent_name", "class_id", "school_id"]
SCHOOL_RESULTS_HEADERS = [
    "exam_session_id",
    "student_id",
    "class_id",
    "subject_id",
    "marks",
    "total_marks",
    "subject_status",
    "subject_percentage",
    "subject_category",
    "pass_ratio",
    "failed_major_subjects",
    "failed_minor_subjects",
    "final_result",
    "entered_by",
    "modified_by",
    "updated_at",
]


class SchoolsColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1
    SESSION_ID = 2
    SCHOOL_SHEET_URL = 3


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1
    CLASS_NAME = 2
    CLASS_SECTION = 3
    CLASS_INCHARGE_TEACHER_ID = 4


class SubjectsColumns:
    SUBJECT_ID = 0
    CLASS_ID = 1
    SUBJECT_NAME = 2


class TeachersColumns:
    TEACHER_ID = 0
    SCHOOL_ID = 2
    SESSION_ID = 3


class TeacherAssignmentsColumns:
    ASSIGNMENT_ID = 0
    TEACHER_ID = 1
    SCHOOL_ID = 2
    CLASS_ID = 3
    SUBJECT_ID = 4


class ExamSessionColumns:
    EXAM_SESSION_ID = 0
    SESSION_ID = 1
    MONTH = 2


class AccountsColumns:
    USER_ID = 0
    ROLE = 3


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class TeacherManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()
        self._schema_ensured_school_sheet_ids: Set[str] = set()

    @staticmethod
    def _safe_get(row: List[str], index: Optional[int]) -> str:
        if index is None:
            return ""
        return row[index] if index < len(row) else ""

    @staticmethod
    def _normalize_header(value: str) -> str:
        return str(value).strip().lower().replace(" ", "_")

    def _header_index(self, headers: List[str], aliases: List[str]) -> Optional[int]:
        normalized_headers = [self._normalize_header(item) for item in headers]
        normalized_aliases = {self._normalize_header(item) for item in aliases}
        for index, header in enumerate(normalized_headers):
            if header in normalized_aliases:
                return index
        return None

    @staticmethod
    def _is_active(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "active"}

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        return to_float(value)

    @staticmethod
    def _is_absent_token(value: Any) -> bool:
        return is_absent_token(value)

    @staticmethod
    def _number_to_str(value: float) -> str:
        return number_to_string(value)

    @staticmethod
    def _class_label(class_name: str, class_section: str) -> str:
        return f"{str(class_name).strip()}{str(class_section).strip()}"

    def _get_active_session_id(self) -> Optional[str]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            session_id = self._safe_get(row, 0)
            is_active = self._safe_get(row, 2)
            if session_id and self._is_active(is_active):
                return session_id
        return None

    def _get_teacher_school_ids(self, teacher_id: str, session_id: str) -> List[str]:
        rows = self.controller.read_tab(TAB_TEACHERS)
        school_ids: List[str] = []
        for row in rows[1:]:
            row_teacher_id = self._safe_get(row, TeachersColumns.TEACHER_ID)
            row_school_id = self._safe_get(row, TeachersColumns.SCHOOL_ID)
            row_session_id = self._safe_get(row, TeachersColumns.SESSION_ID)
            if row_teacher_id == teacher_id and row_school_id and row_session_id == session_id:
                school_ids.append(row_school_id)
        return school_ids

    def _get_teacher_school_ids_active(self, teacher_id: str) -> List[str]:
        active_session_id = self._get_active_session_id()
        if not active_session_id:
            return []
        return self._get_teacher_school_ids(teacher_id, active_session_id)

    def _teacher_has_school_membership(self, teacher_id: str, school_id: str, session_id: str) -> bool:
        return school_id in set(self._get_teacher_school_ids(teacher_id, session_id))

    def _get_school_row(self, school_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_SCHOOLS)
        for row in rows[1:]:
            if self._safe_get(row, SchoolsColumns.SCHOOL_ID) == school_id:
                return row
        return None

    def _get_school_sheet_id(self, school_id: str) -> Optional[str]:
        school_row = self._get_school_row(school_id)
        if school_row is None:
            return None
        school_sheet_url = self._safe_get(school_row, SchoolsColumns.SCHOOL_SHEET_URL)
        return self.controller.get_school_sheet_id_from_url(school_sheet_url)

    def _get_class_row(self, class_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_CLASSES)
        for row in rows[1:]:
            if self._safe_get(row, ClassesColumns.CLASS_ID) == class_id:
                return row
        return None

    def _get_exam_session_row(self, exam_session_id: str) -> Optional[List[str]]:
        rows = self.controller.read_tab(TAB_EXAM_SESSIONS)
        for row in rows[1:]:
            if self._safe_get(row, ExamSessionColumns.EXAM_SESSION_ID) == exam_session_id:
                return row
        return None

    def _subject_belongs_to_class(self, subject_id: str, class_id: str) -> bool:
        rows = self.controller.read_tab(TAB_SUBJECTS)
        for row in rows[1:]:
            if (
                self._safe_get(row, SubjectsColumns.SUBJECT_ID) == subject_id
                and self._safe_get(row, SubjectsColumns.CLASS_ID) == class_id
            ):
                return True
        return False

    def _teacher_has_assignment(self, teacher_id: str, school_id: str, class_id: str, subject_id: str) -> bool:
        rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
        for row in rows[1:]:
            if (
                self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID) == teacher_id
                and self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID) == school_id
                and self._safe_get(row, TeacherAssignmentsColumns.CLASS_ID) == class_id
                and self._safe_get(row, TeacherAssignmentsColumns.SUBJECT_ID) == subject_id
            ):
                return True
        return False

    def _teacher_has_subject_assignment(self, teacher_id: str, school_id: str, subject_id: str) -> bool:
        rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
        for row in rows[1:]:
            if (
                self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID) == teacher_id
                and self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID) == school_id
                and self._safe_get(row, TeacherAssignmentsColumns.SUBJECT_ID) == subject_id
            ):
                return True
        return False

    def _teacher_has_class_access(self, teacher_id: str, school_id: str, class_id: str) -> bool:
        class_row = self._get_class_row(class_id)
        if class_row is not None:
            row_school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            row_incharge_id = self._safe_get(class_row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID)
            if row_school_id == school_id and row_incharge_id == teacher_id:
                return True

        rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
        for row in rows[1:]:
            if (
                self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID) == teacher_id
                and self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID) == school_id
                and self._safe_get(row, TeacherAssignmentsColumns.CLASS_ID) == class_id
            ):
                return True
        return False

    def _is_admin_user(self, user_id: str) -> bool:
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id:
            return False

        rows = self.controller.read_tab(TAB_ACCOUNTS)
        for row in rows[1:]:
            row_user_id = self._safe_get(row, AccountsColumns.USER_ID)
            if row_user_id != normalized_user_id:
                continue
            role_value = self._safe_get(row, AccountsColumns.ROLE).strip().lower()
            return role_value in {"admin", "super_user", "superuser"}
        return False

    def _teacher_can_edit_subject(self, actor_id: str, school_id: str, class_id: str, subject_id: str) -> bool:
        if self._is_admin_user(actor_id):
            return True

        class_row = self._get_class_row(class_id)
        if class_row is not None:
            row_school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            row_incharge_id = self._safe_get(class_row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID)
            if row_school_id == school_id and row_incharge_id == actor_id:
                return True

        return self._teacher_has_assignment(actor_id, school_id, class_id, subject_id)

    def _ensure_school_tabs(self, school_sheet_id: str) -> Dict[str, Any]:
        if school_sheet_id in self._schema_ensured_school_sheet_ids:
            return _response(True, "School worksheet schema already ensured.")

        students_result = self.controller.ensure_tab_with_headers(
            school_sheet_id,
            SCHOOL_STUDENTS_TAB,
            SCHOOL_STUDENTS_HEADERS,
        )
        if not students_result.get("success"):
            return students_result

        results_result = self.controller.ensure_tab_with_headers(
            school_sheet_id,
            SCHOOL_RESULTS_TAB,
            SCHOOL_RESULTS_HEADERS,
        )
        if not results_result.get("success"):
            return results_result

        self._schema_ensured_school_sheet_ids.add(school_sheet_id)

        return _response(True, "School worksheet schema ensured.")

    def _read_students_dataframe(self, school_sheet_id: str) -> pd.DataFrame:
        rows = self.controller.read_tab_from_spreadsheet(school_sheet_id, SCHOOL_STUDENTS_TAB)
        if not rows:
            return pd.DataFrame(columns=SCHOOL_STUDENTS_HEADERS)

        headers = rows[0]
        student_id_index = self._header_index(headers, ["student_id"])
        student_name_index = self._header_index(headers, ["student_name"])
        gender_index = self._header_index(headers, ["gender", "sex"])
        parent_name_index = self._header_index(headers, ["parent_name", "guardian_name"])
        class_id_index = self._header_index(headers, ["class_id"])
        school_id_index = self._header_index(headers, ["school_id"])

        items: List[Dict[str, str]] = []
        for row in rows[1:]:
            student_id = self._safe_get(row, student_id_index)
            if not student_id:
                continue
            items.append(
                {
                    "student_id": student_id,
                    "student_name": self._safe_get(row, student_name_index),
                    "gender": self._safe_get(row, gender_index) or "Unknown",
                    "parent_name": self._safe_get(row, parent_name_index),
                    "class_id": self._safe_get(row, class_id_index),
                    "school_id": self._safe_get(row, school_id_index),
                }
            )

        students_df = pd.DataFrame(items)
        if students_df.empty:
            return pd.DataFrame(columns=SCHOOL_STUDENTS_HEADERS)

        students_df["gender"] = (
            students_df["gender"]
            .astype(str)
            .str.strip()
            .str.title()
            .replace({"M": "Male", "F": "Female"})
        )
        return students_df

    def _read_results_dataframe(self, school_sheet_id: str) -> pd.DataFrame:
        rows = self.controller.read_tab_from_spreadsheet(school_sheet_id, SCHOOL_RESULTS_TAB)
        if not rows:
            return pd.DataFrame(columns=SCHOOL_RESULTS_HEADERS)

        headers = rows[0]
        exam_index = self._header_index(headers, ["exam_session_id"])
        student_index = self._header_index(headers, ["student_id"])
        class_index = self._header_index(headers, ["class_id"])
        subject_index = self._header_index(headers, ["subject_id"])
        marks_index = self._header_index(headers, ["marks", "score"])
        total_index = self._header_index(headers, ["total_marks", "max_marks"])
        subject_status_index = self._header_index(headers, ["subject_status", "status"])
        subject_percentage_index = self._header_index(headers, ["subject_percentage", "percentage"])
        subject_category_index = self._header_index(headers, ["subject_category", "category"])
        pass_ratio_index = self._header_index(headers, ["pass_ratio", "passing_ratio", "pass_marks_ratio"])
        failed_major_index = self._header_index(headers, ["failed_major_subjects", "failed_major"])
        failed_minor_index = self._header_index(headers, ["failed_minor_subjects", "failed_minor"])
        final_result_index = self._header_index(headers, ["final_result", "final_status", "promotion_status"])
        entered_by_index = self._header_index(headers, ["entered_by", "created_by"])
        modified_by_index = self._header_index(headers, ["modified_by", "updated_by"])
        updated_at_index = self._header_index(headers, ["updated_at", "modified_at", "last_updated_at"])

        items: List[Dict[str, Any]] = []
        for row in rows[1:]:
            exam_session_id = self._safe_get(row, exam_index)
            student_id = self._safe_get(row, student_index)
            class_id = self._safe_get(row, class_index)
            subject_id = self._safe_get(row, subject_index)
            if not exam_session_id or not student_id or not class_id or not subject_id:
                continue
            marks_value = self._safe_get(row, marks_index)
            total_value = self._safe_get(row, total_index)
            if total_index is None and marks_value:
                total_value = "100"
            if (not str(total_value).strip()) and str(marks_value).strip() and (not self._is_absent_token(marks_value)):
                total_value = "100"
            items.append(
                {
                    "exam_session_id": exam_session_id,
                    "student_id": student_id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "marks": marks_value,
                    "total_marks": total_value,
                    "subject_status": self._safe_get(row, subject_status_index),
                    "subject_percentage": self._safe_get(row, subject_percentage_index),
                    "subject_category": self._safe_get(row, subject_category_index),
                    "pass_ratio": self._safe_get(row, pass_ratio_index),
                    "failed_major_subjects": self._safe_get(row, failed_major_index),
                    "failed_minor_subjects": self._safe_get(row, failed_minor_index),
                    "final_result": self._safe_get(row, final_result_index),
                    "entered_by": self._safe_get(row, entered_by_index),
                    "modified_by": self._safe_get(row, modified_by_index),
                    "updated_at": self._safe_get(row, updated_at_index),
                }
            )

        results_df = pd.DataFrame(items)
        if results_df.empty:
            return pd.DataFrame(columns=SCHOOL_RESULTS_HEADERS)

        for column in ["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]:
            results_df[column] = results_df[column].astype(str).str.strip()

        for column, default_value in {
            "subject_status": "",
            "subject_percentage": "",
            "subject_category": "",
            "pass_ratio": "",
            "failed_major_subjects": "",
            "failed_minor_subjects": "",
            "final_result": "",
            "entered_by": "",
            "modified_by": "",
            "updated_at": "",
        }.items():
            if column not in results_df.columns:
                results_df[column] = default_value
            results_df[column] = results_df[column].astype(str).fillna(default_value).str.strip()

        results_df["marks"] = results_df.apply(
            lambda row: parse_marks(row.get("marks", ""), row.get("total_marks", "")).get("normalized_marks", ABSENT_MARK_TOKEN),
            axis=1,
        )
        results_df["total_marks"] = results_df.apply(
            lambda row: (
                parse_marks(row.get("marks", ""), row.get("total_marks", "")).get("normalized_total_marks", "")
                or str(row.get("total_marks", "")).strip()
            ),
            axis=1,
        )

        results_df = results_df.drop_duplicates(
            subset=["exam_session_id", "student_id", "class_id", "subject_id"], keep="last"
        )
        return results_df

    def _write_results_dataframe(self, school_sheet_id: str, results_df: pd.DataFrame) -> None:
        ordered_df = results_df.copy()
        if ordered_df.empty:
            values: List[List[str]] = [SCHOOL_RESULTS_HEADERS]
        else:
            for column in SCHOOL_RESULTS_HEADERS:
                if column not in ordered_df.columns:
                    ordered_df[column] = ""

            for column in ["exam_session_id", "student_id", "class_id", "subject_id"]:
                ordered_df[column] = ordered_df[column].astype(str).str.strip()

            ordered_df["marks"] = ordered_df["marks"].astype(str).str.strip()
            ordered_df["total_marks"] = ordered_df["total_marks"].astype(str).str.strip()
            for column in [
                "subject_status",
                "subject_percentage",
                "subject_category",
                "pass_ratio",
                "failed_major_subjects",
                "failed_minor_subjects",
                "final_result",
                "entered_by",
                "modified_by",
                "updated_at",
            ]:
                ordered_df[column] = ordered_df[column].astype(str).str.strip()

            ordered_df = ordered_df.drop_duplicates(
                subset=["exam_session_id", "student_id", "class_id", "subject_id"], keep="last"
            )
            ordered_df = ordered_df.sort_values(
                by=["exam_session_id", "class_id", "subject_id", "student_id"],
                ignore_index=True,
            )

            values = [SCHOOL_RESULTS_HEADERS]
            for _, row in ordered_df.iterrows():
                parsed = parse_marks(row.get("marks", ""), row.get("total_marks", ""))
                normalized_marks = parsed.get("normalized_marks", ABSENT_MARK_TOKEN)
                normalized_total = parsed.get("normalized_total_marks", "") or str(row.get("total_marks", "")).strip()
                values.append(
                    [
                        str(row.get("exam_session_id", "")),
                        str(row.get("student_id", "")),
                        str(row.get("class_id", "")),
                        str(row.get("subject_id", "")),
                        normalized_marks or ABSENT_MARK_TOKEN,
                        normalized_total,
                        str(row.get("subject_status", "")),
                        str(row.get("subject_percentage", "")),
                        str(row.get("subject_category", "")),
                        str(row.get("pass_ratio", "")),
                        str(row.get("failed_major_subjects", "")),
                        str(row.get("failed_minor_subjects", "")),
                        str(row.get("final_result", "")),
                        str(row.get("entered_by", "")),
                        str(row.get("modified_by", "")),
                        str(row.get("updated_at", "")),
                    ]
                )

        self.controller.replace_tab_values_in_spreadsheet(
            school_sheet_id,
            SCHOOL_RESULTS_TAB,
            values,
        )

    def _subject_name_by_id_for_class(self, class_id: str) -> Dict[str, str]:
        rows = self.controller.read_tab(TAB_SUBJECTS)
        mapping: Dict[str, str] = {}
        for row in rows[1:]:
            row_subject_id = self._safe_get(row, SubjectsColumns.SUBJECT_ID)
            row_class_id = self._safe_get(row, SubjectsColumns.CLASS_ID)
            if row_class_id != class_id or not row_subject_id:
                continue
            mapping[row_subject_id] = self._safe_get(row, SubjectsColumns.SUBJECT_NAME)
        return mapping

    def _apply_student_result_rules(
        self,
        results_df: pd.DataFrame,
        class_id: str,
        exam_session_id: str,
        class_name: str,
        subject_name_by_id: Dict[str, str],
    ) -> pd.DataFrame:
        if results_df.empty:
            return results_df

        scoped_mask = (
            (results_df["class_id"] == class_id)
            & (results_df["exam_session_id"] == exam_session_id)
        )
        scoped_df = results_df[scoped_mask].copy()
        if scoped_df.empty:
            return results_df

        pass_ratio = get_class_pass_ratio(class_name)
        for student_id in sorted(set(scoped_df["student_id"].astype(str).tolist())):
            student_mask = scoped_mask & (results_df["student_id"] == student_id)
            student_rows = results_df[student_mask].copy()
            if student_rows.empty:
                continue

            subject_rows: List[Dict[str, Any]] = []
            for _, row in student_rows.iterrows():
                subject_id = str(row.get("subject_id", "")).strip()
                subject_name = subject_name_by_id.get(subject_id, subject_id)
                subject_rows.append(
                    {
                        "subject_id": subject_id,
                        "subject_name": subject_name,
                        "marks": row.get("marks", ""),
                        "total_marks": row.get("total_marks", ""),
                    }
                )

            evaluation = evaluate_student_result(class_name, subject_rows)
            final_status = str(evaluation.get("final_status", "Promoted"))
            failed_major_subjects = int(evaluation.get("failed_major_subjects", 0) or 0)
            failed_minor_subjects = int(evaluation.get("failed_minor_subjects", 0) or 0)

            status_by_subject: Dict[str, Dict[str, Any]] = {
                str(item.get("canonical_subject_name", "")): item
                for item in evaluation.get("subject_rows", [])
            }

            for row_index in results_df[student_mask].index:
                subject_id = str(results_df.at[row_index, "subject_id"]).strip()
                subject_name = subject_name_by_id.get(subject_id, subject_id)
                subject_key = canonical_subject_name(subject_name)

                parsed = parse_marks(
                    results_df.at[row_index, "marks"],
                    results_df.at[row_index, "total_marks"],
                    passing_ratio=pass_ratio,
                )

                subject_status = "Fail"
                subject_percentage = 0.0
                if parsed.get("status") == "Pass":
                    subject_status = "Pass"
                percentage_value = parsed.get("percentage")
                if percentage_value is not None:
                    subject_percentage = round(float(percentage_value), 2)

                subject_category = classify_subject(subject_name).title()

                evaluated_subject = status_by_subject.get(subject_key, {})
                if evaluated_subject:
                    subject_status = str(evaluated_subject.get("subject_status", subject_status))
                    subject_percentage = float(evaluated_subject.get("subject_percentage", subject_percentage) or 0.0)
                    subject_category = str(evaluated_subject.get("subject_category", subject_category))

                results_df.at[row_index, "subject_status"] = subject_status
                results_df.at[row_index, "subject_percentage"] = number_to_string(subject_percentage)
                results_df.at[row_index, "subject_category"] = subject_category
                results_df.at[row_index, "pass_ratio"] = number_to_string(pass_ratio * 100)
                results_df.at[row_index, "failed_major_subjects"] = str(failed_major_subjects)
                results_df.at[row_index, "failed_minor_subjects"] = str(failed_minor_subjects)
                results_df.at[row_index, "final_result"] = final_status

        return results_df

    def get_teacher_classes(self, teacher_id: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")

            active_school_ids = set(self._get_teacher_school_ids_active(normalized_teacher_id))
            if not active_school_ids:
                return _response(False, "Teacher is not assigned to any school.")

            classes_rows = self.controller.read_tab(TAB_CLASSES)
            assignment_rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
            schools_rows = self.controller.read_tab(TAB_SCHOOLS)

            school_name_by_id = {
                self._safe_get(row, SchoolsColumns.SCHOOL_ID): self._safe_get(row, SchoolsColumns.SCHOOL_NAME)
                for row in schools_rows[1:]
            }

            assigned_class_ids = {
                self._safe_get(row, TeacherAssignmentsColumns.CLASS_ID)
                for row in assignment_rows[1:]
                if self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID) == normalized_teacher_id
                and self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID) in active_school_ids
            }

            classes: List[Dict[str, str]] = []
            for row in classes_rows[1:]:
                class_id = self._safe_get(row, ClassesColumns.CLASS_ID)
                row_school_id = self._safe_get(row, ClassesColumns.SCHOOL_ID)
                if row_school_id not in active_school_ids:
                    continue

                class_name = self._safe_get(row, ClassesColumns.CLASS_NAME)
                class_section = self._safe_get(row, ClassesColumns.CLASS_SECTION)
                incharge_id = self._safe_get(row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID)
                is_incharge = incharge_id == normalized_teacher_id
                is_assigned = class_id in assigned_class_ids
                if not is_incharge and not is_assigned:
                    continue

                access_parts: List[str] = []
                if is_incharge:
                    access_parts.append("incharge")
                if is_assigned:
                    access_parts.append("assigned")

                classes.append(
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "class_section": class_section,
                        "class_label": self._class_label(class_name, class_section),
                        "school_id": row_school_id,
                        "school_name": school_name_by_id.get(row_school_id, ""),
                        "access": "+".join(access_parts),
                    }
                )

            return _response(True, "Teacher classes fetched successfully.", {"classes": classes})
        except Exception as exc:
            return _response(False, f"Failed to fetch teacher classes: {exc}")

    def get_teacher_subjects(self, teacher_id: str, class_id: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_class_id = class_id.strip()
            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")

            class_row = self._get_class_row(normalized_class_id)
            if class_row is None:
                return _response(False, "Class does not exist.")

            school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            active_session_id = self._get_active_session_id()
            if not school_id or not active_session_id:
                return _response(False, "Teacher is not assigned to any school.")
            has_admin_access = self._is_admin_user(normalized_teacher_id)
            if (not has_admin_access) and (not self._teacher_has_school_membership(normalized_teacher_id, school_id, active_session_id)):
                return _response(False, "Access denied")

            if (not has_admin_access) and (not self._teacher_has_class_access(normalized_teacher_id, school_id, normalized_class_id)):
                return _response(False, "Access denied")

            subject_rows = self.controller.read_tab(TAB_SUBJECTS)
            class_subjects: List[Dict[str, str]] = []
            for row in subject_rows[1:]:
                row_subject_id = self._safe_get(row, SubjectsColumns.SUBJECT_ID)
                row_class_id = self._safe_get(row, SubjectsColumns.CLASS_ID)
                if row_class_id != normalized_class_id or not row_subject_id:
                    continue
                class_subjects.append(
                    {
                        "subject_id": row_subject_id,
                        "subject_name": self._safe_get(row, SubjectsColumns.SUBJECT_NAME),
                    }
                )

            incharge_teacher_id = self._safe_get(class_row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID)
            is_incharge = incharge_teacher_id == normalized_teacher_id

            subjects: List[Dict[str, str]] = []
            if has_admin_access or is_incharge:
                subjects = class_subjects
            else:
                assignments_rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)
                class_subject_name_by_id = {
                    item.get("subject_id", ""): item.get("subject_name", "")
                    for item in class_subjects
                }
                seen_subjects = set()
                for row in assignments_rows[1:]:
                    row_teacher_id = self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID)
                    row_school_id = self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID)
                    row_class_id = self._safe_get(row, TeacherAssignmentsColumns.CLASS_ID)
                    row_subject_id = self._safe_get(row, TeacherAssignmentsColumns.SUBJECT_ID)
                    if row_teacher_id != normalized_teacher_id or row_school_id != school_id or row_class_id != normalized_class_id:
                        continue
                    if not row_subject_id or row_subject_id in seen_subjects:
                        continue
                    seen_subjects.add(row_subject_id)
                    subjects.append(
                        {
                            "subject_id": row_subject_id,
                            "subject_name": class_subject_name_by_id.get(row_subject_id, ""),
                        }
                    )

            return _response(True, "Teacher subjects fetched successfully.", {"subjects": subjects})
        except Exception as exc:
            return _response(False, f"Failed to fetch teacher subjects: {exc}")

    def get_exam_sessions_for_teacher(self, teacher_id: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")

            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")

            active_school_ids = set(self._get_teacher_school_ids(normalized_teacher_id, active_session_id))
            if not active_school_ids:
                return _response(False, "Teacher is not assigned to any school.")

            rows = self.controller.read_tab(TAB_EXAM_SESSIONS)
            sessions: List[Dict[str, str]] = []
            for row in rows[1:]:
                row_session_id = self._safe_get(row, ExamSessionColumns.SESSION_ID)
                if row_session_id != active_session_id:
                    continue
                sessions.append(
                    {
                        "exam_session_id": self._safe_get(row, ExamSessionColumns.EXAM_SESSION_ID),
                        "session_id": row_session_id,
                        "month": self._safe_get(row, ExamSessionColumns.MONTH),
                    }
                )

            return _response(True, "Exam sessions fetched successfully.", {"exam_sessions": sessions})
        except Exception as exc:
            return _response(False, f"Failed to fetch exam sessions: {exc}")

    def get_students_for_class(self, teacher_id: str, class_id: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_class_id = class_id.strip()
            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")

            class_row = self._get_class_row(normalized_class_id)
            if class_row is None:
                return _response(False, "Class does not exist.")
            class_school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)

            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")
            if not self._teacher_has_school_membership(normalized_teacher_id, class_school_id, active_session_id):
                return _response(False, "Access denied")
            if not self._teacher_has_class_access(normalized_teacher_id, class_school_id, normalized_class_id):
                return _response(False, "Access denied")

            school_sheet_id = self._get_school_sheet_id(class_school_id)
            if not school_sheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            ensure_result = self._ensure_school_tabs(school_sheet_id)
            if not ensure_result.get("success"):
                return ensure_result

            students_df = self._read_students_dataframe(school_sheet_id)
            students_df = students_df[students_df["class_id"] == normalized_class_id].copy()

            students: List[Dict[str, str]] = []
            for _, row in students_df.iterrows():
                students.append(
                    {
                        "student_id": str(row.get("student_id", "")),
                        "student_name": str(row.get("student_name", "")),
                        "gender": str(row.get("gender", "Unknown")),
                        "parent_name": str(row.get("parent_name", "")),
                        "class_id": str(row.get("class_id", "")),
                        "school_id": str(row.get("school_id", "")),
                    }
                )

            return _response(True, "Students fetched successfully.", {"students": students})
        except Exception as exc:
            return _response(False, f"Failed to fetch students: {exc}")

    def enroll_student(self, teacher_id: str, class_id: str, student_name: str, gender: str, parent_name: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_class_id = class_id.strip()
            normalized_student_name = student_name.strip()
            normalized_gender_input = gender.strip().lower()
            gender_by_value = {"male": "Male", "female": "Female"}
            normalized_gender = gender_by_value.get(normalized_gender_input, "")
            normalized_parent_name = parent_name.strip()

            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_student_name:
                return _response(False, "student_name is required.")
            if not normalized_gender:
                return _response(False, "gender must be Male or Female.")
            if not normalized_parent_name:
                return _response(False, "parent_name is required.")

            class_row = self._get_class_row(normalized_class_id)
            if class_row is None:
                return _response(False, "Class does not exist.")

            class_school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")
            if not self._teacher_has_school_membership(normalized_teacher_id, class_school_id, active_session_id):
                return _response(False, "Access denied")

            class_incharge_teacher_id = self._safe_get(class_row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID)
            if class_incharge_teacher_id != normalized_teacher_id:
                return _response(False, "Access denied")

            school_sheet_id = self._get_school_sheet_id(class_school_id)
            if not school_sheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            ensure_result = self._ensure_school_tabs(school_sheet_id)
            if not ensure_result.get("success"):
                return ensure_result

            students_df = self._read_students_dataframe(school_sheet_id)
            duplicate_df = students_df[
                (students_df["class_id"] == normalized_class_id)
                & (students_df["student_name"].astype(str).str.strip().str.lower() == normalized_student_name.lower())
                & (students_df["parent_name"].astype(str).str.strip().str.lower() == normalized_parent_name.lower())
            ]
            if not duplicate_df.empty:
                return _response(False, "Student with the same name and parent already exists in this class.")

            student_id = self.controller.generate_next_id(
                "ST",
                SCHOOL_STUDENTS_TAB,
                0,
                spreadsheet_id=school_sheet_id,
            )
            self.controller.append_row_to_spreadsheet(
                school_sheet_id,
                SCHOOL_STUDENTS_TAB,
                [
                    student_id,
                    normalized_student_name,
                    normalized_gender,
                    normalized_parent_name,
                    normalized_class_id,
                    class_school_id,
                ],
            )

            return _response(
                True,
                "Student enrolled successfully.",
                {
                    "student_id": student_id,
                    "school_id": class_school_id,
                    "class_id": normalized_class_id,
                    "student_name": normalized_student_name,
                    "gender": normalized_gender,
                    "parent_name": normalized_parent_name,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to enroll student: {exc}")

    def get_marks_entry_grid(
        self,
        teacher_id: str,
        class_id: str,
        subject_id: str,
        exam_session_id: str,
    ) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_class_id = class_id.strip()
            normalized_subject_id = subject_id.strip()
            normalized_exam_session_id = exam_session_id.strip()

            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_subject_id:
                return _response(False, "subject_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            class_row = self._get_class_row(normalized_class_id)
            if class_row is None:
                return _response(False, "Class does not exist.")

            school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")
            has_admin_access = self._is_admin_user(normalized_teacher_id)
            if (not has_admin_access) and (not self._teacher_has_school_membership(normalized_teacher_id, school_id, active_session_id)):
                return _response(False, "Access denied")
            if not self._teacher_can_edit_subject(normalized_teacher_id, school_id, normalized_class_id, normalized_subject_id):
                return _response(False, "Access denied")

            exam_session_row = self._get_exam_session_row(normalized_exam_session_id)
            if exam_session_row is None:
                return _response(False, "exam_session_id does not exist.")
            if self._safe_get(exam_session_row, ExamSessionColumns.SESSION_ID) != active_session_id:
                return _response(False, "Access denied")

            school_sheet_id = self._get_school_sheet_id(school_id)
            if not school_sheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            ensure_result = self._ensure_school_tabs(school_sheet_id)
            if not ensure_result.get("success"):
                return ensure_result

            students_df = self._read_students_dataframe(school_sheet_id)
            students_df = students_df[students_df["class_id"] == normalized_class_id].copy()

            results_df = self._read_results_dataframe(school_sheet_id)
            result_scope = results_df[
                (results_df["exam_session_id"] == normalized_exam_session_id)
                & (results_df["class_id"] == normalized_class_id)
                & (results_df["subject_id"] == normalized_subject_id)
            ][["student_id", "marks", "total_marks"]].copy()

            merged_df = students_df.merge(result_scope, on="student_id", how="left")
            merged_df = merged_df.sort_values(by=["student_name", "student_id"], ignore_index=True)

            inferred_total_marks = ""
            if not result_scope.empty:
                for _, result_row in result_scope.iterrows():
                    parsed = parse_marks(result_row.get("marks", ""), result_row.get("total_marks", ""))
                    candidate_total = str(parsed.get("normalized_total_marks", "")).strip()
                    if candidate_total:
                        inferred_total_marks = candidate_total

            rows: List[Dict[str, Any]] = []
            for _, row in merged_df.iterrows():
                marks_value = row.get("marks", "")
                total_value = row.get("total_marks", inferred_total_marks)
                if pd.isna(marks_value):
                    marks_display = ABSENT_MARK_TOKEN
                else:
                    parsed = parse_marks(marks_value, total_value)
                    if parsed.get("status") == "Absent":
                        marks_display = ABSENT_MARK_TOKEN
                    else:
                        marks_display = str(parsed.get("normalized_marks", ABSENT_MARK_TOKEN))
                rows.append(
                    {
                        "student_id": str(row.get("student_id", "")),
                        "student_name": str(row.get("student_name", "")),
                        "parent_name": str(row.get("parent_name", "")),
                        "gender": str(row.get("gender", "Unknown")),
                        "marks": marks_display,
                    }
                )

            return _response(
                True,
                "Marks entry grid fetched successfully.",
                {
                    "teacher_id": normalized_teacher_id,
                    "school_id": school_id,
                    "class_id": normalized_class_id,
                    "subject_id": normalized_subject_id,
                    "exam_session_id": normalized_exam_session_id,
                    "total_marks": inferred_total_marks,
                    "rows": rows,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch marks entry grid: {exc}")

    def save_marks(
        self,
        teacher_id: str,
        subject_id: str,
        class_id: str,
        exam_session_id: str,
        total_marks: str,
        edited_dataframe: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_subject_id = subject_id.strip()
            normalized_class_id = class_id.strip()
            normalized_exam_session_id = exam_session_id.strip()
            total_marks_value = self._to_float(total_marks)

            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_subject_id:
                return _response(False, "subject_id is required.")
            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")
            if total_marks_value is None or total_marks_value <= 0:
                return _response(False, "total_marks must be greater than zero.")

            class_row = self._get_class_row(normalized_class_id)
            if class_row is None:
                return _response(False, "Class does not exist.")

            school_id = self._safe_get(class_row, ClassesColumns.SCHOOL_ID)
            class_name = self._safe_get(class_row, ClassesColumns.CLASS_NAME)
            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")
            has_admin_access = self._is_admin_user(normalized_teacher_id)
            if (not has_admin_access) and (not self._teacher_has_school_membership(normalized_teacher_id, school_id, active_session_id)):
                return _response(False, "Access denied")
            if not self._teacher_can_edit_subject(normalized_teacher_id, school_id, normalized_class_id, normalized_subject_id):
                return _response(False, "Access denied")
            if not self._subject_belongs_to_class(normalized_subject_id, normalized_class_id):
                return _response(False, "Subject does not belong to class.")

            exam_session_row = self._get_exam_session_row(normalized_exam_session_id)
            if exam_session_row is None:
                return _response(False, "exam_session_id does not exist.")
            if self._safe_get(exam_session_row, ExamSessionColumns.SESSION_ID) != active_session_id:
                return _response(False, "Access denied")

            school_sheet_id = self._get_school_sheet_id(school_id)
            if not school_sheet_id:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            ensure_result = self._ensure_school_tabs(school_sheet_id)
            if not ensure_result.get("success"):
                return ensure_result

            students_df = self._read_students_dataframe(school_sheet_id)
            students_scope = students_df[students_df["class_id"] == normalized_class_id].copy()
            valid_student_ids = set(students_scope["student_id"].astype(str).tolist())
            if not valid_student_ids:
                return _response(False, "No students found in selected class.")

            incoming_df = pd.DataFrame(edited_dataframe or [])
            if incoming_df.empty:
                incoming_df = pd.DataFrame(
                    {
                        "student_id": sorted(valid_student_ids),
                        "marks": [""] * len(valid_student_ids),
                    }
                )

            if "student_id" not in incoming_df.columns:
                return _response(False, "edited_dataframe must include student_id column.")

            if "marks" not in incoming_df.columns:
                incoming_df["marks"] = ""

            incoming_df["student_id"] = incoming_df["student_id"].astype(str).str.strip()
            unknown_ids = sorted(set(incoming_df["student_id"].tolist()) - valid_student_ids)
            if unknown_ids:
                return _response(False, f"Students do not belong to selected class: {', '.join(unknown_ids)}")

            incoming_df = incoming_df.drop_duplicates(subset=["student_id"], keep="last").copy()
            incoming_df["marks_text"] = incoming_df["marks"].astype(str).str.strip()

            parse_errors = {
                "marks_not_numeric": "Marks must be numeric or use A/Absent.",
                "marks_negative": "Marks cannot be negative.",
                "total_marks_invalid": "total_marks must be greater than zero.",
                "marks_exceed_total": "Marks cannot be greater than total_marks.",
            }
            pass_ratio = get_class_pass_ratio(class_name)
            subject_name_by_id = self._subject_name_by_id_for_class(normalized_class_id)
            subject_name = subject_name_by_id.get(normalized_subject_id, normalized_subject_id)
            subject_category = classify_subject(subject_name).title()

            parsed_rows: List[Dict[str, Any]] = []
            for _, incoming_row in incoming_df.iterrows():
                student_value = str(incoming_row.get("student_id", "")).strip()
                marks_value = incoming_row.get("marks_text", "")
                parsed = parse_marks(marks_value, total_marks_value, passing_ratio=pass_ratio)
                if not parsed.get("is_valid", False):
                    error_key = str(parsed.get("error", "")).strip()
                    error_message = parse_errors.get(error_key, "Invalid marks value.")
                    return _response(False, f"Invalid marks for student {student_value}: {error_message}")

                percentage_value = parsed.get("percentage")
                percentage = round(float(percentage_value), 2) if percentage_value is not None else 0.0
                parsed_status = str(parsed.get("status", "Absent"))
                subject_status = "Pass" if parsed_status == "Pass" else "Fail"

                parsed_rows.append(
                    {
                        "student_id": student_value,
                        "marks": str(parsed.get("normalized_marks", ABSENT_MARK_TOKEN)) or ABSENT_MARK_TOKEN,
                        "total_marks": str(parsed.get("normalized_total_marks", "")) or self._number_to_str(total_marks_value),
                        "subject_status": subject_status,
                        "subject_percentage": number_to_string(percentage),
                        "subject_category": subject_category,
                        "is_explicit_absent": bool(parsed.get("is_explicit_absent", False)),
                    }
                )

            parsed_df = pd.DataFrame(parsed_rows)
            if parsed_df.empty:
                return _response(False, "No marks data to save.")

            parsed_df = parsed_df.drop_duplicates(subset=["student_id"], keep="last").copy()
            incoming_student_ids = set(parsed_df["student_id"].astype(str).tolist())

            results_df = self._read_results_dataframe(school_sheet_id)
            target_mask = (
                (results_df["exam_session_id"] == normalized_exam_session_id)
                & (results_df["class_id"] == normalized_class_id)
                & (results_df["subject_id"] == normalized_subject_id)
            )
            existing_target = results_df[target_mask].copy()
            existing_keys = set(existing_target["student_id"].astype(str).tolist()) if not existing_target.empty else set()
            existing_audit_by_student: Dict[str, Dict[str, str]] = {}
            if not existing_target.empty:
                for _, existing_row in existing_target.iterrows():
                    sid = str(existing_row.get("student_id", "")).strip()
                    if not sid:
                        continue
                    existing_audit_by_student[sid] = {
                        "entered_by": str(existing_row.get("entered_by", "")).strip(),
                    }

            base_results = results_df[~target_mask].copy()

            rows_to_save = parsed_df.copy()
            rows_to_save["exam_session_id"] = normalized_exam_session_id
            rows_to_save["class_id"] = normalized_class_id
            rows_to_save["subject_id"] = normalized_subject_id
            rows_to_save["pass_ratio"] = number_to_string(pass_ratio * 100)
            rows_to_save["failed_major_subjects"] = ""
            rows_to_save["failed_minor_subjects"] = ""
            rows_to_save["final_result"] = ""

            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows_to_save["entered_by"] = ""
            rows_to_save["modified_by"] = normalized_teacher_id
            rows_to_save["updated_at"] = now_iso

            for row_index in rows_to_save.index:
                sid = str(rows_to_save.at[row_index, "student_id"]).strip()
                existing_entered_by = existing_audit_by_student.get(sid, {}).get("entered_by", "")
                rows_to_save.at[row_index, "entered_by"] = existing_entered_by or normalized_teacher_id

            rows_to_save = rows_to_save[
                [
                    "exam_session_id",
                    "student_id",
                    "class_id",
                    "subject_id",
                    "marks",
                    "total_marks",
                    "subject_status",
                    "subject_percentage",
                    "subject_category",
                    "pass_ratio",
                    "failed_major_subjects",
                    "failed_minor_subjects",
                    "final_result",
                    "entered_by",
                    "modified_by",
                    "updated_at",
                ]
            ]

            merged_results = pd.concat([base_results, rows_to_save], ignore_index=True)
            merged_results = self._apply_student_result_rules(
                merged_results,
                normalized_class_id,
                normalized_exam_session_id,
                class_name,
                subject_name_by_id,
            )

            self._write_results_dataframe(school_sheet_id, merged_results)

            current_target_df = merged_results[
                (merged_results["exam_session_id"] == normalized_exam_session_id)
                & (merged_results["class_id"] == normalized_class_id)
                & (merged_results["subject_id"] == normalized_subject_id)
            ][["student_id", "marks", "total_marks"]].copy()

            status_by_student: Dict[str, str] = {}
            if not current_target_df.empty:
                for _, result_row in current_target_df.iterrows():
                    sid = str(result_row.get("student_id", "")).strip()
                    parsed = parse_marks(result_row.get("marks", ""), result_row.get("total_marks", ""), passing_ratio=pass_ratio)
                    status_by_student[sid] = str(parsed.get("status", "Absent"))

            absent_count = 0
            for sid in valid_student_ids:
                if status_by_student.get(str(sid), "Absent") == "Absent":
                    absent_count += 1

            explicit_absent_count = int((parsed_df["is_explicit_absent"] == True).sum())
            inserted_count = len([sid for sid in incoming_student_ids if sid not in existing_keys])
            updated_count = len([sid for sid in incoming_student_ids if sid in existing_keys])
            deleted_count = len([sid for sid in existing_keys if sid not in incoming_student_ids])

            return _response(
                True,
                "Marks saved successfully.",
                {
                    "teacher_id": normalized_teacher_id,
                    "school_id": school_id,
                    "class_id": normalized_class_id,
                    "subject_id": normalized_subject_id,
                    "exam_session_id": normalized_exam_session_id,
                    "total_marks": self._number_to_str(total_marks_value),
                    "pass_marks_percentage": number_to_string(pass_ratio * 100),
                    "uploaded_count": int(len(incoming_student_ids)),
                    "inserted_count": int(inserted_count),
                    "updated_count": int(updated_count),
                    "deleted_count": int(deleted_count),
                    "explicit_absent_count": explicit_absent_count,
                    "absent_count": int(absent_count),
                    "subject_category": subject_category,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to save marks: {exc}")

    def enter_marks(
        self,
        teacher_id: str,
        exam_session_id: str,
        student_id: str,
        subject_id: str,
        marks: str,
    ) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_exam_session_id = exam_session_id.strip()
            normalized_student_id = student_id.strip()
            normalized_subject_id = subject_id.strip()
            normalized_marks = marks.strip()

            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")
            if not normalized_student_id:
                return _response(False, "student_id is required.")
            if not normalized_subject_id:
                return _response(False, "subject_id is required.")
            sample_parse = parse_marks(normalized_marks, 100)
            if not sample_parse.get("is_valid", False):
                return _response(False, "marks must be numeric or use A/Absent.")

            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")

            has_admin_access = self._is_admin_user(normalized_teacher_id)
            candidate_school_ids: List[str]
            if has_admin_access:
                schools_rows = self.controller.read_tab(TAB_SCHOOLS)
                candidate_school_ids = [
                    self._safe_get(row, SchoolsColumns.SCHOOL_ID)
                    for row in schools_rows[1:]
                    if self._safe_get(row, SchoolsColumns.SCHOOL_ID)
                ]
            else:
                candidate_school_ids = self._get_teacher_school_ids(normalized_teacher_id, active_session_id)

            for school_id in candidate_school_ids:
                school_sheet_id = self._get_school_sheet_id(school_id)
                if not school_sheet_id:
                    continue

                ensure_result = self._ensure_school_tabs(school_sheet_id)
                if not ensure_result.get("success"):
                    return ensure_result

                students_df = self._read_students_dataframe(school_sheet_id)
                student_rows = students_df[students_df["student_id"] == normalized_student_id]
                if student_rows.empty:
                    continue

                class_id = str(student_rows.iloc[0].get("class_id", ""))
                if not class_id:
                    return _response(False, "Student class mapping is missing.")

                if not self._teacher_can_edit_subject(normalized_teacher_id, school_id, class_id, normalized_subject_id):
                    return _response(False, "Access denied")

                return self.save_marks(
                    normalized_teacher_id,
                    normalized_subject_id,
                    class_id,
                    normalized_exam_session_id,
                    "100",
                    [{"student_id": normalized_student_id, "marks": normalized_marks}],
                )

            return _response(False, "Access denied")
        except Exception as exc:
            return _response(False, f"Failed to enter marks: {exc}")


_MANAGER: Optional[TeacherManager] = None


def get_teacher_manager() -> TeacherManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = TeacherManager()
    return _MANAGER


def enroll_student(teacher_id: str, class_id: str, student_name: str, gender: str, parent_name: str) -> Dict[str, Any]:
    return get_teacher_manager().enroll_student(teacher_id, class_id, student_name, gender, parent_name)


def enter_marks(
    teacher_id: str,
    exam_session_id: str,
    student_id: str,
    subject_id: str,
    marks: str,
) -> Dict[str, Any]:
    return get_teacher_manager().enter_marks(teacher_id, exam_session_id, student_id, subject_id, marks)
