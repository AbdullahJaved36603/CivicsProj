from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
    from .google_sheets_utils import is_absent_token, parse_marks, to_float
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller
    from google_sheets_utils import is_absent_token, parse_marks, to_float


TAB_SESSIONS = "Sessions"
TAB_SCHOOLS = "Schools"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"
TAB_TEACHERS = "teachers"
TAB_TEACHER_ASSIGNMENTS = "Teacher_Assignments"

SCHOOL_STUDENTS_TAB = "Students"
SCHOOL_RESULTS_TAB = "Results"

PASSING_RATIO = 0.5


class SessionColumns:
    SESSION_ID = 0
    IS_ACTIVE = 2


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
    TEACHER_NAME = 1
    SCHOOL_ID = 2
    SESSION_ID = 3


class TeacherAssignmentsColumns:
    TEACHER_ID = 1
    SCHOOL_ID = 2
    CLASS_ID = 3
    SUBJECT_ID = 4


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _strip_ids_from_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).endswith("_id"):
                continue
            cleaned[key] = _strip_ids_from_payload(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_ids_from_payload(item) for item in value]
    return value


class AnalyticsManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    @staticmethod
    def _safe_get(row: List[str], index: int) -> str:
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
    def _class_label(class_name: str, class_section: str) -> str:
        return f"{str(class_name).strip()}{str(class_section).strip()}"

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        return to_float(value)

    @staticmethod
    def _series_to_number(value: Any) -> Any:
        try:
            float_value = float(value)
            if float_value.is_integer():
                return int(float_value)
            return round(float_value, 2)
        except Exception:
            return value

    def _get_active_session_id(self) -> Optional[str]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            session_id = self._safe_get(row, SessionColumns.SESSION_ID)
            is_active = self._safe_get(row, SessionColumns.IS_ACTIVE)
            if session_id and self._is_active(is_active):
                return session_id
        return None

    def _read_master_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        schools_rows = self.controller.read_tab(TAB_SCHOOLS)
        classes_rows = self.controller.read_tab(TAB_CLASSES)
        subjects_rows = self.controller.read_tab(TAB_SUBJECTS)
        teachers_rows = self.controller.read_tab(TAB_TEACHERS)
        assignments_rows = self.controller.read_tab(TAB_TEACHER_ASSIGNMENTS)

        schools_df = pd.DataFrame(
            [
                {
                    "school_id": self._safe_get(row, SchoolsColumns.SCHOOL_ID),
                    "school_name": self._safe_get(row, SchoolsColumns.SCHOOL_NAME),
                    "session_id": self._safe_get(row, SchoolsColumns.SESSION_ID),
                    "school_sheet_url": self._safe_get(row, SchoolsColumns.SCHOOL_SHEET_URL),
                }
                for row in schools_rows[1:]
            ]
        )

        classes_df = pd.DataFrame(
            [
                {
                    "class_id": self._safe_get(row, ClassesColumns.CLASS_ID),
                    "school_id": self._safe_get(row, ClassesColumns.SCHOOL_ID),
                    "class_name": self._safe_get(row, ClassesColumns.CLASS_NAME),
                    "class_section": self._safe_get(row, ClassesColumns.CLASS_SECTION),
                    "class_incharge_teacher_id": self._safe_get(row, ClassesColumns.CLASS_INCHARGE_TEACHER_ID),
                }
                for row in classes_rows[1:]
            ]
        )
        if not classes_df.empty:
            classes_df["class_label"] = classes_df.apply(
                lambda row: self._class_label(row.get("class_name", ""), row.get("class_section", "")),
                axis=1,
            )

        subjects_df = pd.DataFrame(
            [
                {
                    "subject_id": self._safe_get(row, SubjectsColumns.SUBJECT_ID),
                    "class_id": self._safe_get(row, SubjectsColumns.CLASS_ID),
                    "subject_name": self._safe_get(row, SubjectsColumns.SUBJECT_NAME),
                }
                for row in subjects_rows[1:]
            ]
        )

        teachers_df = pd.DataFrame(
            [
                {
                    "teacher_id": self._safe_get(row, TeachersColumns.TEACHER_ID),
                    "teacher_name": self._safe_get(row, TeachersColumns.TEACHER_NAME),
                    "school_id": self._safe_get(row, TeachersColumns.SCHOOL_ID),
                    "session_id": self._safe_get(row, TeachersColumns.SESSION_ID),
                }
                for row in teachers_rows[1:]
            ]
        )

        assignments_df = pd.DataFrame(
            [
                {
                    "teacher_id": self._safe_get(row, TeacherAssignmentsColumns.TEACHER_ID),
                    "school_id": self._safe_get(row, TeacherAssignmentsColumns.SCHOOL_ID),
                    "class_id": self._safe_get(row, TeacherAssignmentsColumns.CLASS_ID),
                    "subject_id": self._safe_get(row, TeacherAssignmentsColumns.SUBJECT_ID),
                }
                for row in assignments_rows[1:]
            ]
        )

        return schools_df, classes_df, subjects_df, teachers_df, assignments_df

    def _read_school_students(self, school_sheet_id: str) -> pd.DataFrame:
        rows = self.controller.read_tab_from_spreadsheet(school_sheet_id, SCHOOL_STUDENTS_TAB)
        if not rows:
            return pd.DataFrame(columns=["student_id", "student_name", "gender", "parent_name", "class_id", "school_id"])

        headers = rows[0]
        student_id_index = self._header_index(headers, ["student_id"])
        student_name_index = self._header_index(headers, ["student_name"])
        gender_index = self._header_index(headers, ["gender", "sex"])
        parent_name_index = self._header_index(headers, ["parent_name", "guardian_name"])
        class_id_index = self._header_index(headers, ["class_id"])
        school_id_index = self._header_index(headers, ["school_id"])

        items: List[Dict[str, str]] = []
        for row in rows[1:]:
            student_id = self._safe_get(row, student_id_index) if student_id_index is not None else ""
            if not student_id:
                continue
            gender_value = (self._safe_get(row, gender_index) if gender_index is not None else "Unknown").strip()
            items.append(
                {
                    "student_id": student_id,
                    "student_name": self._safe_get(row, student_name_index) if student_name_index is not None else "",
                    "gender": gender_value or "Unknown",
                    "parent_name": self._safe_get(row, parent_name_index) if parent_name_index is not None else "",
                    "class_id": self._safe_get(row, class_id_index) if class_id_index is not None else "",
                    "school_id": self._safe_get(row, school_id_index) if school_id_index is not None else "",
                }
            )

        students_df = pd.DataFrame(items)
        if students_df.empty:
            return pd.DataFrame(columns=["student_id", "student_name", "gender", "parent_name", "class_id", "school_id"])

        students_df["gender"] = (
            students_df["gender"]
            .astype(str)
            .str.strip()
            .str.title()
            .replace({"M": "Male", "F": "Female"})
        )
        return students_df

    def _read_school_results(self, school_sheet_id: str) -> pd.DataFrame:
        rows = self.controller.read_tab_from_spreadsheet(school_sheet_id, SCHOOL_RESULTS_TAB)
        if not rows:
            return pd.DataFrame(
                columns=["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]
            )

        headers = rows[0]
        exam_session_index = self._header_index(headers, ["exam_session_id"])
        student_index = self._header_index(headers, ["student_id"])
        class_index = self._header_index(headers, ["class_id"])
        subject_index = self._header_index(headers, ["subject_id"])
        marks_index = self._header_index(headers, ["marks", "score"])
        total_marks_index = self._header_index(headers, ["total_marks", "max_marks"])

        items: List[Dict[str, Any]] = []
        for row in rows[1:]:
            exam_session_id = self._safe_get(row, exam_session_index) if exam_session_index is not None else ""
            student_id = self._safe_get(row, student_index) if student_index is not None else ""
            class_id = self._safe_get(row, class_index) if class_index is not None else ""
            subject_id = self._safe_get(row, subject_index) if subject_index is not None else ""
            marks = self._safe_get(row, marks_index) if marks_index is not None else ""
            total_marks = self._safe_get(row, total_marks_index) if total_marks_index is not None else ""
            if (total_marks_index is None) and str(marks).strip():
                total_marks = "100"
            if (not str(total_marks).strip()) and str(marks).strip() and (not is_absent_token(marks)):
                total_marks = "100"
            if not exam_session_id or not student_id or not class_id or not subject_id:
                continue
            parsed = parse_marks(marks, total_marks)
            normalized_marks = str(parsed.get("normalized_marks", "A"))
            normalized_total = str(parsed.get("normalized_total_marks", "")).strip() or str(total_marks).strip()
            items.append(
                {
                    "exam_session_id": exam_session_id,
                    "student_id": student_id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "marks": normalized_marks,
                    "total_marks": normalized_total,
                }
            )

        results_df = pd.DataFrame(items)
        if results_df.empty:
            return pd.DataFrame(
                columns=["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]
            )

        for column in ["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]:
            results_df[column] = results_df[column].astype(str).str.strip()

        results_df = results_df.drop_duplicates(
            subset=["exam_session_id", "student_id", "class_id", "subject_id"], keep="last"
        )
        return results_df

    def _student_performance_frame(
        self,
        students_df: pd.DataFrame,
        results_df: pd.DataFrame,
        exam_session_id: str,
        class_id: str = "",
        subject_id: str = "",
    ) -> pd.DataFrame:
        if students_df.empty:
            return pd.DataFrame(
                columns=[
                    "student_id",
                    "student_name",
                    "parent_name",
                    "gender",
                    "class_id",
                    "marks",
                    "total_marks",
                    "status",
                    "percentage",
                ]
            )

        students_scope = students_df.copy()
        if class_id:
            students_scope = students_scope[students_scope["class_id"] == class_id].copy()

        if students_scope.empty:
            return pd.DataFrame(
                columns=[
                    "student_id",
                    "student_name",
                    "parent_name",
                    "gender",
                    "class_id",
                    "marks",
                    "total_marks",
                    "status",
                    "percentage",
                ]
            )

        results_scope = results_df.copy()
        results_scope = results_scope[results_scope["exam_session_id"] == exam_session_id].copy()
        if class_id:
            results_scope = results_scope[results_scope["class_id"] == class_id].copy()
        if subject_id:
            results_scope = results_scope[results_scope["subject_id"] == subject_id].copy()

        parsed_items: List[Dict[str, Any]] = []
        for _, result_row in results_scope.iterrows():
            parsed = parse_marks(result_row.get("marks", ""), result_row.get("total_marks", ""))
            status = str(parsed.get("status", "Absent"))
            is_appeared = 1 if status in {"Pass", "Fail"} else 0
            marks_value = float(parsed.get("marks_value", 0.0) or 0.0) if is_appeared else 0.0
            total_value = float(parsed.get("total_marks_value", 0.0) or 0.0) if is_appeared else 0.0
            parsed_items.append(
                {
                    "student_id": str(result_row.get("student_id", "")),
                    "marks_value": marks_value,
                    "total_marks_value": total_value,
                    "status": status,
                    "is_appeared": is_appeared,
                }
            )

        parsed_results_df = pd.DataFrame(parsed_items)

        if subject_id:
            if parsed_results_df.empty:
                student_result = pd.DataFrame(columns=["student_id", "marks", "total_marks", "status", "percentage"])
            else:
                subject_result = (
                    parsed_results_df.sort_index()
                    .groupby("student_id", as_index=False)
                    .agg(
                        {
                            "marks_value": "last",
                            "total_marks_value": "last",
                            "status": "last",
                            "is_appeared": "last",
                        }
                    )
                )
                subject_result["marks"] = subject_result.apply(
                    lambda row: row.get("marks_value") if int(row.get("is_appeared", 0)) > 0 else None,
                    axis=1,
                )
                subject_result["total_marks"] = subject_result.apply(
                    lambda row: row.get("total_marks_value") if int(row.get("is_appeared", 0)) > 0 else None,
                    axis=1,
                )
                subject_result["percentage"] = subject_result.apply(
                    lambda row: (
                        (float(row.get("marks", 0.0)) / float(row.get("total_marks", 0.0))) * 100
                        if row.get("marks") is not None and row.get("total_marks") not in (None, 0)
                        else None
                    ),
                    axis=1,
                )
                student_result = subject_result[["student_id", "marks", "total_marks", "status", "percentage"]]
        else:
            if parsed_results_df.empty:
                student_result = pd.DataFrame(columns=["student_id", "marks", "total_marks", "status", "percentage"])
            else:
                aggregate_result = (
                    parsed_results_df.groupby("student_id", as_index=False)
                    .agg(
                        {
                            "is_appeared": "sum",
                            "marks_value": "sum",
                            "total_marks_value": "sum",
                        }
                    )
                )

                def _aggregate_status(row: pd.Series) -> str:
                    appeared_count = int(row.get("is_appeared", 0) or 0)
                    total_value = float(row.get("total_marks_value", 0.0) or 0.0)
                    if appeared_count <= 0 or total_value <= 0:
                        return "Absent"
                    marks_value = float(row.get("marks_value", 0.0) or 0.0)
                    return "Pass" if marks_value >= (total_value * PASSING_RATIO) else "Fail"

                aggregate_result["status"] = aggregate_result.apply(_aggregate_status, axis=1)
                aggregate_result["marks"] = aggregate_result.apply(
                    lambda row: row.get("marks_value") if str(row.get("status", "")) in {"Pass", "Fail"} else None,
                    axis=1,
                )
                aggregate_result["total_marks"] = aggregate_result.apply(
                    lambda row: row.get("total_marks_value") if str(row.get("status", "")) in {"Pass", "Fail"} else None,
                    axis=1,
                )
                aggregate_result["percentage"] = aggregate_result.apply(
                    lambda row: (
                        (float(row.get("marks", 0.0)) / float(row.get("total_marks", 0.0))) * 100
                        if row.get("marks") is not None and row.get("total_marks") not in (None, 0)
                        else None
                    ),
                    axis=1,
                )
                student_result = aggregate_result[["student_id", "marks", "total_marks", "status", "percentage"]]

        merged = students_scope.merge(student_result, on="student_id", how="left")
        merged["status"] = merged["status"].fillna("Absent")
        merged["marks"] = pd.to_numeric(merged["marks"], errors="coerce")
        merged["total_marks"] = pd.to_numeric(merged["total_marks"], errors="coerce")
        merged["percentage"] = pd.to_numeric(merged["percentage"], errors="coerce")
        return merged

    def _metrics_from_performance(self, performance_df: pd.DataFrame) -> Dict[str, Any]:
        if performance_df.empty:
            return {
                "total_students": 0,
                "absent_students": 0,
                "appeared_students": 0,
                "passed_students": 0,
                "failed_students": 0,
                "pass_percentage": 0.0,
                "fail_percentage": 0.0,
                "average_marks": 0.0,
                "male_passed": 0,
                "male_failed": 0,
                "female_passed": 0,
                "female_failed": 0,
            }

        total_students = int(len(performance_df))
        absent_students = int((performance_df["status"] == "Absent").sum())
        appeared_students = total_students - absent_students
        passed_students = int((performance_df["status"] == "Pass").sum())
        failed_students = int((performance_df["status"] == "Fail").sum())

        denominator = appeared_students if appeared_students > 0 else 0
        pass_percentage = round((passed_students / denominator) * 100, 2) if denominator else 0.0
        fail_percentage = round((failed_students / denominator) * 100, 2) if denominator else 0.0

        appeared_df = performance_df[performance_df["status"] != "Absent"].copy()
        average_marks = round(float(appeared_df["marks"].mean()), 2) if not appeared_df.empty else 0.0

        normalized_gender = performance_df["gender"].astype(str).str.strip().str.lower()
        male_mask = normalized_gender.str.startswith("m")
        female_mask = normalized_gender.str.startswith("f")

        male_passed = int(((performance_df["status"] == "Pass") & male_mask).sum())
        male_failed = int(((performance_df["status"] == "Fail") & male_mask).sum())
        female_passed = int(((performance_df["status"] == "Pass") & female_mask).sum())
        female_failed = int(((performance_df["status"] == "Fail") & female_mask).sum())

        return {
            "total_students": total_students,
            "absent_students": absent_students,
            "appeared_students": appeared_students,
            "passed_students": passed_students,
            "failed_students": failed_students,
            "pass_percentage": pass_percentage,
            "fail_percentage": fail_percentage,
            "average_marks": average_marks,
            "male_passed": male_passed,
            "male_failed": male_failed,
            "female_passed": female_passed,
            "female_failed": female_failed,
        }

    def _school_context_frames(
        self,
        school_id: str,
        classes_df: pd.DataFrame,
        subjects_df: pd.DataFrame,
        schools_df: pd.DataFrame,
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame], str]:
        school_rows = schools_df[schools_df["school_id"] == school_id]
        if school_rows.empty:
            return None, None, None, None, ""

        school_row = school_rows.iloc[0]
        school_name = str(school_row.get("school_name", ""))
        school_sheet_id = self.controller.get_school_sheet_id_from_url(str(school_row.get("school_sheet_url", "")))
        if not school_sheet_id:
            return None, None, None, None, school_name

        students_df = self._read_school_students(school_sheet_id)
        results_df = self._read_school_results(school_sheet_id)
        school_classes_df = classes_df[classes_df["school_id"] == school_id].copy()
        school_subjects_df = subjects_df.merge(
            school_classes_df[["class_id", "class_label"]], on="class_id", how="inner"
        )
        return students_df, results_df, school_classes_df, school_subjects_df, school_name

    def get_teacher_subject_analytics(self, teacher_id: str, subject_id: str, exam_session_id: str) -> Dict[str, Any]:
        try:
            normalized_teacher_id = teacher_id.strip()
            normalized_subject_id = subject_id.strip()
            normalized_exam_session_id = exam_session_id.strip()

            if not normalized_teacher_id:
                return _response(False, "teacher_id is required.")
            if not normalized_subject_id:
                return _response(False, "subject_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            active_session_id = self._get_active_session_id()
            if not active_session_id:
                return _response(False, "No active session found.")

            schools_df, classes_df, subjects_df, teachers_df, assignments_df = self._read_master_data()
            teacher_schools = set(
                teachers_df[
                    (teachers_df["teacher_id"] == normalized_teacher_id)
                    & (teachers_df["session_id"] == active_session_id)
                ]["school_id"].tolist()
            )
            if not teacher_schools:
                return _response(False, "Access denied")

            assignment_scope = assignments_df[
                (assignments_df["teacher_id"] == normalized_teacher_id)
                & (assignments_df["subject_id"] == normalized_subject_id)
                & (assignments_df["school_id"].isin(teacher_schools))
            ].copy()
            if assignment_scope.empty:
                return _response(False, "Access denied")

            school_session_map = schools_df.set_index("school_id")["session_id"].to_dict() if not schools_df.empty else {}
            assignment_scope = assignment_scope[
                assignment_scope["school_id"].map(lambda sid: school_session_map.get(sid, "")) == active_session_id
            ].copy()
            if assignment_scope.empty:
                return _response(False, "Access denied")

            class_rows: List[Dict[str, Any]] = []
            merged_performance = pd.DataFrame()

            subject_name = ""
            subject_rows = subjects_df[subjects_df["subject_id"] == normalized_subject_id]
            if not subject_rows.empty:
                subject_name = str(subject_rows.iloc[0].get("subject_name", ""))

            for school_id in sorted(set(assignment_scope["school_id"].tolist())):
                students_df, results_df, school_classes_df, _, school_name = self._school_context_frames(
                    school_id,
                    classes_df,
                    subjects_df,
                    schools_df,
                )
                if students_df is None or results_df is None or school_classes_df is None:
                    continue

                class_ids = sorted(
                    set(assignment_scope[assignment_scope["school_id"] == school_id]["class_id"].tolist())
                )
                for class_id in class_ids:
                    class_info_rows = school_classes_df[school_classes_df["class_id"] == class_id]
                    if class_info_rows.empty:
                        continue
                    class_info = class_info_rows.iloc[0]
                    perf_df = self._student_performance_frame(
                        students_df,
                        results_df,
                        normalized_exam_session_id,
                        class_id=class_id,
                        subject_id=normalized_subject_id,
                    )
                    metrics = self._metrics_from_performance(perf_df)
                    class_rows.append(
                        {
                            "school_id": school_id,
                            "school_name": school_name,
                            "class_id": class_id,
                            "class_name": str(class_info.get("class_name", "")),
                            "class_section": str(class_info.get("class_section", "")),
                            "class_label": str(class_info.get("class_label", "")),
                            **metrics,
                        }
                    )
                    merged_performance = pd.concat([merged_performance, perf_df], ignore_index=True)

            overall_metrics = self._metrics_from_performance(merged_performance)

            return _response(
                True,
                "Teacher subject analytics fetched successfully.",
                _strip_ids_from_payload({
                    "teacher_id": normalized_teacher_id,
                    "subject_id": normalized_subject_id,
                    "subject_name": subject_name,
                    "exam_session_id": normalized_exam_session_id,
                    "overall": overall_metrics,
                    "by_class": class_rows,
                }),
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch teacher subject analytics: {exc}")

    def get_class_analytics(self, class_id: str, exam_session_id: str) -> Dict[str, Any]:
        try:
            normalized_class_id = class_id.strip()
            normalized_exam_session_id = exam_session_id.strip()

            if not normalized_class_id:
                return _response(False, "class_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            schools_df, classes_df, subjects_df, _, _ = self._read_master_data()
            class_rows = classes_df[classes_df["class_id"] == normalized_class_id]
            if class_rows.empty:
                return _response(False, "class_id does not exist.")

            class_row = class_rows.iloc[0]
            school_id = str(class_row.get("school_id", ""))
            students_df, results_df, school_classes_df, school_subjects_df, school_name = self._school_context_frames(
                school_id,
                classes_df,
                subjects_df,
                schools_df,
            )
            if students_df is None or results_df is None:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            overall_perf = self._student_performance_frame(
                students_df,
                results_df,
                normalized_exam_session_id,
                class_id=normalized_class_id,
                subject_id="",
            )
            overall_metrics = self._metrics_from_performance(overall_perf)

            subject_rows: List[Dict[str, Any]] = []
            class_subjects = school_subjects_df[school_subjects_df["class_id"] == normalized_class_id]
            for _, subject_row in class_subjects.iterrows():
                subject_id = str(subject_row.get("subject_id", ""))
                perf_df = self._student_performance_frame(
                    students_df,
                    results_df,
                    normalized_exam_session_id,
                    class_id=normalized_class_id,
                    subject_id=subject_id,
                )
                metrics = self._metrics_from_performance(perf_df)
                subject_rows.append(
                    {
                        "subject_id": subject_id,
                        "subject_name": str(subject_row.get("subject_name", "")),
                        **metrics,
                    }
                )

            return _response(
                True,
                "Class analytics fetched successfully.",
                _strip_ids_from_payload({
                    "school_id": school_id,
                    "school_name": school_name,
                    "class_id": normalized_class_id,
                    "class_name": str(class_row.get("class_name", "")),
                    "class_section": str(class_row.get("class_section", "")),
                    "class_label": str(class_row.get("class_label", "")),
                    "exam_session_id": normalized_exam_session_id,
                    "overall": overall_metrics,
                    "subject_wise": subject_rows,
                }),
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch class analytics: {exc}")

    def get_school_analytics(
        self,
        school_id: str,
        exam_session_id: str,
        class_id: str = "",
        subject_id: str = "",
    ) -> Dict[str, Any]:
        try:
            normalized_school_id = school_id.strip()
            normalized_exam_session_id = exam_session_id.strip()
            normalized_class_id = class_id.strip()
            normalized_subject_id = subject_id.strip()

            if not normalized_school_id:
                return _response(False, "school_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            schools_df, classes_df, subjects_df, _, _ = self._read_master_data()
            students_df, results_df, school_classes_df, school_subjects_df, school_name = self._school_context_frames(
                normalized_school_id,
                classes_df,
                subjects_df,
                schools_df,
            )
            if students_df is None or results_df is None or school_classes_df is None or school_subjects_df is None:
                return _response(False, "School spreadsheet URL is missing or invalid.")

            overall_perf = self._student_performance_frame(
                students_df,
                results_df,
                normalized_exam_session_id,
                class_id=normalized_class_id,
                subject_id=normalized_subject_id,
            )
            overall_metrics = self._metrics_from_performance(overall_perf)

            class_scope_df = school_classes_df.copy()
            if normalized_class_id:
                class_scope_df = class_scope_df[class_scope_df["class_id"] == normalized_class_id].copy()

            class_rows: List[Dict[str, Any]] = []
            for _, class_row in class_scope_df.iterrows():
                class_value = str(class_row.get("class_id", ""))
                perf_df = self._student_performance_frame(
                    students_df,
                    results_df,
                    normalized_exam_session_id,
                    class_id=class_value,
                    subject_id=normalized_subject_id,
                )
                metrics = self._metrics_from_performance(perf_df)
                class_rows.append(
                    {
                        "class_id": class_value,
                        "class_name": str(class_row.get("class_name", "")),
                        "class_section": str(class_row.get("class_section", "")),
                        "class_label": str(class_row.get("class_label", "")),
                        **metrics,
                    }
                )

            subject_scope_df = school_subjects_df.copy()
            if normalized_class_id:
                subject_scope_df = subject_scope_df[subject_scope_df["class_id"] == normalized_class_id].copy()
            if normalized_subject_id:
                subject_scope_df = subject_scope_df[subject_scope_df["subject_id"] == normalized_subject_id].copy()

            subject_rows: List[Dict[str, Any]] = []
            for _, subject_row in subject_scope_df.iterrows():
                class_value = str(subject_row.get("class_id", ""))
                subject_value = str(subject_row.get("subject_id", ""))
                perf_df = self._student_performance_frame(
                    students_df,
                    results_df,
                    normalized_exam_session_id,
                    class_id=class_value,
                    subject_id=subject_value,
                )
                metrics = self._metrics_from_performance(perf_df)
                subject_rows.append(
                    {
                        "class_id": class_value,
                        "class_label": str(subject_row.get("class_label", "")),
                        "subject_id": subject_value,
                        "subject_name": str(subject_row.get("subject_name", "")),
                        **metrics,
                    }
                )

            class_detail: Dict[str, Any] = {}
            if normalized_class_id:
                class_detail_response = self.get_class_analytics(normalized_class_id, normalized_exam_session_id)
                if class_detail_response.get("success"):
                    class_detail = class_detail_response.get("data", {})

            return _response(
                True,
                "School analytics fetched successfully.",
                _strip_ids_from_payload({
                    "school_id": normalized_school_id,
                    "school_name": school_name,
                    "exam_session_id": normalized_exam_session_id,
                    "class_id": normalized_class_id,
                    "subject_id": normalized_subject_id,
                    "overall": overall_metrics,
                    "class_wise": class_rows,
                    "subject_wise": subject_rows,
                    "class_detail": class_detail,
                }),
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch school analytics: {exc}")

    def get_admin_hierarchical_class_analytics(
        self,
        session_id: str,
        exam_session_id: str,
        class_name: str = "",
    ) -> Dict[str, Any]:
        try:
            normalized_session_id = session_id.strip()
            normalized_exam_session_id = exam_session_id.strip()
            normalized_class_name = class_name.strip()

            if not normalized_session_id:
                return _response(False, "session_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            schools_df, classes_df, subjects_df, teachers_df, assignments_df = self._read_master_data()
            session_schools_df = schools_df[schools_df["session_id"] == normalized_session_id].copy()

            if session_schools_df.empty:
                return _response(
                    True,
                    "No schools found for selected session.",
                    {
                        "class_names": [],
                        "summary": {
                            "total_students": 0,
                            "appeared_students": 0,
                            "absent_students": 0,
                            "passed_students": 0,
                            "failed_students": 0,
                            "pass_percentage": 0.0,
                            "fail_percentage": 0.0,
                        },
                        "grouped_rows": [],
                        "sections": [],
                        "export_sheets": {},
                    },
                )

            school_ids = set(session_schools_df["school_id"].astype(str).tolist())
            session_classes_df = classes_df[classes_df["school_id"].isin(school_ids)].copy()
            session_classes_df["class_name"] = session_classes_df["class_name"].astype(str).str.strip()
            session_classes_df["class_section"] = session_classes_df["class_section"].astype(str).str.strip()
            session_classes_df["class_label"] = session_classes_df.apply(
                lambda row: self._class_label(row.get("class_name", ""), row.get("class_section", "")),
                axis=1,
            )

            class_names = sorted(
                {
                    str(item).strip()
                    for item in session_classes_df["class_name"].tolist()
                    if str(item).strip()
                }
            )

            if not normalized_class_name:
                return _response(
                    True,
                    "Class names fetched successfully.",
                    {
                        "class_names": class_names,
                        "summary": {
                            "total_students": 0,
                            "appeared_students": 0,
                            "absent_students": 0,
                            "passed_students": 0,
                            "failed_students": 0,
                            "pass_percentage": 0.0,
                            "fail_percentage": 0.0,
                        },
                        "grouped_rows": [],
                        "sections": [],
                        "export_sheets": {},
                    },
                )

            filtered_classes_df = session_classes_df[
                session_classes_df["class_name"].astype(str).str.casefold() == normalized_class_name.casefold()
            ].copy()

            if filtered_classes_df.empty:
                return _response(
                    True,
                    "No class sections found for selected class name.",
                    {
                        "class_names": class_names,
                        "summary": {
                            "total_students": 0,
                            "appeared_students": 0,
                            "absent_students": 0,
                            "passed_students": 0,
                            "failed_students": 0,
                            "pass_percentage": 0.0,
                            "fail_percentage": 0.0,
                        },
                        "grouped_rows": [],
                        "sections": [],
                        "export_sheets": {},
                    },
                )

            filtered_class_ids = set(filtered_classes_df["class_id"].astype(str).tolist())
            filtered_school_ids = set(filtered_classes_df["school_id"].astype(str).tolist())

            subjects_scope_df = subjects_df[subjects_df["class_id"].isin(filtered_class_ids)].copy()
            assignments_scope_df = assignments_df[
                assignments_df["class_id"].isin(filtered_class_ids)
                & assignments_df["school_id"].isin(filtered_school_ids)
            ].copy()

            teachers_scope_df = teachers_df[
                (teachers_df["session_id"] == normalized_session_id)
                & (teachers_df["school_id"].isin(filtered_school_ids))
            ].copy()
            teacher_name_by_id = {
                str(row.get("teacher_id", "")): (
                    str(row.get("teacher_name", "")).strip() or str(row.get("teacher_id", ""))
                )
                for _, row in teachers_scope_df.iterrows()
            }

            school_name_by_id = {
                str(row.get("school_id", "")): str(row.get("school_name", ""))
                for _, row in session_schools_df.iterrows()
            }

            school_cache: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]] = {}
            for school_id in sorted(filtered_school_ids):
                school_rows = session_schools_df[session_schools_df["school_id"] == school_id]
                if school_rows.empty:
                    school_cache[school_id] = (
                        pd.DataFrame(columns=["student_id", "class_id"]),
                        pd.DataFrame(columns=["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]),
                    )
                    continue
                school_row = school_rows.iloc[0]
                school_sheet_id = self.controller.get_school_sheet_id_from_url(str(school_row.get("school_sheet_url", "")))
                if not school_sheet_id:
                    school_cache[school_id] = (
                        pd.DataFrame(columns=["student_id", "class_id"]),
                        pd.DataFrame(columns=["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]),
                    )
                    continue

                students_df = self._read_school_students(school_sheet_id)
                results_df = self._read_school_results(school_sheet_id)
                school_cache[school_id] = (students_df, results_df)

            grouped_rows: List[Dict[str, Any]] = []
            export_sheets: Dict[str, List[Dict[str, Any]]] = {}

            summary_total_students = 0
            summary_appeared_students = 0
            summary_absent_students = 0
            summary_passed_students = 0
            summary_failed_students = 0

            sorted_classes_df = filtered_classes_df.sort_values(
                by=["class_name", "class_section", "school_id"],
                ignore_index=True,
            )

            for _, class_row in sorted_classes_df.iterrows():
                school_id = str(class_row.get("school_id", ""))
                class_id = str(class_row.get("class_id", ""))
                class_name_value = str(class_row.get("class_name", "")).strip()
                class_section_value = str(class_row.get("class_section", "")).strip()
                class_label_value = str(class_row.get("class_label", "")).strip() or self._class_label(
                    class_name_value,
                    class_section_value,
                )
                school_name = school_name_by_id.get(school_id, "")

                students_df, results_df = school_cache.get(
                    school_id,
                    (
                        pd.DataFrame(columns=["student_id", "class_id"]),
                        pd.DataFrame(columns=["exam_session_id", "student_id", "class_id", "subject_id", "marks", "total_marks"]),
                    ),
                )
                class_students_df = students_df[students_df["class_id"] == class_id].copy()

                class_performance_df = self._student_performance_frame(
                    students_df,
                    results_df,
                    normalized_exam_session_id,
                    class_id=class_id,
                    subject_id="",
                )
                class_metrics = self._metrics_from_performance(class_performance_df)

                summary_total_students += int(class_metrics.get("total_students", 0))
                summary_appeared_students += int(class_metrics.get("appeared_students", 0))
                summary_absent_students += int(class_metrics.get("absent_students", 0))
                summary_passed_students += int(class_metrics.get("passed_students", 0))
                summary_failed_students += int(class_metrics.get("failed_students", 0))

                if class_label_value not in export_sheets:
                    export_sheets[class_label_value] = []

                class_results_scope = results_df[
                    (results_df["exam_session_id"] == normalized_exam_session_id)
                    & (results_df["class_id"] == class_id)
                ].copy()

                if class_results_scope.empty:
                    no_data_row = {
                        "School": school_name,
                        "Subject": "No data available",
                        "Teacher": "-",
                        "Total": int(class_metrics.get("total_students", 0)),
                        "Appeared": 0,
                        "Absent": int(class_metrics.get("total_students", 0)),
                        "Passed": 0,
                        "Failed": 0,
                        "Pass %": 0.0,
                        "Fail %": 0.0,
                    }
                    export_sheets[class_label_value].append(no_data_row)
                    grouped_rows.append(
                        {
                            "School": school_name,
                            "Class": class_name_value,
                            "Section": class_section_value,
                            "Subject": "No data available",
                            "Teacher": "-",
                            "Total Students": int(class_metrics.get("total_students", 0)),
                            "Appeared": 0,
                            "Absent": int(class_metrics.get("total_students", 0)),
                            "Passed": 0,
                            "Failed": 0,
                            "Pass %": 0.0,
                            "Fail %": 0.0,
                        }
                    )
                    continue

                class_subjects_df = subjects_scope_df[subjects_scope_df["class_id"] == class_id].copy()
                if class_subjects_df.empty:
                    class_subjects_df = pd.DataFrame([{"subject_id": "", "subject_name": "Unassigned"}])

                for _, subject_row in class_subjects_df.iterrows():
                    subject_id = str(subject_row.get("subject_id", "")).strip()
                    subject_name = str(subject_row.get("subject_name", "")).strip() or "Unassigned"

                    subject_performance_df = self._student_performance_frame(
                        students_df,
                        results_df,
                        normalized_exam_session_id,
                        class_id=class_id,
                        subject_id=subject_id,
                    )
                    subject_metrics = self._metrics_from_performance(subject_performance_df)

                    subject_assignments_df = assignments_scope_df[
                        (assignments_scope_df["school_id"] == school_id)
                        & (assignments_scope_df["class_id"] == class_id)
                        & (assignments_scope_df["subject_id"] == subject_id)
                    ].copy()

                    teacher_names: List[str] = []
                    if subject_assignments_df.empty:
                        teacher_names = ["Unassigned"]
                    else:
                        for teacher_id_value in subject_assignments_df["teacher_id"].astype(str).tolist():
                            teacher_names.append(teacher_name_by_id.get(teacher_id_value, teacher_id_value))
                        if not teacher_names:
                            teacher_names = ["Unassigned"]

                    for teacher_name in teacher_names:
                        total_students = int(subject_metrics.get("total_students", len(class_students_df)))
                        appeared_students = int(subject_metrics.get("appeared_students", 0))
                        absent_students = int(subject_metrics.get("absent_students", max(total_students - appeared_students, 0)))
                        passed_students = int(subject_metrics.get("passed_students", 0))
                        failed_students = int(subject_metrics.get("failed_students", 0))
                        pass_percentage = float(subject_metrics.get("pass_percentage", 0.0))
                        fail_percentage = float(subject_metrics.get("fail_percentage", 0.0))

                        grouped_rows.append(
                            {
                                "School": school_name,
                                "Class": class_name_value,
                                "Section": class_section_value,
                                "Subject": subject_name,
                                "Teacher": teacher_name,
                                "Total Students": total_students,
                                "Appeared": appeared_students,
                                "Absent": absent_students,
                                "Passed": passed_students,
                                "Failed": failed_students,
                                "Pass %": round(pass_percentage, 2),
                                "Fail %": round(fail_percentage, 2),
                            }
                        )
                        export_sheets[class_label_value].append(
                            {
                                "School": school_name,
                                "Subject": subject_name,
                                "Teacher": teacher_name,
                                "Total": total_students,
                                "Appeared": appeared_students,
                                "Absent": absent_students,
                                "Passed": passed_students,
                                "Failed": failed_students,
                                "Pass %": round(pass_percentage, 2),
                                "Fail %": round(fail_percentage, 2),
                            }
                        )

            summary_denominator = summary_appeared_students if summary_appeared_students > 0 else 0
            summary_pass_percentage = (
                round((summary_passed_students / summary_denominator) * 100, 2)
                if summary_denominator
                else 0.0
            )
            summary_fail_percentage = (
                round((summary_failed_students / summary_denominator) * 100, 2)
                if summary_denominator
                else 0.0
            )

            grouped_df = pd.DataFrame(grouped_rows)
            if not grouped_df.empty:
                grouped_df = grouped_df.sort_values(
                    by=["School", "Class", "Section", "Subject", "Teacher"],
                    ignore_index=True,
                )
                grouped_rows = grouped_df.to_dict("records")

            sections = sorted(export_sheets.keys())

            return _response(
                True,
                "Admin hierarchical analytics fetched successfully.",
                {
                    "class_names": class_names,
                    "selected_class": normalized_class_name,
                    "summary": {
                        "total_students": summary_total_students,
                        "appeared_students": summary_appeared_students,
                        "absent_students": summary_absent_students,
                        "passed_students": summary_passed_students,
                        "failed_students": summary_failed_students,
                        "pass_percentage": summary_pass_percentage,
                        "fail_percentage": summary_fail_percentage,
                    },
                    "grouped_rows": grouped_rows,
                    "sections": sections,
                    "export_sheets": export_sheets,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch admin hierarchical analytics: {exc}")

    def get_session_analytics(
        self,
        session_id: str,
        exam_session_id: str,
        school_id: str = "",
        class_id: str = "",
        subject_id: str = "",
    ) -> Dict[str, Any]:
        try:
            normalized_session_id = session_id.strip()
            normalized_exam_session_id = exam_session_id.strip()
            normalized_school_id = school_id.strip()
            normalized_class_id = class_id.strip()
            normalized_subject_id = subject_id.strip()

            if not normalized_session_id:
                return _response(False, "session_id is required.")
            if not normalized_exam_session_id:
                return _response(False, "exam_session_id is required.")

            schools_df, classes_df, subjects_df, _, _ = self._read_master_data()
            session_schools = schools_df[schools_df["session_id"] == normalized_session_id].copy()
            if normalized_school_id:
                session_schools = session_schools[session_schools["school_id"] == normalized_school_id].copy()

            school_rows: List[Dict[str, Any]] = []
            class_section_rows: List[Dict[str, Any]] = []

            for _, school_row in session_schools.iterrows():
                current_school_id = str(school_row.get("school_id", ""))
                if not current_school_id:
                    continue

                scoped_class_id = normalized_class_id
                if scoped_class_id:
                    class_match = classes_df[
                        (classes_df["class_id"] == scoped_class_id)
                        & (classes_df["school_id"] == current_school_id)
                    ]
                    if class_match.empty:
                        scoped_class_id = ""

                school_response = self.get_school_analytics(
                    current_school_id,
                    normalized_exam_session_id,
                    class_id=scoped_class_id,
                    subject_id=normalized_subject_id,
                )
                if not school_response.get("success"):
                    continue

                school_payload = school_response.get("data", {})
                overall = school_payload.get("overall", {})
                school_rows.append(
                    {
                        "school_id": school_payload.get("school_id", ""),
                        "school_name": school_payload.get("school_name", ""),
                        "total_students": overall.get("total_students", 0),
                        "appeared_students": overall.get("appeared_students", 0),
                        "passed_students": overall.get("passed_students", 0),
                        "failed_students": overall.get("failed_students", 0),
                        "pass_percentage": overall.get("pass_percentage", 0.0),
                        "fail_percentage": overall.get("fail_percentage", 0.0),
                        "average_marks": overall.get("average_marks", 0.0),
                    }
                )

                for class_item in school_payload.get("class_wise", []):
                    class_section_rows.append(
                        {
                            "school_id": school_payload.get("school_id", ""),
                            "school_name": school_payload.get("school_name", ""),
                            **class_item,
                        }
                    )

            school_comparison = sorted(
                school_rows,
                key=lambda item: float(item.get("pass_percentage", 0.0)),
                reverse=True,
            )

            return _response(
                True,
                "Session analytics fetched successfully.",
                _strip_ids_from_payload({
                    "session_id": normalized_session_id,
                    "exam_session_id": normalized_exam_session_id,
                    "school_id": normalized_school_id,
                    "class_id": normalized_class_id,
                    "subject_id": normalized_subject_id,
                    "schools": school_rows,
                    "school_comparison": school_comparison,
                    "class_section_analytics": class_section_rows,
                }),
            )
        except Exception as exc:
            return _response(False, f"Failed to fetch session analytics: {exc}")


_MANAGER: Optional[AnalyticsManager] = None


def get_analytics_manager() -> AnalyticsManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = AnalyticsManager()
    return _MANAGER
