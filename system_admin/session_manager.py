"""Academic session management module."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from system_admin.google_sheets_controller import GoogleSheetsController, ValidationError


class SessionManager:
    """Creates and tracks academic sessions and generated worksheets."""

    def __init__(self, controller: GoogleSheetsController) -> None:
        self.controller = controller
        self.controller.create_worksheet(
            "Sessions",
            ["session_year", "is_active", "created_by", "created_at"],
        )

    def list_sessions(self) -> pd.DataFrame:
        return self.controller.read_sheet_or_empty("Sessions")

    def create_session(self, session_year: int, created_by: str = "super_admin") -> Dict[str, str]:
        year = int(session_year)
        self.controller.ensure_unique_value("Sessions", "session_year", year)

        self.controller.append_data(
            "Sessions",
            {
                "session_year": year,
                "is_active": "yes",
                "created_by": created_by,
                "created_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        schools = self.controller.read_sheet_or_empty("Schools")
        generated: List[str] = []
        if not schools.empty:
            for _, school in schools.iterrows():
                pks = str(school.get("pks_code", "")).strip().upper()
                if not pks:
                    continue
                generated.extend(self.controller.create_session_sheets(year, pks))

        return {"session_year": str(year), "generated_sheet_count": str(len(generated))}

    def create_session_for_school(self, session_year: int, pks_code: str) -> List[str]:
        return self.controller.create_session_sheets(int(session_year), pks_code)

    def session_overview(self) -> Dict[str, int]:
        sessions = self.list_sessions()
        if sessions.empty:
            return {"total_sessions": 0, "active_sessions": 0}

        total = int(len(sessions.index))
        active = int((sessions["is_active"].astype(str).str.lower() == "yes").sum())
        return {"total_sessions": total, "active_sessions": active}
