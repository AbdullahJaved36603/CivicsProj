import re
import ssl
from functools import lru_cache
from typing import Dict, List, Optional

import pandas as pd
from googleapiclient.errors import HttpError

from google_sheets_controller import extract_sheet_id, list_school_sheet_records, service


META_COLS_COUNT = 4
DATA_END_COL = 17
_REQUEST_STATS = {"total": 0, "tabs": 0, "read": 0, "other": 0}


def reset_request_stats() -> None:
    _REQUEST_STATS["total"] = 0
    _REQUEST_STATS["tabs"] = 0
    _REQUEST_STATS["read"] = 0
    _REQUEST_STATS["other"] = 0


def get_request_stats() -> Dict[str, int]:
    return dict(_REQUEST_STATS)


def _safe_execute(request, context: str):
    _REQUEST_STATS["total"] += 1
    if context.startswith("tabs"):
        _REQUEST_STATS["tabs"] += 1
    elif context.startswith("read"):
        _REQUEST_STATS["read"] += 1
    else:
        _REQUEST_STATS["other"] += 1

    try:
        return request.execute()
    except ssl.SSLError as exc:
        print(f"SSL error during {context}: {exc}")
        return None
    except HttpError as exc:
        print(f"Google API error during {context}: {exc}")
        return None
    except Exception as exc:
        print(f"Unexpected error during {context}: {exc}")
        return None


def _normalize_row(row: List[str], width: int = DATA_END_COL) -> List[str]:
    raw = row or []
    padded = raw + [""] * max(0, width - len(raw))
    return ["" if v is None else str(v).strip() for v in padded[:width]]


def _is_blank(v: str) -> bool:
    return not v or not str(v).strip()


def _is_absent(v: str) -> bool:
    token = str(v).strip().upper().replace(".", "")
    return token == "A"


def _to_float(v: str) -> Optional[float]:
    if _is_blank(v) or _is_absent(v):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _max_marks(header_text: str) -> Optional[float]:
    if _is_blank(header_text):
        return None
    match = re.search(r"\((\d+(?:\.\d+)?)\)", header_text)
    if match:
        return float(match.group(1))
    fallback = re.search(r"(\d+(?:\.\d+)?)$", header_text)
    if fallback:
        return float(fallback.group(1))
    return None


