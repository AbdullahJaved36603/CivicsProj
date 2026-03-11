"""School structure management module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from system_admin.google_sheets_controller import GoogleSheetsController, ValidationError


@dataclass
class SchoolRecord:
    school_id: str
    pks_code: str
    school_name: str
    region: str = "Unknown"
    principal_username: str = ""
    status: str = "active"


class SchoolManager:
    """Manages schools, hierarchy sheets, and school lifecycle automation."""

    def __init__(self, controller: GoogleSheetsController) -> None:
        self.controller = controller
        self._bootstrap_core_sheets()

    def _bootstrap_core_sheets(self) -> None:
        self.controller.create_worksheet(
            "Schools",
            ["school_id", "pks_code", "school_name", "region", "principal_username", "status"],
        )
        self.controller.create_worksheet(
            "Users",
            ["user_id", "username", "password_hash", "role", "school_id", "is_active"],
        )

    def list_schools(self) -> pd.DataFrame:
        return self.controller.read_sheet_or_empty("Schools")

    def add_school(self, school: SchoolRecord) -> Dict[str, str]:
        self.controller.ensure_unique_value("Schools", "school_id", school.school_id)
        self.controller.ensure_unique_value("Schools", "pks_code", school.pks_code)
        self.controller.ensure_unique_value("Schools", "school_name", school.school_name)

        self.controller.append_data(
            "Schools",
            {
                "school_id": school.school_id,
                "pks_code": school.pks_code.upper(),
                "school_name": school.school_name,
                "region": school.region,
                "principal_username": school.principal_username,
                "status": school.status,
            },
        )

        created = self.controller.create_school_sheet(school.pks_code)
        return {"school_id": school.school_id, "created_sheets": ", ".join(created)}

    def remove_school(self, school_id: str) -> Dict[str, str]:
        schools = self.list_schools()
        if schools.empty:
            raise ValidationError("No schools available.")

        match = schools.loc[schools["school_id"].astype(str).str.strip() == str(school_id).strip()]
        if match.empty:
            raise ValidationError(f"School '{school_id}' not found.")

        pks_code = str(match.iloc[0]["pks_code"]).strip()
        deleted_rows = self.controller.delete_rows("Schools", "school_id", school_id)
        deleted_sheets = self.controller.delete_school_data(pks_code)
        return {
            "deleted_school_rows": str(deleted_rows),
            "deleted_sheets_count": str(len(deleted_sheets)),
        }

    def assign_principal(self, school_id: str, principal_username: str) -> int:
        return self.controller.update_rows(
            "Schools",
            where_column="school_id",
            where_value=school_id,
            updates={"principal_username": principal_username},
        )

    def school_hierarchy(self, pks_code: str) -> Dict[str, int]:
        pks = pks_code.upper()
        classes = self.controller.read_sheet_or_empty(f"Classes_{pks}")
        students = self.controller.read_sheet_or_empty(f"Students_{pks}")
        teachers = self.controller.read_sheet_or_empty(f"Teachers_{pks}")

        return {
            "classes": int(len(classes.index)),
            "students": int(len(students.index)),
            "teachers": int(len(teachers.index)),
        }

    def system_overview(self) -> Dict[str, int]:
        schools = self.list_schools()
        total_schools = int(len(schools.index))

        total_students = 0
        total_teachers = 0
        total_classes = 0

        for _, row in schools.iterrows():
            pks = str(row.get("pks_code", "")).upper()
            if not pks:
                continue
            total_students += len(self.controller.read_sheet_or_empty(f"Students_{pks}").index)
            total_teachers += len(self.controller.read_sheet_or_empty(f"Teachers_{pks}").index)
            total_classes += len(self.controller.read_sheet_or_empty(f"Classes_{pks}").index)

        return {
            "total_schools": total_schools,
            "total_classes": int(total_classes),
            "total_students": int(total_students),
            "total_teachers": int(total_teachers),
        }

    def seed_demo_school_records(self, pks_code: str, school_id: str) -> None:
        """Populate a school with starter class/student/teacher rows for demos."""
        pks = pks_code.upper()

        classes = pd.DataFrame(
            [
                {"class_id": f"{school_id}-C6", "class_name": "Class 6", "teacher_id": f"{school_id}-T1", "school_id": school_id, "pks_code": pks},
                {"class_id": f"{school_id}-C7", "class_name": "Class 7", "teacher_id": f"{school_id}-T2", "school_id": school_id, "pks_code": pks},
                {"class_id": f"{school_id}-C8", "class_name": "Class 8", "teacher_id": f"{school_id}-T3", "school_id": school_id, "pks_code": pks},
            ]
        )

        teachers = pd.DataFrame(
            [
                {"teacher_id": f"{school_id}-T1", "teacher_name": "Ayesha Khan", "subject": "Math", "class_id": f"{school_id}-C6", "school_id": school_id, "pks_code": pks},
                {"teacher_id": f"{school_id}-T2", "teacher_name": "Usman Ali", "subject": "Science", "class_id": f"{school_id}-C7", "school_id": school_id, "pks_code": pks},
                {"teacher_id": f"{school_id}-T3", "teacher_name": "Sana Tariq", "subject": "English", "class_id": f"{school_id}-C8", "school_id": school_id, "pks_code": pks},
            ]
        )

        students = pd.DataFrame(
            [
                {"student_id": f"{school_id}-S1", "student_name": "Hamza", "gender": "Male", "class_id": f"{school_id}-C6", "school_id": school_id, "pks_code": pks, "monthly_score": 67, "final_score": 74},
                {"student_id": f"{school_id}-S2", "student_name": "Iqra", "gender": "Female", "class_id": f"{school_id}-C6", "school_id": school_id, "pks_code": pks, "monthly_score": 72, "final_score": 79},
                {"student_id": f"{school_id}-S3", "student_name": "Zain", "gender": "Male", "class_id": f"{school_id}-C7", "school_id": school_id, "pks_code": pks, "monthly_score": 64, "final_score": 70},
                {"student_id": f"{school_id}-S4", "student_name": "Hira", "gender": "Female", "class_id": f"{school_id}-C8", "school_id": school_id, "pks_code": pks, "monthly_score": 78, "final_score": 83},
            ]
        )

        self.controller.write_sheet(f"Classes_{pks}", classes)
        self.controller.write_sheet(f"Teachers_{pks}", teachers)
        self.controller.write_sheet(f"Students_{pks}", students)
