from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

try:
    from .google_sheets_controller import GoogleSheetsController, get_controller
except ImportError:
    from google_sheets_controller import GoogleSheetsController, get_controller


def _response(success: bool, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


class SchoolAnalytics:
    """Read-only analytics for dashboard views."""

    def __init__(self, controller: Optional[GoogleSheetsController] = None) -> None:
        self.controller = controller or get_controller()

    @staticmethod
    def _normalize_header(header: str) -> str:
        return header.strip().lower().replace(" ", "_")

    def _resolve_column_index(self, headers: List[str], candidates: List[str]) -> Optional[int]:
        normalized_headers = [self._normalize_header(value) for value in headers]
        normalized_candidates = {self._normalize_header(candidate) for candidate in candidates}
        for index, header in enumerate(normalized_headers):
            if header in normalized_candidates:
                return index
        return None

    @staticmethod
    def _to_float(value: str) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return None

    def _load_table(self, tab_name: str) -> Dict[str, Any]:
        rows = self.controller.read_tab(tab_name)
        if not rows:
            return {"headers": [], "records": []}
        headers = rows[0]
        records = rows[1:] if len(rows) > 1 else []
        return {"headers": headers, "records": records}

    def get_average_marks_per_class(self, tab_name: str = "Performance") -> Dict[str, Any]:
        try:
            table = self._load_table(tab_name)
            headers: List[str] = table["headers"]
            records: List[List[str]] = table["records"]
            if not headers:
                return _response(True, "No analytics data available.", {"average_marks_per_class": {}})

            class_index = self._resolve_column_index(headers, ["class_id", "class", "class_name"])
            marks_index = self._resolve_column_index(headers, ["marks", "score", "total_marks", "final_marks"])
            if class_index is None or marks_index is None:
                return _response(False, "Required columns for class analytics are missing.")

            grouped: Dict[str, List[float]] = {}
            for row in records:
                if class_index >= len(row) or marks_index >= len(row):
                    continue
                class_id = row[class_index].strip()
                marks = self._to_float(row[marks_index])
                if not class_id or marks is None:
                    continue
                grouped.setdefault(class_id, []).append(marks)

            averages = {class_id: round(mean(scores), 2) for class_id, scores in grouped.items() if scores}
            return _response(True, "Average marks per class computed.", {"average_marks_per_class": averages})
        except Exception as exc:
            return _response(False, f"Failed to compute class analytics: {exc}")

    def get_average_marks_per_subject(self, tab_name: str = "Performance") -> Dict[str, Any]:
        try:
            table = self._load_table(tab_name)
            headers: List[str] = table["headers"]
            records: List[List[str]] = table["records"]
            if not headers:
                return _response(True, "No analytics data available.", {"average_marks_per_subject": {}})

            subject_index = self._resolve_column_index(headers, ["subject_id", "subject", "subject_name"])
            marks_index = self._resolve_column_index(headers, ["marks", "score", "total_marks", "final_marks"])
            if subject_index is None or marks_index is None:
                return _response(False, "Required columns for subject analytics are missing.")

            grouped: Dict[str, List[float]] = {}
            for row in records:
                if subject_index >= len(row) or marks_index >= len(row):
                    continue
                subject_id = row[subject_index].strip()
                marks = self._to_float(row[marks_index])
                if not subject_id or marks is None:
                    continue
                grouped.setdefault(subject_id, []).append(marks)

            averages = {subject_id: round(mean(scores), 2) for subject_id, scores in grouped.items() if scores}
            return _response(True, "Average marks per subject computed.", {"average_marks_per_subject": averages})
        except Exception as exc:
            return _response(False, f"Failed to compute subject analytics: {exc}")

    def get_gender_comparison(self, tab_name: str = "Performance") -> Dict[str, Any]:
        try:
            table = self._load_table(tab_name)
            headers: List[str] = table["headers"]
            records: List[List[str]] = table["records"]
            if not headers:
                return _response(True, "No analytics data available.", {"male_vs_female": {}})

            gender_index = self._resolve_column_index(headers, ["gender", "sex"])
            marks_index = self._resolve_column_index(headers, ["marks", "score", "total_marks", "final_marks"])
            if gender_index is None or marks_index is None:
                return _response(False, "Required columns for gender comparison are missing.")

            grouped: Dict[str, List[float]] = {"male": [], "female": []}
            for row in records:
                if gender_index >= len(row) or marks_index >= len(row):
                    continue
                gender = row[gender_index].strip().lower()
                marks = self._to_float(row[marks_index])
                if marks is None:
                    continue
                if gender in {"male", "m"}:
                    grouped["male"].append(marks)
                elif gender in {"female", "f"}:
                    grouped["female"].append(marks)

            comparison = {
                "male_average": round(mean(grouped["male"]), 2) if grouped["male"] else 0.0,
                "female_average": round(mean(grouped["female"]), 2) if grouped["female"] else 0.0,
                "difference": round(
                    (mean(grouped["male"]) if grouped["male"] else 0.0)
                    - (mean(grouped["female"]) if grouped["female"] else 0.0),
                    2,
                ),
            }
            return _response(True, "Male vs Female comparison computed.", {"male_vs_female": comparison})
        except Exception as exc:
            return _response(False, f"Failed to compute gender comparison: {exc}")

    def get_monthly_vs_final_comparison(self, tab_name: str = "Performance") -> Dict[str, Any]:
        try:
            table = self._load_table(tab_name)
            headers: List[str] = table["headers"]
            records: List[List[str]] = table["records"]
            if not headers:
                return _response(True, "No analytics data available.", {"monthly_vs_final": {}})

            monthly_index = self._resolve_column_index(
                headers,
                ["monthly_marks", "monthly_score", "month_marks", "monthly"],
            )
            final_index = self._resolve_column_index(headers, ["final_marks", "final_score", "final", "marks"])
            if monthly_index is None or final_index is None:
                return _response(False, "Required columns for monthly vs final comparison are missing.")

            monthly_scores: List[float] = []
            final_scores: List[float] = []
            for row in records:
                if monthly_index >= len(row) or final_index >= len(row):
                    continue
                monthly = self._to_float(row[monthly_index])
                final = self._to_float(row[final_index])
                if monthly is None or final is None:
                    continue
                monthly_scores.append(monthly)
                final_scores.append(final)

            monthly_average = round(mean(monthly_scores), 2) if monthly_scores else 0.0
            final_average = round(mean(final_scores), 2) if final_scores else 0.0
            summary = {
                "monthly_average": monthly_average,
                "final_average": final_average,
                "delta": round(final_average - monthly_average, 2),
            }
            return _response(True, "Monthly vs Final comparison computed.", {"monthly_vs_final": summary})
        except Exception as exc:
            return _response(False, f"Failed to compute monthly vs final comparison: {exc}")

    def get_dashboard_analytics(self, tab_name: str = "Performance") -> Dict[str, Any]:
        try:
            class_data = self.get_average_marks_per_class(tab_name)
            subject_data = self.get_average_marks_per_subject(tab_name)
            gender_data = self.get_gender_comparison(tab_name)
            monthly_final_data = self.get_monthly_vs_final_comparison(tab_name)

            if not all(
                result.get("success")
                for result in [class_data, subject_data, gender_data, monthly_final_data]
            ):
                return _response(
                    False,
                    "One or more analytics computations failed.",
                    {
                        "average_marks_per_class": class_data,
                        "average_marks_per_subject": subject_data,
                        "male_vs_female": gender_data,
                        "monthly_vs_final": monthly_final_data,
                    },
                )

            return _response(
                True,
                "Analytics computed successfully.",
                {
                    **class_data.get("data", {}),
                    **subject_data.get("data", {}),
                    **gender_data.get("data", {}),
                    **monthly_final_data.get("data", {}),
                },
            )
        except Exception as exc:
            return _response(False, f"Failed to build analytics dashboard data: {exc}")


_ANALYTICS: Optional[SchoolAnalytics] = None


def get_school_analytics() -> SchoolAnalytics:
    global _ANALYTICS
    if _ANALYTICS is None:
        _ANALYTICS = SchoolAnalytics()
    return _ANALYTICS