def _normalize_subject_name(subject_text: str) -> str:
    text = (subject_text or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    text = re.sub(r"\s+\d+(?:\.\d+)?\s*$", "", text)
    return text or (subject_text or "Unknown")


def _sheet_tabs(spreadsheet_id: str) -> List[str]:
    return list(_sheet_tabs_cached(spreadsheet_id))


def _tab_name_from_range(range_name: str) -> str:
    tab = (range_name or "").split("!")[0]
    if tab.startswith("'") and tab.endswith("'"):
        tab = tab[1:-1]
    return tab


@lru_cache(maxsize=256)
def _sheet_tabs_cached(spreadsheet_id: str) -> tuple:
    metadata = _safe_execute(service.spreadsheets().get(spreadsheetId=spreadsheet_id), f"tabs {spreadsheet_id}")
    if not metadata:
        return tuple()
    return tuple(s["properties"]["title"] for s in metadata.get("sheets", []))


@lru_cache(maxsize=256)
def _sheet_tab_rows_cached(spreadsheet_id: str) -> Dict[str, tuple]:
    tabs = _sheet_tabs(spreadsheet_id)
    if not tabs:
        return {}

    ranges = [f"{tab}!A1:Q300" for tab in tabs]
    result = _safe_execute(
        service.spreadsheets().values().batchGet(spreadsheetId=spreadsheet_id, ranges=ranges),
        f"read-batch {spreadsheet_id}",
    )
    if not result:
        return {}

    rows_by_tab: Dict[str, tuple] = {}
    for value_range in result.get("valueRanges", []):
        range_name = value_range.get("range", "")
        tab_name = _tab_name_from_range(range_name)
        rows = value_range.get("values", [])
        rows_by_tab[tab_name] = tuple(tuple(cell for cell in row) for row in rows)

    for tab in tabs:
        rows_by_tab.setdefault(tab, tuple())

    return rows_by_tab


def _read_tab_rows(spreadsheet_id: str, tab_name: str) -> List[List[str]]:
    cached = _read_tab_rows_cached(spreadsheet_id, tab_name)
    return [list(r) for r in cached]


@lru_cache(maxsize=1024)
def _read_tab_rows_cached(spreadsheet_id: str, tab_name: str) -> tuple:
    rows_by_tab = _sheet_tab_rows_cached(spreadsheet_id)
    return rows_by_tab.get(tab_name, tuple())


def clear_analytics_cache() -> None:
    _sheet_tabs_cached.cache_clear()
    _sheet_tab_rows_cached.cache_clear()
    _read_tab_rows_cached.cache_clear()


def _month_blocks(header_row_1: List[str]) -> List[Dict]:
    starts: List[int] = []
    for idx in range(META_COLS_COUNT, DATA_END_COL):
        if not _is_blank(header_row_1[idx]):
            starts.append(idx)

    blocks: List[Dict] = []
    for i, start in enumerate(starts):
        end = (starts[i + 1] - 1) if i + 1 < len(starts) else (DATA_END_COL - 1)
        blocks.append({"month": header_row_1[start], "start": start, "end": end})
    return blocks


def _is_class_tab(spreadsheet_id: str, tab_name: str) -> bool:
    rows = _read_tab_rows(spreadsheet_id, tab_name)
    if len(rows) < 3:
        return False
    row3 = _normalize_row(rows[2])
    return row3[0].lower() == "s.no"


def _build_class_table_from_rows(rows: List[List[str]]) -> Optional[Dict]:
    if len(rows) < 5:
        return None

    row1 = _normalize_row(rows[0])
    row3 = _normalize_row(rows[2])
    if row3[0].lower() != "s.no":
        return None

    data_rows: List[List[str]] = []
    for raw in rows[4:]:
        r = _normalize_row(raw)
        if _is_blank(r[0]) and _is_blank(r[1]) and _is_blank(r[3]):
            continue
        if r[1].lower().startswith("total") or r[1].lower() in {"average"}:
            continue
        data_rows.append(r)

    return {
        "headers_month": row1,
        "headers_subject": row3,
        "month_blocks": _month_blocks(row1),
        "rows": data_rows,
    }


def build_school_analytics_cache(school_sheet_url: str) -> Dict:
    spreadsheet_id = extract_sheet_id(school_sheet_url)
    if not spreadsheet_id:
        return {"success": False, "message": "Invalid school sheet URL"}

    tabs = _sheet_tabs(spreadsheet_id)
    classes: Dict[str, Dict] = {}
    month_set = set()
    for tab in tabs:
        rows = _read_tab_rows(spreadsheet_id, tab)
        table = _build_class_table_from_rows(rows)
        if not table:
            continue
        classes[tab] = table
        for block in table["month_blocks"]:
            if block.get("month"):
                month_set.add(block["month"])

    return {
        "success": True,
        "school_sheet_url": school_sheet_url,
        "spreadsheet_id": spreadsheet_id,
        "classes": classes,
        "class_tabs": sorted(classes.keys()),
        "months": sorted(month_set),
    }


def build_session_analytics_cache(session_name: str) -> Dict:
    records = list_school_sheet_records(session_name=session_name, active_only=True)
    schools = []
    month_set = set()
    class_set = set()

    for record in records:
        school_name = record["school_name"]
        school_url = record.get("sheet_url", "")
        school_cache = build_school_analytics_cache(school_url)
        if not school_cache.get("success"):
            continue
        month_set.update(school_cache.get("months", []))
        class_set.update(school_cache.get("class_tabs", []))
        schools.append(
            {
                "school_name": school_name,
                "sheet_url": school_url,
                "cache": school_cache,
            }
        )

    return {
        "success": True,
        "session_name": session_name,
        "schools": schools,
        "months": sorted(month_set),
        "classes": sorted(class_set),
    }


def list_class_tabs(school_sheet_url: str, school_cache: Optional[Dict] = None) -> List[str]:
    if school_cache and school_cache.get("success"):
        return school_cache.get("class_tabs", [])

    spreadsheet_id = extract_sheet_id(school_sheet_url)
    if not spreadsheet_id:
        return []

    tabs = _sheet_tabs(spreadsheet_id)
    return [tab for tab in tabs if _is_class_tab(spreadsheet_id, tab)]


def _class_table(school_sheet_url: str, class_name: str, school_cache: Optional[Dict] = None) -> Optional[Dict]:
    if school_cache and school_cache.get("success"):
        return school_cache.get("classes", {}).get(class_name)

    spreadsheet_id = extract_sheet_id(school_sheet_url)
    if not spreadsheet_id:
        return None

    tabs = _sheet_tabs(spreadsheet_id)
    if class_name not in tabs:
        return None

    rows = _read_tab_rows(spreadsheet_id, class_name)
    return _build_class_table_from_rows(rows)


def list_available_months(school_sheet_url: str, class_name: Optional[str] = None, school_cache: Optional[Dict] = None) -> List[str]:
    if school_cache and school_cache.get("success") and not class_name:
        return school_cache.get("months", [])

    classes = [class_name] if class_name else list_class_tabs(school_sheet_url, school_cache=school_cache)
    months: List[str] = []
    for cls in classes:
        table = _class_table(school_sheet_url, cls, school_cache=school_cache)
        if not table:
            continue
        for block in table["month_blocks"]:
            m = block["month"]
            if m and m not in months:
                months.append(m)
    return months


def _month_metrics_for_class(table: Dict, month_label: str) -> Dict:
    block = next((b for b in table["month_blocks"] if b["month"] == month_label), None)
    if not block:
        return {"success": False, "message": f"Month '{month_label}' not found"}

    subject_rows = []
    total_entries = 0
    total_passed = 0
    total_failed = 0
    total_appeared = 0
    total_possible_students = 0

    for col in range(block["start"], block["end"] + 1):
        subject = table["headers_subject"][col] or f"Subject {col + 1}"
        max_mark = _max_marks(subject)
        pass_mark = max_mark / 2.0 if max_mark else None

        subject_total = 0.0
        subject_students = 0
        subject_appeared = 0
        subject_absent = 0
        subject_passed = 0
        subject_failed = 0

        for row in table["rows"]:
            cell = row[col] if col < len(row) else ""
            if _is_blank(cell):
                continue
            subject_students += 1
            if _is_absent(cell):
                subject_absent += 1
                continue

            num = _to_float(cell)
            if num is None:
                continue

            subject_total += num
            subject_appeared += 1
            if pass_mark is not None:
                if num >= pass_mark:
                    subject_passed += 1
                else:
                    subject_failed += 1

        average = (subject_total / subject_appeared) if subject_appeared else 0.0
        pass_rate = (subject_passed / subject_appeared * 100.0) if subject_appeared else 0.0

        subject_rows.append(
            {
                "subject": subject,
                "max_mark": max_mark or 0.0,
                "total_marks": round(subject_total, 2),
                "average": round(average, 2),
                "total_students": subject_students,
                "appeared": subject_appeared,
                "absent": subject_absent,
                "passed": subject_passed,
                "failed": subject_failed,
                "pass_rate": round(pass_rate, 2),
            }
        )

        total_possible_students += subject_students
        total_appeared += subject_appeared
        total_passed += subject_passed
        total_failed += subject_failed
        total_entries += 1

    overall_pass_rate = (total_passed / total_appeared * 100.0) if total_appeared else 0.0
    overall_fail_rate = (total_failed / total_appeared * 100.0) if total_appeared else 0.0

    return {
        "success": True,
        "month": month_label,
        "subject_stats": subject_rows,
        "overall": {
            "subjects_count": total_entries,
            "total_students": total_possible_students,
            "appeared": total_appeared,
            "passed": total_passed,
            "failed": total_failed,
            "pass_rate": round(overall_pass_rate, 2),
            "fail_rate": round(overall_fail_rate, 2),
        },
    }


def get_school_month_class_analytics(school_sheet_url: str, class_name: str, month_label: str, school_cache: Optional[Dict] = None) -> Dict:
    table = _class_table(school_sheet_url, class_name, school_cache=school_cache)
    if not table:
        return {"success": False, "message": f"Class '{class_name}' not found or invalid format"}
    metrics = _month_metrics_for_class(table, month_label)
    metrics["class_name"] = class_name
    return metrics


def get_school_overview_analytics(
    school_sheet_url: str,
    month_label: str,
    class_name: Optional[str] = None,
    school_cache: Optional[Dict] = None,
) -> Dict:
    class_tabs = [class_name] if class_name else list_class_tabs(school_sheet_url, school_cache=school_cache)
    if not class_tabs:
        return {"success": False, "message": "No class tabs found"}

    class_rows: List[Dict] = []
    for cls in class_tabs:
        metrics = get_school_month_class_analytics(school_sheet_url, cls, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue
        overall = metrics["overall"]
        class_rows.append(
            {
                "class_name": cls,
                "appeared": overall["appeared"],
                "passed": overall["passed"],
                "failed": overall["failed"],
                "pass_rate": overall["pass_rate"],
                "fail_rate": overall["fail_rate"],
            }
        )

    if not class_rows:
        return {"success": False, "message": f"No data for month '{month_label}'"}

    return {
        "success": True,
        "month": month_label,
        "class_rows": class_rows,
    }


def get_school_subject_analytics(
    school_sheet_url: str,
    month_label: str,
    class_name: Optional[str] = None,
    school_cache: Optional[Dict] = None,
) -> Dict:
    class_tabs = [class_name] if class_name else list_class_tabs(school_sheet_url, school_cache=school_cache)
    if not class_tabs:
        return {"success": False, "message": "No class tabs found"}

    bucket: Dict[str, Dict[str, float]] = {}
    included_classes = 0
    for cls in class_tabs:
        metrics = get_school_month_class_analytics(school_sheet_url, cls, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue
        included_classes += 1
        for s in metrics.get("subject_stats", []):
            subject = s.get("subject", "")
            if subject not in bucket:
                bucket[subject] = {
                    "total_students": 0.0,
                    "appeared": 0.0,
                    "absent": 0.0,
                    "passed": 0.0,
                    "failed": 0.0,
                    "total_marks": 0.0,
                }

            bucket[subject]["total_students"] += float(s.get("total_students", 0))
            bucket[subject]["appeared"] += float(s.get("appeared", 0))
            bucket[subject]["absent"] += float(s.get("absent", 0))
            bucket[subject]["passed"] += float(s.get("passed", 0))
            bucket[subject]["failed"] += float(s.get("failed", 0))
            bucket[subject]["total_marks"] += float(s.get("total_marks", 0.0))

    if not bucket:
        return {"success": False, "message": f"No subject data for month '{month_label}'"}

    rows: List[Dict] = []
    for subject, agg in bucket.items():
        appeared = agg["appeared"]
        pass_rate = (agg["passed"] / appeared * 100.0) if appeared else 0.0
        average = (agg["total_marks"] / appeared) if appeared else 0.0
        rows.append(
            {
                "subject": subject,
                "total_students": int(agg["total_students"]),
                "appeared": int(agg["appeared"]),
                "absent": int(agg["absent"]),
                "passed": int(agg["passed"]),
                "failed": int(agg["failed"]),
                "average": round(average, 2),
                "pass_rate": round(pass_rate, 2),
            }
        )

    rows = sorted(rows, key=lambda r: r["subject"])
    return {
        "success": True,
        "month": month_label,
        "class_name": class_name or "All",
        "included_classes": included_classes,
        "subject_rows": rows,
    }


def get_school_class_subject_analytics(
    school_sheet_url: str,
    month_label: str,
    school_cache: Optional[Dict] = None,
) -> Dict:
    class_tabs = list_class_tabs(school_sheet_url, school_cache=school_cache)
    if not class_tabs:
        return {"success": False, "message": "No class tabs found"}

    rows: List[Dict] = []
    for cls in class_tabs:
        metrics = get_school_month_class_analytics(school_sheet_url, cls, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue

        for s in metrics.get("subject_stats", []):
            rows.append(
                {
                    "class_name": cls,
                    "subject": s.get("subject", ""),
                    "total_students": int(s.get("total_students", 0)),
                    "appeared": int(s.get("appeared", 0)),
                    "absent": int(s.get("absent", 0)),
                    "passed": int(s.get("passed", 0)),
                    "failed": int(s.get("failed", 0)),
                    "average": round(float(s.get("average", 0.0)), 2),
                    "pass_rate": round(float(s.get("pass_rate", 0.0)), 2),
                }
            )

    if not rows:
        return {"success": False, "message": f"No class-subject data for month '{month_label}'"}

    rows = sorted(rows, key=lambda r: (r["class_name"], r["subject"]))
    return {
        "success": True,
        "month": month_label,
        "class_subject_rows": rows,
    }


def get_system_wide_class_analytics(
    session_name: str,
    month_label: str,
    class_name: str,
    session_cache: Optional[Dict] = None,
) -> Dict:
    school_entries = session_cache.get("schools", []) if session_cache else None
    if school_entries is None:
        records = list_school_sheet_records(session_name=session_name, active_only=True)
        school_entries = [{"school_name": r["school_name"], "sheet_url": r.get("sheet_url", ""), "cache": None} for r in records]

    school_rows: List[Dict] = []
    for entry in school_entries:
        school_name = entry["school_name"]
        school_url = entry.get("sheet_url", "")
        school_cache = entry.get("cache")
        metrics = get_school_month_class_analytics(school_url, class_name, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue
        overall = metrics["overall"]
        school_rows.append(
            {
                "school_name": school_name,
                "class_name": class_name,
                "month": month_label,
                "appeared": overall["appeared"],
                "passed": overall["passed"],
                "failed": overall["failed"],
                "pass_rate": overall["pass_rate"],
                "fail_rate": overall["fail_rate"],
            }
        )

    if not school_rows:
        return {"success": False, "message": "No matching class data found across schools"}

    return {"success": True, "rows": school_rows}


def get_system_wide_subject_analytics(
    session_name: str,
    month_label: str,
    class_name: str,
    session_cache: Optional[Dict] = None,
) -> Dict:
    school_entries = session_cache.get("schools", []) if session_cache else None
    if school_entries is None:
        records = list_school_sheet_records(session_name=session_name, active_only=True)
        school_entries = [{"school_name": r["school_name"], "sheet_url": r.get("sheet_url", ""), "cache": None} for r in records]

    bucket: Dict[str, Dict[str, float]] = {}
    for entry in school_entries:
        school_url = entry.get("sheet_url", "")
        school_cache = entry.get("cache")
        metrics = get_school_month_class_analytics(school_url, class_name, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue
        for s in metrics.get("subject_stats", []):
            subject = s.get("subject", "")
            if subject not in bucket:
                bucket[subject] = {"appeared": 0.0, "passed": 0.0, "failed": 0.0, "total_marks": 0.0}
            bucket[subject]["appeared"] += float(s.get("appeared", 0))
            bucket[subject]["passed"] += float(s.get("passed", 0))
            bucket[subject]["failed"] += float(s.get("failed", 0))
            bucket[subject]["total_marks"] += float(s.get("total_marks", 0.0))

    rows = []
    for subject, agg in bucket.items():
        appeared = agg["appeared"]
        pass_rate = (agg["passed"] / appeared * 100.0) if appeared else 0.0
        avg = (agg["total_marks"] / appeared) if appeared else 0.0
        rows.append(
            {
                "subject": subject,
                "appeared": int(appeared),
                "passed": int(agg["passed"]),
                "failed": int(agg["failed"]),
                "average": round(avg, 2),
                "pass_rate": round(pass_rate, 2),
            }
        )

    if not rows:
        return {"success": False, "message": "No subject analytics available for selected month/class"}
    rows = sorted(rows, key=lambda r: r["subject"])
    return {"success": True, "rows": rows}


def get_system_wide_school_subject_analytics(
    session_name: str,
    month_label: str,
    class_name: str,
    session_cache: Optional[Dict] = None,
) -> Dict:
    school_entries = session_cache.get("schools", []) if session_cache else None
    if school_entries is None:
        records = list_school_sheet_records(session_name=session_name, active_only=True)
        school_entries = [{"school_name": r["school_name"], "sheet_url": r.get("sheet_url", ""), "cache": None} for r in records]

    school_subject_rows: List[Dict] = []
    subject_bucket: Dict[str, Dict[str, float]] = {}

    for entry in school_entries:
        school_name = entry.get("school_name", "")
        school_url = entry.get("sheet_url", "")
        school_cache = entry.get("cache")
        metrics = get_school_month_class_analytics(school_url, class_name, month_label, school_cache=school_cache)
        if not metrics.get("success"):
            continue

        for s in metrics.get("subject_stats", []):
            subject = s.get("subject", "")
            row = {
                "school_name": school_name,
                "subject": subject,
                "appeared": int(s.get("appeared", 0)),
                "passed": int(s.get("passed", 0)),
                "failed": int(s.get("failed", 0)),
                "average": round(float(s.get("average", 0.0)), 2),
                "pass_rate": round(float(s.get("pass_rate", 0.0)), 2),
            }
            school_subject_rows.append(row)

            if subject not in subject_bucket:
                subject_bucket[subject] = {"appeared": 0.0, "passed": 0.0, "failed": 0.0, "total_marks": 0.0}
            subject_bucket[subject]["appeared"] += float(s.get("appeared", 0))
            subject_bucket[subject]["passed"] += float(s.get("passed", 0))
            subject_bucket[subject]["failed"] += float(s.get("failed", 0))
            subject_bucket[subject]["total_marks"] += float(s.get("total_marks", 0.0))

    if not school_subject_rows:
        return {
            "success": False,
            "message": "No subject analytics available for selected month/class",
        }

    subject_summary = []
    for subject, agg in subject_bucket.items():
        appeared = agg["appeared"]
        pass_rate = (agg["passed"] / appeared * 100.0) if appeared else 0.0
        avg = (agg["total_marks"] / appeared) if appeared else 0.0
        subject_summary.append(
            {
                "subject": subject,
                "appeared": int(appeared),
                "passed": int(agg["passed"]),
                "failed": int(agg["failed"]),
                "average": round(avg, 2),
                "pass_rate": round(pass_rate, 2),
            }
        )

    school_subject_rows = sorted(school_subject_rows, key=lambda r: (r["subject"], r["school_name"]))
    subject_summary = sorted(subject_summary, key=lambda r: r["subject"])
    schools_count = len({r["school_name"] for r in school_subject_rows})

    return {
        "success": True,
        "session_name": session_name,
        "month": month_label,
        "class_name": class_name,
        "schools_count": schools_count,
        "school_subject_rows": school_subject_rows,
        "subject_summary": subject_summary,
    }


def get_system_wide_class_subject_analytics(
    session_name: str,
    class_name: str,
    session_cache: Optional[Dict] = None,
) -> Dict:
    school_entries = session_cache.get("schools", []) if session_cache else None
    if school_entries is None:
        records = list_school_sheet_records(session_name=session_name, active_only=True)
        school_entries = [{"school_name": r["school_name"], "sheet_url": r.get("sheet_url", ""), "cache": None} for r in records]

    bucket: Dict[str, Dict[str, float]] = {}
    schools_with_class = 0

    for entry in school_entries:
        school_url = entry.get("sheet_url", "")
        school_cache = entry.get("cache")
        table = _class_table(school_url, class_name, school_cache=school_cache)
        if not table:
            continue

        schools_with_class += 1
        for block in table.get("month_blocks", []):
            for col in range(block["start"], block["end"] + 1):
                header = table["headers_subject"][col] or f"Subject {col + 1}"
                subject = _normalize_subject_name(header)
                max_mark = _max_marks(header)
                pass_mark = (max_mark / 2.0) if max_mark else None

                if subject not in bucket:
                    bucket[subject] = {
                        "total_students": 0.0,
                        "appeared": 0.0,
                        "absent": 0.0,
                        "passed": 0.0,
                        "failed": 0.0,
                        "total_marks": 0.0,
                    }

                for row in table.get("rows", []):
                    cell = row[col] if col < len(row) else ""
                    if _is_blank(cell):
                        continue

                    bucket[subject]["total_students"] += 1.0
                    if _is_absent(cell):
                        bucket[subject]["absent"] += 1.0
                        continue

                    num = _to_float(cell)
                    if num is None:
                        continue

                    bucket[subject]["appeared"] += 1.0
                    bucket[subject]["total_marks"] += num

                    if pass_mark is not None:
                        if num >= pass_mark:
                            bucket[subject]["passed"] += 1.0
                        else:
                            bucket[subject]["failed"] += 1.0

    rows: List[Dict] = []
    for subject, agg in bucket.items():
        appeared = agg["appeared"]
        pass_rate = (agg["passed"] / appeared * 100.0) if appeared else 0.0
        average = (agg["total_marks"] / appeared) if appeared else 0.0
        rows.append(
            {
                "subject": subject,
                "total_students": int(agg["total_students"]),
                "appeared": int(appeared),
                "absent": int(agg["absent"]),
                "passed": int(agg["passed"]),
                "failed": int(agg["failed"]),
                "average": round(average, 2),
                "pass_rate": round(pass_rate, 2),
            }
        )

    if not rows:
        return {
            "success": False,
            "message": f"No subject analytics available for class '{class_name}' across selected session",
        }

    rows = sorted(rows, key=lambda r: r["subject"])
    return {
        "success": True,
        "class_name": class_name,
        "schools_count": schools_with_class,
        "rows": rows,
    }


def get_class_performance(school_sheet_url: str, class_name: str) -> Dict:
    months = list_available_months(school_sheet_url, class_name)
    if not months:
        return {"success": False, "message": f"No month blocks found for class '{class_name}'"}
    latest_month = months[-1]
    result = get_school_month_class_analytics(school_sheet_url, class_name, latest_month)
    result["selected_month"] = latest_month
    return result


def get_subject_performance(school_sheet_url: str) -> Dict:
    classes = list_class_tabs(school_sheet_url)
    if not classes:
        return {"success": False, "message": "No class tabs found"}

    subject_bucket: Dict[str, List[float]] = {}
    for cls in classes:
        table = _class_table(school_sheet_url, cls)
        if not table:
            continue
        for block in table["month_blocks"]:
            for col in range(block["start"], block["end"] + 1):
                subject = table["headers_subject"][col] or f"Subject {col + 1}"
                key = f"{block['month']} | {subject}"
                for row in table["rows"]:
                    v = row[col] if col < len(row) else ""
                    num = _to_float(v)
                    if num is not None:
                        subject_bucket.setdefault(key, []).append(num)

    rows = []
    for key, nums in subject_bucket.items():
        if not nums:
            continue
        rows.append({"subject": key, "average": round(sum(nums) / len(nums), 2), "count": len(nums)})

    rows = sorted(rows, key=lambda x: x["subject"])
    return {"success": True, "subjects": rows}


def compare_gender_performance(school_sheet_url: str) -> Dict:
    return {
        "success": False,
        "message": "Gender analytics is unavailable because the class sheets do not have a gender column.",
    }


def monthly_vs_final_exam_comparison(school_sheet_url: str) -> Dict:
    classes = list_class_tabs(school_sheet_url)
    if not classes:
        return {"success": False, "message": "No class tabs found"}

    monthly_scores: List[float] = []
    final_scores: List[float] = []

    for cls in classes:
        table = _class_table(school_sheet_url, cls)
        if not table or not table["month_blocks"]:
            continue
        first_block = table["month_blocks"][0]
        last_block = table["month_blocks"][-1]
        for row in table["rows"]:
            for col in range(first_block["start"], first_block["end"] + 1):
                v = _to_float(row[col] if col < len(row) else "")
                if v is not None:
                    monthly_scores.append(v)
            for col in range(last_block["start"], last_block["end"] + 1):
                v = _to_float(row[col] if col < len(row) else "")
                if v is not None:
                    final_scores.append(v)

    if not monthly_scores and not final_scores:
        return {"success": False, "message": "No comparable monthly/final numeric data found"}

    monthly_avg = (sum(monthly_scores) / len(monthly_scores)) if monthly_scores else 0.0
    final_avg = (sum(final_scores) / len(final_scores)) if final_scores else 0.0
    return {
        "success": True,
        "monthly_average": round(monthly_avg, 2),
        "final_average": round(final_avg, 2),
        "delta_final_minus_monthly": round(final_avg - monthly_avg, 2),
    }
