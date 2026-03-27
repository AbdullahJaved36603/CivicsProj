from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller


TAB_SESSIONS = "Sessions"
TAB_SCHOOLS = "Schools"
TAB_EXAM_SESSIONS = "exam_sessions"
TAB_TEACHERS = "teachers"
TAB_CLASSES = "classes"
TAB_SUBJECTS = "subjects"


class SessionColumns:
    SESSION_ID = 0
    SESSION_NAME = 1
    IS_ACTIVE = 2
    FOLDER_URL = 3


class SchoolColumns:
    SCHOOL_ID = 0
    SCHOOL_NAME = 1
    SESSION_ID = 2
    SCHOOL_SHEET_URL = 3
    PRINCIPAL_ID = 4


class ExamSessionColumns:
    EXAM_SESSION_ID = 0
    SESSION_ID = 1
    MONTH = 2


class TeachersColumns:
    TEACHER_ID = 0
    TEACHER_NAME = 1
    SCHOOL_ID = 2
    SESSION_ID = 3


class ClassesColumns:
    CLASS_ID = 0
    SCHOOL_ID = 1
    CLASS_NAME = 2
    CLASS_SECTION = 3
    CLASS_INCHARGE_TEACHER_ID = 4
    SESSION_ID = 5


class SubjectsColumns:
    SUBJECT_ID = 0
    CLASS_ID = 1
    SUBJECT_NAME = 2
    SESSION_ID = 3


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class SessionManager:
    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    @staticmethod
    def _is_active(value: str) -> bool:
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "active"}

    @staticmethod
    def _generate_batch_ids(prefix: str, rows: List[List[str]], column_index: int, count: int) -> List[str]:
        if count <= 0:
            return []

        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
        max_number = 0
        max_width = 3

        for row in rows[1:]:
            if column_index >= len(row):
                continue
            value = row[column_index].strip()
            match = pattern.match(value)
            if not match:
                continue
            numeric = match.group(1)
            max_width = max(max_width, len(numeric))
            max_number = max(max_number, int(numeric))

        start = max_number + 1
        return [f"{prefix}{number:0{max_width}d}" for number in range(start, start + count)]

    def _set_all_sessions_inactive(self) -> None:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row_index, row in enumerate(rows[1:], start=2):
            session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
            session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
            folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
            self.controller.update_row(
                row_index=row_index,
                tab_name=TAB_SESSIONS,
                row=[session_id, session_name, "FALSE", folder_url],
            )

    def _get_active_session(self) -> Optional[Dict[str, str]]:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            is_active = row[SessionColumns.IS_ACTIVE] if SessionColumns.IS_ACTIVE < len(row) else ""
            if not self._is_active(is_active):
                continue
            return {
                "session_id": row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else "",
                "session_name": row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else "",
                "folder_url": row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else "",
            }
        return None

    def _session_name_exists(self, session_name: str) -> bool:
        rows = self.controller.read_tab(TAB_SESSIONS)
        target = session_name.lower()
        for row in rows[1:]:
            if SessionColumns.SESSION_NAME < len(row) and row[SessionColumns.SESSION_NAME].lower() == target:
                return True
        return False

    def _session_exists(self, session_id: str) -> bool:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row in rows[1:]:
            current_session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
            if current_session_id == session_id:
                return True
        return False

    def _set_active_session(self, session_id: str) -> None:
        rows = self.controller.read_tab(TAB_SESSIONS)
        for row_index, row in enumerate(rows[1:], start=2):
            current_session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
            session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
            folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
            is_active = "TRUE" if current_session_id == session_id else "FALSE"
            self.controller.update_row(TAB_SESSIONS, row_index, [current_session_id, session_name, is_active, folder_url])

    def _delete_rows_matching(self, tab_name: str, predicate) -> int:
        rows = self.controller.read_tab(tab_name)
        row_indexes_to_delete: List[int] = []
        for row_index, row in enumerate(rows[1:], start=2):
            if predicate(row):
                row_indexes_to_delete.append(row_index)

        deleted = 0
        for row_index in reversed(row_indexes_to_delete):
            self.controller.delete_row(tab_name, row_index)
            deleted += 1
        return deleted

    def _rollback_new_session_data(self, new_session_id: str, folder_id: str, previous_active_session_id: str) -> None:
        try:
            self._delete_rows_matching(
                TAB_SUBJECTS,
                lambda row: (row[SubjectsColumns.SESSION_ID] if SubjectsColumns.SESSION_ID < len(row) else "")
                == new_session_id,
            )
            self._delete_rows_matching(
                TAB_CLASSES,
                lambda row: (row[ClassesColumns.SESSION_ID] if ClassesColumns.SESSION_ID < len(row) else "")
                == new_session_id,
            )
            self._delete_rows_matching(
                TAB_TEACHERS,
                lambda row: (row[TeachersColumns.SESSION_ID] if TeachersColumns.SESSION_ID < len(row) else "") == new_session_id,
            )
            self._delete_rows_matching(
                TAB_SCHOOLS,
                lambda row: (row[SchoolColumns.SESSION_ID] if SchoolColumns.SESSION_ID < len(row) else "") == new_session_id,
            )
            self._delete_rows_matching(
                TAB_SESSIONS,
                lambda row: (row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else "") == new_session_id,
            )

            if folder_id:
                self.controller.delete_folder(folder_id)

            if previous_active_session_id:
                self._set_active_session(previous_active_session_id)
        except Exception:
            return

    def _copy_previous_session_schools(
        self,
        previous_session_id: str,
        new_session_id: str,
        new_session_folder_id: str,
    ) -> Dict[str, Any]:
        schools_rows = self.controller.read_tab(TAB_SCHOOLS)
        source_schools: List[List[str]] = [
            row
            for row in schools_rows[1:]
            if SchoolColumns.SESSION_ID < len(row) and row[SchoolColumns.SESSION_ID] == previous_session_id
        ]

        copied: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        source_to_new_school_map: Dict[str, str] = {}

        for school_row in source_schools:
            school_name = school_row[SchoolColumns.SCHOOL_NAME] if SchoolColumns.SCHOOL_NAME < len(school_row) else ""
            source_school_id = school_row[SchoolColumns.SCHOOL_ID] if SchoolColumns.SCHOOL_ID < len(school_row) else ""
            source_sheet_url = (
                school_row[SchoolColumns.SCHOOL_SHEET_URL] if SchoolColumns.SCHOOL_SHEET_URL < len(school_row) else ""
            )
            source_sheet_id = self.controller.get_school_sheet_id_from_url(source_sheet_url)

            if not school_name:
                failed.append({"school_name": "", "reason": "Missing school_name in source session."})
                continue
            if not source_sheet_id:
                failed.append({"school_name": school_name, "reason": "Missing or invalid source school spreadsheet URL."})
                continue

            create_sheet_result = self.controller.create_sheet(school_name, new_session_folder_id)
            if not create_sheet_result.get("success"):
                failed.append({
                    "school_name": school_name,
                    "reason": create_sheet_result.get("message", "Failed to create school spreadsheet."),
                })
                continue

            sheet_data = create_sheet_result.get("data", {})
            destination_sheet_url = (
                sheet_data.get("school_sheet_url")
                or sheet_data.get("sheet_url")
                or sheet_data.get("spreadsheet_url")
                or sheet_data.get("url")
                or sheet_data.get("result")
            )
            destination_sheet_url = str(destination_sheet_url or "").strip()
            destination_sheet_id = self.controller.get_school_sheet_id_from_url(destination_sheet_url)

            if not destination_sheet_url or not destination_sheet_id:
                failed.append({"school_name": school_name, "reason": "Destination spreadsheet URL is missing or invalid."})
                continue

            clone_result = self.controller.clone_spreadsheet_structure(source_sheet_id, destination_sheet_id)
            if not clone_result.get("success"):
                failed.append({
                    "school_name": school_name,
                    "reason": clone_result.get("message", "Failed to clone spreadsheet structure."),
                })
                continue

            new_school_id = self.controller.generate_next_id("S", TAB_SCHOOLS, SchoolColumns.SCHOOL_ID)
            self.controller.append_row(
                TAB_SCHOOLS,
                [new_school_id, school_name, new_session_id, destination_sheet_url, ""],
            )
            copied.append(
                {
                    "source_school_id": source_school_id,
                    "source_school_name": school_name,
                    "new_school_id": new_school_id,
                    "new_school_sheet_url": destination_sheet_url,
                }
            )
            if source_school_id and new_school_id:
                source_to_new_school_map[source_school_id] = new_school_id

        return {
            "copied": copied,
            "failed": failed,
            "source_school_count": len(source_schools),
            "copied_count": len(copied),
            "source_to_new_school_map": source_to_new_school_map,
        }

    def _copy_previous_session_teacher_mappings(
        self,
        previous_session_id: str,
        new_session_id: str,
        source_to_new_school_map: Dict[str, str],
    ) -> Dict[str, Any]:
        if not source_to_new_school_map:
            return {
                "source_mapping_count": 0,
                "copied_count": 0,
                "copied": [],
            }

        teacher_rows = self.controller.read_tab(TAB_TEACHERS)
        existing_new_keys = {
            (
                row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else "",
                row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else "",
                row[TeachersColumns.SESSION_ID] if TeachersColumns.SESSION_ID < len(row) else "",
            )
            for row in teacher_rows[1:]
        }

        source_rows = [
            row
            for row in teacher_rows[1:]
            if TeachersColumns.SESSION_ID < len(row)
            and row[TeachersColumns.SESSION_ID] == previous_session_id
            and TeachersColumns.SCHOOL_ID < len(row)
            and row[TeachersColumns.SCHOOL_ID] in source_to_new_school_map
        ]

        copied: List[Dict[str, str]] = []
        for row in source_rows:
            teacher_id = row[TeachersColumns.TEACHER_ID] if TeachersColumns.TEACHER_ID < len(row) else ""
            teacher_name = row[TeachersColumns.TEACHER_NAME] if TeachersColumns.TEACHER_NAME < len(row) else ""
            source_school_id = row[TeachersColumns.SCHOOL_ID] if TeachersColumns.SCHOOL_ID < len(row) else ""
            new_school_id = source_to_new_school_map.get(source_school_id, "")
            if not teacher_id or not new_school_id:
                continue

            key = (teacher_id, new_school_id, new_session_id)
            if key in existing_new_keys:
                continue

            self.controller.append_row(TAB_TEACHERS, [teacher_id, teacher_name, new_school_id, new_session_id])
            existing_new_keys.add(key)
            copied.append(
                {
                    "teacher_id": teacher_id,
                    "teacher_name": teacher_name,
                    "source_school_id": source_school_id,
                    "new_school_id": new_school_id,
                    "session_id": new_session_id,
                }
            )

        return {
            "source_mapping_count": len(source_rows),
            "copied_count": len(copied),
            "copied": copied,
        }

    def _copy_previous_session_classes(
        self,
        previous_session_id: str,
        new_session_id: str,
        source_to_new_school_map: Dict[str, str],
    ) -> Dict[str, Any]:
        if not source_to_new_school_map:
            return {
                "source_class_count": 0,
                "copied_count": 0,
                "copied": [],
                "failed": [],
                "source_to_new_class_map": {},
            }

        class_rows = self.controller.read_tab(TAB_CLASSES)
        source_classes = [
            row
            for row in class_rows[1:]
            if ClassesColumns.SCHOOL_ID < len(row)
            and row[ClassesColumns.SCHOOL_ID] in source_to_new_school_map
            and (
                (ClassesColumns.SESSION_ID < len(row) and row[ClassesColumns.SESSION_ID] == previous_session_id)
                or (ClassesColumns.SESSION_ID >= len(row))
            )
        ]

        target_school_ids = set(source_to_new_school_map.values())
        existing_keys = {
            (
                row[ClassesColumns.SCHOOL_ID].strip().lower() if ClassesColumns.SCHOOL_ID < len(row) else "",
                row[ClassesColumns.CLASS_NAME].strip().lower() if ClassesColumns.CLASS_NAME < len(row) else "",
                row[ClassesColumns.CLASS_SECTION].strip().lower() if ClassesColumns.CLASS_SECTION < len(row) else "",
                (
                    row[ClassesColumns.SESSION_ID].strip().lower()
                    if ClassesColumns.SESSION_ID < len(row)
                    else new_session_id.strip().lower()
                ),
            )
            for row in class_rows[1:]
            if ClassesColumns.SCHOOL_ID < len(row) and row[ClassesColumns.SCHOOL_ID] in target_school_ids
        }

        failed: List[Dict[str, str]] = []
        prepared: List[Dict[str, str]] = []

        for row in source_classes:
            source_class_id = row[ClassesColumns.CLASS_ID] if ClassesColumns.CLASS_ID < len(row) else ""
            source_school_id = row[ClassesColumns.SCHOOL_ID] if ClassesColumns.SCHOOL_ID < len(row) else ""
            class_name = row[ClassesColumns.CLASS_NAME] if ClassesColumns.CLASS_NAME < len(row) else ""
            class_section = row[ClassesColumns.CLASS_SECTION] if ClassesColumns.CLASS_SECTION < len(row) else ""
            new_school_id = source_to_new_school_map.get(source_school_id, "")

            if not source_class_id:
                failed.append(
                    {
                        "source_school_id": source_school_id,
                        "class_name": class_name,
                        "class_section": class_section,
                        "reason": "Missing class_id in source class row.",
                    }
                )
                continue
            if not new_school_id:
                failed.append(
                    {
                        "source_school_id": source_school_id,
                        "class_name": class_name,
                        "class_section": class_section,
                        "reason": "No mapped target school_id for source school.",
                    }
                )
                continue
            if not class_name.strip() or not class_section.strip():
                failed.append(
                    {
                        "source_school_id": source_school_id,
                        "class_name": class_name,
                        "class_section": class_section,
                        "reason": "class_name and class_section are required.",
                    }
                )
                continue

            key = (
                new_school_id.strip().lower(),
                class_name.strip().lower(),
                class_section.strip().lower(),
                new_session_id.strip().lower(),
            )
            if key in existing_keys:
                failed.append(
                    {
                        "source_school_id": source_school_id,
                        "class_name": class_name,
                        "class_section": class_section,
                        "reason": "Duplicate class_name + class_section for target school/session.",
                    }
                )
                continue

            existing_keys.add(key)
            prepared.append(
                {
                    "source_class_id": source_class_id,
                    "source_school_id": source_school_id,
                    "new_school_id": new_school_id,
                    "class_name": class_name.strip(),
                    "class_section": class_section.strip(),
                }
            )

        if failed:
            return {
                "source_class_count": len(source_classes),
                "copied_count": 0,
                "copied": [],
                "failed": failed,
                "source_to_new_class_map": {},
            }

        new_class_ids = self._generate_batch_ids("C", class_rows, ClassesColumns.CLASS_ID, len(prepared))
        rows_to_append: List[List[str]] = []
        copied: List[Dict[str, str]] = []
        source_to_new_class_map: Dict[str, str] = {}

        for item, new_class_id in zip(prepared, new_class_ids):
            rows_to_append.append(
                [
                    new_class_id,
                    item["new_school_id"],
                    item["class_name"],
                    item["class_section"],
                    "",
                    new_session_id,
                ]
            )
            source_to_new_class_map[item["source_class_id"]] = new_class_id
            copied.append(
                {
                    "source_class_id": item["source_class_id"],
                    "new_class_id": new_class_id,
                    "source_school_id": item["source_school_id"],
                    "new_school_id": item["new_school_id"],
                    "class_name": item["class_name"],
                    "class_section": item["class_section"],
                    "session_id": new_session_id,
                }
            )

        if rows_to_append:
            self.controller.append_rows(TAB_CLASSES, rows_to_append)

        return {
            "source_class_count": len(source_classes),
            "copied_count": len(copied),
            "copied": copied,
            "failed": [],
            "source_to_new_class_map": source_to_new_class_map,
        }

    def _copy_previous_session_subjects(
        self,
        previous_session_id: str,
        new_session_id: str,
        source_to_new_class_map: Dict[str, str],
    ) -> Dict[str, Any]:
        if not source_to_new_class_map:
            return {
                "source_subject_count": 0,
                "copied_count": 0,
                "copied": [],
                "failed": [],
            }

        subject_rows = self.controller.read_tab(TAB_SUBJECTS)
        source_subjects = [
            row
            for row in subject_rows[1:]
            if SubjectsColumns.CLASS_ID < len(row)
            and row[SubjectsColumns.CLASS_ID] in source_to_new_class_map
            and (
                (SubjectsColumns.SESSION_ID < len(row) and row[SubjectsColumns.SESSION_ID] == previous_session_id)
                or (SubjectsColumns.SESSION_ID >= len(row))
            )
        ]

        target_class_ids = set(source_to_new_class_map.values())
        existing_keys = {
            (
                row[SubjectsColumns.CLASS_ID].strip().lower() if SubjectsColumns.CLASS_ID < len(row) else "",
                row[SubjectsColumns.SUBJECT_NAME].strip().lower() if SubjectsColumns.SUBJECT_NAME < len(row) else "",
            )
            for row in subject_rows[1:]
            if SubjectsColumns.CLASS_ID < len(row) and row[SubjectsColumns.CLASS_ID] in target_class_ids
        }

        failed: List[Dict[str, str]] = []
        prepared: List[Dict[str, str]] = []

        for row in source_subjects:
            source_subject_id = row[SubjectsColumns.SUBJECT_ID] if SubjectsColumns.SUBJECT_ID < len(row) else ""
            source_class_id = row[SubjectsColumns.CLASS_ID] if SubjectsColumns.CLASS_ID < len(row) else ""
            subject_name = row[SubjectsColumns.SUBJECT_NAME] if SubjectsColumns.SUBJECT_NAME < len(row) else ""
            new_class_id = source_to_new_class_map.get(source_class_id, "")

            if not source_subject_id:
                failed.append(
                    {
                        "source_class_id": source_class_id,
                        "subject_name": subject_name,
                        "reason": "Missing subject_id in source subject row.",
                    }
                )
                continue
            if not new_class_id:
                failed.append(
                    {
                        "source_class_id": source_class_id,
                        "subject_name": subject_name,
                        "reason": "No mapped target class_id for source class.",
                    }
                )
                continue
            if not subject_name.strip():
                failed.append(
                    {
                        "source_class_id": source_class_id,
                        "subject_name": subject_name,
                        "reason": "subject_name is required.",
                    }
                )
                continue

            key = (new_class_id.strip().lower(), subject_name.strip().lower())
            if key in existing_keys:
                failed.append(
                    {
                        "source_class_id": source_class_id,
                        "subject_name": subject_name,
                        "reason": "Duplicate subject_name in target class.",
                    }
                )
                continue

            existing_keys.add(key)
            prepared.append(
                {
                    "source_subject_id": source_subject_id,
                    "source_class_id": source_class_id,
                    "new_class_id": new_class_id,
                    "subject_name": subject_name.strip(),
                }
            )

        if failed:
            return {
                "source_subject_count": len(source_subjects),
                "copied_count": 0,
                "copied": [],
                "failed": failed,
            }

        new_subject_ids = self._generate_batch_ids("SUB", subject_rows, SubjectsColumns.SUBJECT_ID, len(prepared))
        rows_to_append: List[List[str]] = []
        copied: List[Dict[str, str]] = []

        for item, new_subject_id in zip(prepared, new_subject_ids):
            rows_to_append.append([new_subject_id, item["new_class_id"], item["subject_name"], new_session_id])
            copied.append(
                {
                    "source_subject_id": item["source_subject_id"],
                    "new_subject_id": new_subject_id,
                    "source_class_id": item["source_class_id"],
                    "new_class_id": item["new_class_id"],
                    "subject_name": item["subject_name"],
                    "session_id": new_session_id,
                }
            )

        if rows_to_append:
            self.controller.append_rows(TAB_SUBJECTS, rows_to_append)

        return {
            "source_subject_count": len(source_subjects),
            "copied_count": len(copied),
            "copied": copied,
            "failed": [],
        }

    def create_session(self, session_name: str, copy_previous: bool = False) -> Dict[str, Any]:
        try:
            normalized_name = session_name.strip()
            if not normalized_name:
                return _response(False, "session_name is required.")
            if self._session_name_exists(normalized_name):
                return _response(False, "Session name already exists.")

            previous_active_session = self._get_active_session()
            previous_active_session_id = previous_active_session.get("session_id", "") if previous_active_session else ""
            session_id = self.controller.generate_next_id("SS", TAB_SESSIONS, SessionColumns.SESSION_ID)
            folder_result = self.controller.create_session_folder(session_id)
            if not folder_result.get("success"):
                return _response(False, folder_result.get("message", "Failed to create session folder."))

            folder_data = folder_result.get("data", {})
            folder_url = str(folder_data.get("folder_url") or "").strip()
            if not folder_url:
                return _response(False, "Session folder URL is missing.")

            folder_id = self.controller.get_folder_id_from_url(folder_url)
            if not folder_id:
                return _response(False, "Session folder ID is missing or invalid.")

            copy_summary: Dict[str, Any] = {
                "copy_previous": copy_previous,
                "source_session_id": previous_active_session.get("session_id", "") if previous_active_session else "",
                "source_session_name": previous_active_session.get("session_name", "") if previous_active_session else "",
                "copied": [],
                "failed": [],
                "source_school_count": 0,
                "copied_count": 0,
            }

            if copy_previous and previous_active_session and previous_active_session.get("session_id"):
                copy_summary = self._copy_previous_session_schools(
                    previous_session_id=str(previous_active_session.get("session_id", "")),
                    new_session_id=session_id,
                    new_session_folder_id=folder_id,
                )

                if copy_summary.get("failed"):
                    self._rollback_new_session_data(session_id, folder_id, previous_active_session_id)
                    return _response(
                        False,
                        "Session creation rolled back because school copy failed.",
                        {
                            "session_id": session_id,
                            "copy_summary": copy_summary,
                        },
                    )

                teacher_copy_summary = self._copy_previous_session_teacher_mappings(
                    previous_session_id=str(previous_active_session.get("session_id", "")),
                    new_session_id=session_id,
                    source_to_new_school_map=copy_summary.get("source_to_new_school_map", {}),
                )
                copy_summary["copy_previous"] = True
                copy_summary["source_session_id"] = previous_active_session.get("session_id", "")
                copy_summary["source_session_name"] = previous_active_session.get("session_name", "")
                copy_summary["teacher_copy_summary"] = teacher_copy_summary

                class_copy_summary = self._copy_previous_session_classes(
                    previous_session_id=str(previous_active_session.get("session_id", "")),
                    new_session_id=session_id,
                    source_to_new_school_map=copy_summary.get("source_to_new_school_map", {}),
                )
                copy_summary["class_copy_summary"] = class_copy_summary

                if class_copy_summary.get("failed"):
                    copy_summary.pop("source_to_new_school_map", None)
                    copy_summary.get("class_copy_summary", {}).pop("source_to_new_class_map", None)
                    self._rollback_new_session_data(session_id, folder_id, previous_active_session_id)
                    return _response(
                        False,
                        "Session creation rolled back because class copy failed.",
                        {
                            "session_id": session_id,
                            "copy_summary": copy_summary,
                        },
                    )

                subject_copy_summary = self._copy_previous_session_subjects(
                    previous_session_id=str(previous_active_session.get("session_id", "")),
                    new_session_id=session_id,
                    source_to_new_class_map=class_copy_summary.get("source_to_new_class_map", {}),
                )
                copy_summary["subject_copy_summary"] = subject_copy_summary

                if subject_copy_summary.get("failed"):
                    copy_summary.pop("source_to_new_school_map", None)
                    copy_summary.get("class_copy_summary", {}).pop("source_to_new_class_map", None)
                    self._rollback_new_session_data(session_id, folder_id, previous_active_session_id)
                    return _response(
                        False,
                        "Session creation rolled back because subject copy failed.",
                        {
                            "session_id": session_id,
                            "copy_summary": copy_summary,
                        },
                    )

                copy_summary.pop("source_to_new_school_map", None)
                copy_summary.get("class_copy_summary", {}).pop("source_to_new_class_map", None)

            self._set_all_sessions_inactive()
            self.controller.append_row(TAB_SESSIONS, [session_id, normalized_name, "TRUE", folder_url])

            return _response(
                True,
                "Session created and activated successfully.",
                {
                    "session_id": session_id,
                    "session_name": normalized_name,
                    "folder_url": folder_url,
                    "copy_summary": copy_summary,
                },
            )
        except Exception as exc:
            try:
                rollback_folder_id = locals().get("folder_id", "")
                rollback_session_id = locals().get("session_id", "")
                rollback_previous = (
                    previous_active_session_id
                    if "previous_active_session_id" in locals()
                    else ""
                )
                if rollback_session_id:
                    self._rollback_new_session_data(rollback_session_id, rollback_folder_id, rollback_previous)
            except Exception:
                pass
            return _response(False, f"Failed to create session: {exc}")

    def activate_session(self, session_id: str) -> Dict[str, Any]:
        try:
            target_session_id = session_id.strip()
            if not target_session_id:
                return _response(False, "session_id is required.")

            rows = self.controller.read_tab(TAB_SESSIONS)
            target_found = False

            for row_index, row in enumerate(rows[1:], start=2):
                current_session_id = row[SessionColumns.SESSION_ID] if SessionColumns.SESSION_ID < len(row) else ""
                session_name = row[SessionColumns.SESSION_NAME] if SessionColumns.SESSION_NAME < len(row) else ""
                folder_url = row[SessionColumns.FOLDER_URL] if SessionColumns.FOLDER_URL < len(row) else ""
                if current_session_id == target_session_id:
                    target_found = True
                    self.controller.update_row(TAB_SESSIONS, row_index, [current_session_id, session_name, "TRUE", folder_url])
                else:
                    self.controller.update_row(TAB_SESSIONS, row_index, [current_session_id, session_name, "FALSE", folder_url])

            if not target_found:
                return _response(False, "session_id does not exist.")

            return _response(True, "Session activated successfully.", {"session_id": target_session_id})
        except Exception as exc:
            return _response(False, f"Failed to activate session: {exc}")

    def create_exam_session(self, session_id: str, month: str) -> Dict[str, Any]:
        try:
            normalized_session_id = session_id.strip()
            normalized_month = month.strip()

            if not normalized_session_id:
                return _response(False, "session_id is required.")
            if not normalized_month:
                return _response(False, "month is required.")
            if not self._session_exists(normalized_session_id):
                return _response(False, "session_id does not exist.")

            exam_session_id = self.controller.generate_next_id(
                "ES",
                TAB_EXAM_SESSIONS,
                ExamSessionColumns.EXAM_SESSION_ID,
            )
            self.controller.append_row(TAB_EXAM_SESSIONS, [exam_session_id, normalized_session_id, normalized_month])
            return _response(
                True,
                "Exam session created successfully.",
                {
                    "exam_session_id": exam_session_id,
                    "session_id": normalized_session_id,
                    "month": normalized_month,
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to create exam session: {exc}")


_MANAGER: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SessionManager()
    return _MANAGER


def create_session(session_name: str, copy_previous: bool = False) -> Dict[str, Any]:
    return get_session_manager().create_session(session_name, copy_previous)


def create_exam_session(session_id: str, month: str) -> Dict[str, Any]:
    return get_session_manager().create_exam_session(session_id, month)
