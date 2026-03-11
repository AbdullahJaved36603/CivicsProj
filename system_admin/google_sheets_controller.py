"""Data controller for Google Sheets with Excel fallback backend.

This controller provides one API for two storage modes:
- google_sheets: uses gspread + Google Sheets API
- excel: uses a local Excel workbook as temporary offline database
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

try:
    import gspread
    from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
except Exception:  # pragma: no cover
    gspread = None
    SpreadsheetNotFound = Exception
    WorksheetNotFound = Exception


class GoogleSheetsControllerError(Exception):
    """Base exception for data-controller errors."""


class AuthenticationError(GoogleSheetsControllerError):
    """Raised when authentication fails."""


class ValidationError(GoogleSheetsControllerError):
    """Raised when data validation fails."""


class AccessVerificationError(GoogleSheetsControllerError):
    """Raised when read/write verification fails."""


@dataclass(frozen=True)
class AccessVerificationResult:
    """Read/write verification result."""

    read_access: bool
    write_access: bool
    target: str


class GoogleSheetsController:
    """Controller used by all Group A modules."""

    PKS_PATTERN = re.compile(r"^PKS\d{2}$")

    def __init__(
        self,
        *,
        backend: str = "excel",
        excel_path: str = "local_system_db.xlsx",
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        spreadsheet_name: Optional[str] = None,
        cache_enabled: bool = True,
    ) -> None:
        self.backend = backend.strip().lower()
        self.excel_path = excel_path
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.spreadsheet_id = spreadsheet_id
        self.spreadsheet_name = spreadsheet_name
        self.cache_enabled = cache_enabled

        self._client = None
        self._spreadsheet = None
        self._cache: Dict[str, pd.DataFrame] = {}

        if self.backend not in {"excel", "google_sheets"}:
            raise ValidationError("backend must be 'excel' or 'google_sheets'.")

        if self.backend == "excel":
            self._ensure_excel_db()

    # ----------------------------
    # Core setup / connection
    # ----------------------------
    def _ensure_excel_db(self) -> None:
        if os.path.exists(self.excel_path):
            return

        with pd.ExcelWriter(self.excel_path, engine="openpyxl") as writer:
            pd.DataFrame(columns=["created_at", "backend"]).to_excel(
                writer, sheet_name="Meta", index=False
            )

    def authenticate(self):
        if self.backend == "excel":
            return None

        if gspread is None:
            raise AuthenticationError("gspread is not installed in this environment.")

        if self._client is not None:
            return self._client

        if not self.credentials_path:
            raise AuthenticationError(
                "Missing credentials. Set credentials_path or GOOGLE_APPLICATION_CREDENTIALS."
            )

        if not os.path.exists(self.credentials_path):
            raise AuthenticationError(f"Credentials file not found: {self.credentials_path}")

        try:
            self._client = gspread.service_account(filename=self.credentials_path)
            return self._client
        except Exception as exc:
            raise AuthenticationError(f"Google authentication failed: {exc}") from exc

    def connect(self):
        if self.backend == "excel":
            self._ensure_excel_db()
            return self.excel_path

        if self._spreadsheet is not None:
            return self._spreadsheet

        client = self.authenticate()
        try:
            if self.spreadsheet_id:
                self._spreadsheet = client.open_by_key(self.spreadsheet_id)
            elif self.spreadsheet_name:
                self._spreadsheet = client.open(self.spreadsheet_name)
            else:
                raise ValidationError("Provide spreadsheet_id or spreadsheet_name for Google mode.")
            return self._spreadsheet
        except SpreadsheetNotFound as exc:
            raise AuthenticationError("Spreadsheet not found or access denied.") from exc

    # ----------------------------
    # Introspection
    # ----------------------------
    def list_worksheets(self) -> List[str]:
        if self.backend == "excel":
            with pd.ExcelFile(self.connect()) as book:
                return list(book.sheet_names)

        return [ws.title for ws in self.connect().worksheets()]

    def verify_read_write_access(self, worksheet_name: Optional[str] = None) -> AccessVerificationResult:
        try:
            sheets = self.list_worksheets()
            target = worksheet_name or (sheets[0] if sheets else "Meta")
            _ = self.read_sheet(target)
            self.write_sheet(target, self.read_sheet(target))
            return AccessVerificationResult(True, True, target)
        except Exception as exc:
            raise AccessVerificationError(str(exc)) from exc

    # ----------------------------
    # Basic CRUD
    # ----------------------------
    def read_sheet(self, worksheet_name: str) -> pd.DataFrame:
        if self.cache_enabled and worksheet_name in self._cache:
            return self._cache[worksheet_name].copy()

        if self.backend == "excel":
            with pd.ExcelFile(self.connect()) as book:
                if worksheet_name not in book.sheet_names:
                    raise ValidationError(f"Sheet '{worksheet_name}' does not exist.")
                frame = pd.read_excel(self.connect(), sheet_name=worksheet_name)
        else:
            ws = self._get_google_worksheet(worksheet_name)
            frame = pd.DataFrame(ws.get_all_records())

        if self.cache_enabled:
            self._cache[worksheet_name] = frame.copy()
        return frame

    def write_sheet(self, worksheet_name: str, frame: pd.DataFrame) -> None:
        frame = frame.copy()

        if self.backend == "excel":
            self._write_excel_sheet(worksheet_name, frame)
            self._invalidate_cache(worksheet_name)
            return

        ws = self._get_or_create_google_sheet(worksheet_name)
        ws.clear()
        if frame.empty:
            ws.update([[]])
        else:
            payload = [list(frame.columns)] + frame.fillna("").astype(str).values.tolist()
            ws.update(payload)
        self._invalidate_cache(worksheet_name)

    def append_data(self, worksheet_name: str, row_data: Dict[str, Any]) -> int:
        frame = self.read_sheet_or_empty(worksheet_name)
        if frame.empty:
            frame = pd.DataFrame(columns=list(row_data.keys()))

        for key in row_data:
            if key not in frame.columns:
                frame[key] = ""

        ordered = {column: row_data.get(column, "") for column in frame.columns}
        frame = pd.concat([frame, pd.DataFrame([ordered])], ignore_index=True)
        self.write_sheet(worksheet_name, frame)
        return len(frame)

    def update_rows(
        self,
        worksheet_name: str,
        where_column: str,
        where_value: Any,
        updates: Dict[str, Any],
    ) -> int:
        frame = self.read_sheet(worksheet_name)
        if where_column not in frame.columns:
            raise ValidationError(f"Column '{where_column}' not found.")

        mask = frame[where_column].astype(str).str.strip() == str(where_value).strip()
        changed = int(mask.sum())
        if changed == 0:
            return 0

        for column, value in updates.items():
            if column not in frame.columns:
                frame[column] = ""
            frame.loc[mask, column] = value

        self.write_sheet(worksheet_name, frame)
        return changed

    def delete_rows(self, worksheet_name: str, where_column: str, where_value: Any) -> int:
        frame = self.read_sheet(worksheet_name)
        if where_column not in frame.columns:
            raise ValidationError(f"Column '{where_column}' not found.")

        mask = frame[where_column].astype(str).str.strip() == str(where_value).strip()
        deleted = int(mask.sum())
        frame = frame.loc[~mask].reset_index(drop=True)
        self.write_sheet(worksheet_name, frame)
        return deleted

    # ----------------------------
    # Worksheet management
    # ----------------------------
    def create_worksheet(self, worksheet_name: str, columns: Optional[Sequence[str]] = None) -> None:
        columns = list(columns or [])
        if worksheet_name in self.list_worksheets():
            return

        if self.backend == "excel":
            self._write_excel_sheet(worksheet_name, pd.DataFrame(columns=columns))
            return

        self.connect().add_worksheet(title=worksheet_name, rows=1000, cols=max(26, len(columns)))
        if columns:
            self.write_sheet(worksheet_name, pd.DataFrame(columns=columns))

    def delete_worksheet(self, worksheet_name: str) -> bool:
        if worksheet_name not in self.list_worksheets():
            return False

        if self.backend == "excel":
            all_sheets = {name: self.read_sheet(name) for name in self.list_worksheets() if name != worksheet_name}
            with pd.ExcelWriter(self.connect(), engine="openpyxl", mode="w") as writer:
                for name, frame in all_sheets.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
            self._invalidate_cache(worksheet_name)
            return True

        sheet = self.connect().worksheet(worksheet_name)
        self.connect().del_worksheet(sheet)
        self._invalidate_cache(worksheet_name)
        return True

    # ----------------------------
    # Validation
    # ----------------------------
    def ensure_unique_value(self, worksheet_name: str, column: str, value: Any) -> bool:
        frame = self.read_sheet_or_empty(worksheet_name)
        if frame.empty:
            return True

        if column not in frame.columns:
            return True

        existing = frame[column].astype(str).str.strip()
        if str(value).strip() in set(existing.tolist()):
            raise ValidationError(f"Duplicate value '{value}' for column '{column}'.")
        return True

    def ensure_unique_ids(self, worksheet_name: str, id_column: str) -> bool:
        frame = self.read_sheet_or_empty(worksheet_name)
        if frame.empty or id_column not in frame.columns:
            return True

        values = frame[id_column].astype(str).str.strip()
        duplicates = values[values.ne("")].duplicated()
        if duplicates.any():
            raise ValidationError(f"Duplicate IDs found in {worksheet_name}.{id_column}")
        return True

    # ----------------------------
    # Naming convention helpers
    # ----------------------------
    @classmethod
    def normalize_pks(cls, pks_code: str) -> str:
        normalized = str(pks_code).strip().upper()
        if not cls.PKS_PATTERN.match(normalized):
            raise ValidationError("Invalid PKS format. Expected PKS##.")
        return normalized

    def create_school_sheet(self, pks_code: str) -> List[str]:
        pks = self.normalize_pks(pks_code)
        names = [
            f"Classes_{pks}",
            f"Students_{pks}",
            f"Teachers_{pks}",
            f"Monthly_Test_{pks}",
            f"Final_Exam_{pks}",
        ]

        schema = {
            f"Classes_{pks}": ["class_id", "class_name", "teacher_id", "school_id", "pks_code"],
            f"Students_{pks}": [
                "student_id",
                "student_name",
                "gender",
                "class_id",
                "school_id",
                "pks_code",
                "monthly_score",
                "final_score",
            ],
            f"Teachers_{pks}": ["teacher_id", "teacher_name", "subject", "class_id", "school_id", "pks_code"],
            f"Monthly_Test_{pks}": ["student_id", "subject", "score", "session_year", "class_id", "gender"],
            f"Final_Exam_{pks}": ["student_id", "subject", "score", "session_year", "class_id", "gender"],
        }

        for sheet_name in names:
            self.create_worksheet(sheet_name, schema[sheet_name])
        return names

    def create_assessment_worksheet(self, pks_code: str, assessment_type: str) -> str:
        pks = self.normalize_pks(pks_code)
        key = assessment_type.strip().lower()
        if key in {"monthly", "monthly_test"}:
            name = f"Monthly_Test_{pks}"
        elif key in {"final", "final_exam"}:
            name = f"Final_Exam_{pks}"
        else:
            raise ValidationError("assessment_type must be monthly/monthly_test/final/final_exam")

        self.create_worksheet(name, ["student_id", "subject", "score", "session_year", "class_id", "gender"])
        return name

    def create_session_sheets(self, session_year: int, pks_code: str) -> List[str]:
        pks = self.normalize_pks(pks_code)
        year = int(session_year)
        names = [f"{year}_{pks}_Monthly", f"{year}_{pks}_Final"]
        for name in names:
            self.create_worksheet(name, ["student_id", "subject", "score", "class_id", "gender"])
        return names

    def delete_school_data(self, pks_code: str) -> List[str]:
        pks = self.normalize_pks(pks_code)
        deleted: List[str] = []
        for sheet in self.list_worksheets():
            if sheet.endswith(f"_{pks}"):
                if self.delete_worksheet(sheet):
                    deleted.append(sheet)
        return deleted

    # ----------------------------
    # Cache
    # ----------------------------
    def read_sheet_or_empty(self, worksheet_name: str) -> pd.DataFrame:
        if worksheet_name in self.list_worksheets():
            return self.read_sheet(worksheet_name)
        return pd.DataFrame()

    def clear_cache(self, worksheet_name: Optional[str] = None) -> None:
        if worksheet_name:
            self._cache.pop(worksheet_name, None)
            return
        self._cache.clear()

    # ----------------------------
    # Internal helpers
    # ----------------------------
    def _write_excel_sheet(self, worksheet_name: str, frame: pd.DataFrame) -> None:
        existing: Dict[str, pd.DataFrame] = {}
        if os.path.exists(self.excel_path):
            with pd.ExcelFile(self.excel_path) as book:
                for name in book.sheet_names:
                    if name != worksheet_name:
                        existing[name] = pd.read_excel(self.excel_path, sheet_name=name)

        existing[worksheet_name] = frame.copy()
        with pd.ExcelWriter(self.excel_path, engine="openpyxl", mode="w") as writer:
            for name, data in existing.items():
                data.to_excel(writer, sheet_name=name, index=False)

    def _invalidate_cache(self, worksheet_name: str) -> None:
        if self.cache_enabled:
            self._cache.pop(worksheet_name, None)

    def _get_google_worksheet(self, worksheet_name: str):
        try:
            return self.connect().worksheet(worksheet_name)
        except WorksheetNotFound as exc:
            raise ValidationError(f"Worksheet '{worksheet_name}' not found.") from exc

    def _get_or_create_google_sheet(self, worksheet_name: str):
        try:
            return self.connect().worksheet(worksheet_name)
        except WorksheetNotFound:
            self.connect().add_worksheet(title=worksheet_name, rows=1000, cols=30)
            return self.connect().worksheet(worksheet_name)

    # ----------------------------
    # Convenience metadata
    # ----------------------------
    def log_event(self, action: str, details: str) -> None:
        self.create_worksheet("Audit_Log", ["timestamp", "action", "details"])
        self.append_data(
            "Audit_Log",
            {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
                "action": action,
                "details": details,
            },
        )
