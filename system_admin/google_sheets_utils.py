from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, Optional, TypeVar


T = TypeVar("T")

PASSING_RATIO = 0.5
ABSENT_MARK_TOKEN = "A"
ABSENT_TOKENS = {"", "a", "ab", "absent", "na", "n/a"}

MAJOR_SUBJECTS = {"english", "urdu", "math", "general science"}
MINOR_SUBJECTS = {
    "social studies",
    "general knowledge",
    "islamiat",
    "geography",
    "history",
    "computer",
}

SUBJECT_CANONICAL_MAP = {
    "eng": "english",
    "english": "english",
    "urdu": "urdu",
    "math": "math",
    "mathematics": "math",
    "science": "general science",
    "general science": "general science",
    "social studies": "social studies",
    "social study": "social studies",
    "sst": "social studies",
    "general knowledge": "general knowledge",
    "gk": "general knowledge",
    "islamiat": "islamiat",
    "islamiyat": "islamiat",
    "geography": "geography",
    "history": "history",
    "computer": "computer",
    "computer science": "computer",
}

CLASS_SUBJECT_MAP = {
    (2, 3): ["english", "urdu", "math", "general knowledge", "islamiat"],
    (4, 5): ["english", "urdu", "math", "general science", "islamiat", "social studies"],
    (6, 8): ["english", "urdu", "math", "general science", "geography", "computer", "history", "islamiat"],
}

MONTESSORI_TOKENS = {"montessori", "nursery", "prep", "kg", "kindergarten", "play"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def get_class_number(class_name: Any) -> Optional[int]:
    text = str(class_name or "").strip()
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def is_montessori_class(class_name: Any) -> bool:
    normalized = _normalize_text(class_name)
    class_number = get_class_number(class_name)
    if class_number is not None and class_number <= 1:
        return True
    return any(token in normalized for token in MONTESSORI_TOKENS)


def get_class_pass_ratio(class_name: Any) -> float:
    return 0.5 if is_montessori_class(class_name) else 0.4


def canonical_subject_name(subject_name: Any) -> str:
    normalized = _normalize_text(subject_name)
    return SUBJECT_CANONICAL_MAP.get(normalized, normalized)


def classify_subject(subject_name: Any) -> str:
    canonical = canonical_subject_name(subject_name)
    if canonical in MAJOR_SUBJECTS:
        return "major"
    if canonical in MINOR_SUBJECTS:
        return "minor"
    return "other"


def get_expected_subjects_for_class(class_name: Any) -> set[str]:
    class_number = get_class_number(class_name)
    if class_number is None:
        return set()

    for (start, end), subjects in CLASS_SUBJECT_MAP.items():
        if start <= class_number <= end:
            return {canonical_subject_name(subject) for subject in subjects}
    return set()


def evaluate_student_result(class_name: Any, subject_rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    pass_ratio = get_class_pass_ratio(class_name)
    expected_subjects = get_expected_subjects_for_class(class_name)

    failed_major_subjects = 0
    failed_minor_subjects = 0
    evaluated_subject_rows: list[Dict[str, Any]] = []

    for row in subject_rows:
        raw_subject_name = str(row.get("subject_name", "")).strip()
        canonical_name = canonical_subject_name(raw_subject_name)

        if expected_subjects and canonical_name not in expected_subjects:
            continue

        subject_category = classify_subject(canonical_name)
        if subject_category == "other":
            continue

        parsed = parse_marks(row.get("marks", ""), row.get("total_marks", ""), passing_ratio=pass_ratio)
        percentage_value = parsed.get("percentage")
        percentage = round(float(percentage_value), 2) if percentage_value is not None else 0.0

        parsed_status = str(parsed.get("status", "Absent"))
        subject_status = "Pass" if parsed_status == "Pass" else "Fail"

        if subject_status == "Fail":
            if subject_category == "major":
                failed_major_subjects += 1
            elif subject_category == "minor":
                failed_minor_subjects += 1

        evaluated_subject_rows.append(
            {
                "subject_name": raw_subject_name or canonical_name.title(),
                "canonical_subject_name": canonical_name,
                "subject_category": subject_category.title(),
                "subject_status": subject_status,
                "subject_percentage": percentage,
                "marks": parsed.get("normalized_marks", ABSENT_MARK_TOKEN),
                "total_marks": parsed.get("normalized_total_marks", ""),
            }
        )

    final_status = "Promoted"
    if failed_major_subjects >= 2:
        final_status = "Fail"
    elif failed_major_subjects >= 1 and failed_minor_subjects >= 2:
        final_status = "Fail"

    return {
        "pass_ratio": pass_ratio,
        "failed_major_subjects": failed_major_subjects,
        "failed_minor_subjects": failed_minor_subjects,
        "final_status": final_status,
        "subject_rows": evaluated_subject_rows,
    }


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


def parse_marks(marks_value: Any, total_marks: Any, passing_ratio: float = PASSING_RATIO) -> Dict[str, Any]:
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
    effective_ratio = float(passing_ratio) if float(passing_ratio) > 0 else PASSING_RATIO
    status = "Pass" if marks_float >= (total_float * effective_ratio) else "Fail"

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
