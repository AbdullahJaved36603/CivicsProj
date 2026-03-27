from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, TypeVar


T = TypeVar("T")

PASSING_RATIO = 0.5
ABSENT_MARK_TOKEN = "A"
ABSENT_TOKENS = {"", "a", "ab", "absent", "na", "n/a"}


def safe_sheet_read(func: Callable[[], T], retries: int = 3, delay_seconds: float = 1.0) -> T:
    last_error: Optional[Exception] = None
    attempts = max(int(retries), 1)
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(max(float(delay_seconds), 0.0))
    raise Exception("Failed after retries") from last_error


def to_float(value: Any) -> Optional[float]:
    try:
        normalized = str(value).strip()
        if not normalized:
            return None
        return float(normalized)
    except Exception:
        return None


def number_to_string(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(round(float(value), 2))


def is_absent_token(value: Any) -> bool:
    return str(value).strip().lower() in ABSENT_TOKENS


def parse_marks(marks_value: Any, total_marks: Any) -> Dict[str, Any]:
    marks_text = "" if marks_value is None else str(marks_value).strip()
    total_float = to_float(total_marks)
    has_valid_total = total_float is not None and total_float > 0
    normalized_total = number_to_string(total_float) if has_valid_total and total_float is not None else ""

    if is_absent_token(marks_text):
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": normalized_total,
            "total_marks_value": total_float if has_valid_total and total_float is not None else None,
            "is_explicit_absent": True,
            "is_numeric": False,
            "is_valid": True,
            "status": "Absent",
            "percentage": None,
            "error": "",
        }

    marks_float = to_float(marks_text)
    if marks_float is None:
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": normalized_total,
            "total_marks_value": total_float if has_valid_total and total_float is not None else None,
            "is_explicit_absent": False,
            "is_numeric": False,
            "is_valid": False,
            "status": "Absent",
            "percentage": None,
            "error": "marks_not_numeric",
        }

    if marks_float < 0:
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": normalized_total,
            "total_marks_value": total_float if has_valid_total and total_float is not None else None,
            "is_explicit_absent": False,
            "is_numeric": False,
            "is_valid": False,
            "status": "Absent",
            "percentage": None,
            "error": "marks_negative",
        }

    if not has_valid_total:
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": "",
            "total_marks_value": None,
            "is_explicit_absent": False,
            "is_numeric": False,
            "is_valid": False,
            "status": "Absent",
            "percentage": None,
            "error": "total_marks_invalid",
        }

    if total_float is None:
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": "",
            "total_marks_value": None,
            "is_explicit_absent": False,
            "is_numeric": False,
            "is_valid": False,
            "status": "Absent",
            "percentage": None,
            "error": "total_marks_invalid",
        }

    if marks_float > total_float:
        return {
            "raw_marks": marks_text,
            "normalized_marks": ABSENT_MARK_TOKEN,
            "marks_value": None,
            "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
            "normalized_total_marks": normalized_total,
            "total_marks_value": total_float,
            "is_explicit_absent": False,
            "is_numeric": False,
            "is_valid": False,
            "status": "Absent",
            "percentage": None,
            "error": "marks_exceed_total",
        }

    percentage = (marks_float / total_float) * 100 if total_float > 0 else None
    status = "Pass" if marks_float >= (total_float * PASSING_RATIO) else "Fail"

    return {
        "raw_marks": marks_text,
        "normalized_marks": number_to_string(marks_float),
        "marks_value": float(marks_float),
        "raw_total_marks": "" if total_marks is None else str(total_marks).strip(),
        "normalized_total_marks": normalized_total,
        "total_marks_value": float(total_float),
        "is_explicit_absent": False,
        "is_numeric": True,
        "is_valid": True,
        "status": status,
        "percentage": percentage,
        "error": "",
    }
