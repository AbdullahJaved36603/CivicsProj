from typing import Dict, List

from google_sheets_controller import (
    create_school_record,
    create_school_sheet_record,
    create_sheet,
    deactivate_school_record,
    deactivate_school_sheet_records,
    list_school_records,
    list_school_sheet_records,
    list_session_records,
    resolve_sheet_editor_email,
)


def _session_name_from_folder_id(session_folder_id: str) -> str:
    for session in list_session_records(active_only=True):
        if session.get("folder_id") == session_folder_id:
            return session["session_name"]
    return ""


def create_school(school_name: str, session_folder_id: str, editor_email: str) -> str:
    school_name = school_name.strip()
    if not school_name:
        print("create_school failed: school_name is required")
        return ""

    if not session_folder_id:
        print("create_school failed: session_folder_id is required")
        return ""

    resolved_editor = resolve_sheet_editor_email(editor_email)
    create_school_record(school_name, resolved_editor)

    sheet_url = create_sheet(school_name, session_folder_id, resolved_editor)
    if not sheet_url:
        print(f"Failed creating school sheet for '{school_name}'")
        return ""

    session_name = _session_name_from_folder_id(session_folder_id)
    if not session_name:
        session_name = "unknown"

    create_school_sheet_record(
        session_name=session_name,
        school_name=school_name,
        folder_id=session_folder_id,
        sheet_url=sheet_url,
        editor_email=resolved_editor,
    )
    print(f"School '{school_name}' created for session '{session_name}'")
    return sheet_url


def create_school_in_all_sessions(school_name: str, editor_email: str) -> Dict[str, str]:
    results: Dict[str, str] = {}
    school_name = school_name.strip()
    if not school_name:
        print("create_school_in_all_sessions failed: school_name is required")
        return results

    resolved_editor = resolve_sheet_editor_email(editor_email)
    create_school_record(school_name, resolved_editor)
    sessions = list_session_records(active_only=True)
    if not sessions:
        print("create_school_in_all_sessions failed: no active sessions found")
        return results

    for session in sessions:
        folder_id = session["folder_id"]
        session_name = session["session_name"]
        sheet_url = create_sheet(school_name, folder_id, resolved_editor)
        if sheet_url:
            create_school_sheet_record(
                session_name=session_name,
                school_name=school_name,
                folder_id=folder_id,
                sheet_url=sheet_url,
                editor_email=resolved_editor,
            )
            results[session_name] = sheet_url
    print(f"School '{school_name}' created in sessions: {list(results.keys())}")
    return results


def delete_school(school_name: str) -> bool:
    school_name = school_name.strip()
    if not school_name:
        print("delete_school failed: school_name is required")
        return False

    school_deactivated = deactivate_school_record(school_name)
    mappings_count = deactivate_school_sheet_records(school_name=school_name)
    print(f"School '{school_name}' deactivated={school_deactivated}, mappings_updated={mappings_count}")
    return school_deactivated


def list_schools(session_folder_id: str) -> List[str]:
    if not session_folder_id:
        schools = [r["school_name"] for r in list_school_records(active_only=True)]
        print(f"Schools (all active): {schools}")
        return schools

    records = [
        r for r in list_school_sheet_records(active_only=True) if r.get("folder_id") == session_folder_id
    ]
    schools = sorted({r["school_name"] for r in records})
    print(f"Schools for folder '{session_folder_id}': {schools}")
    return schools


if __name__ == "__main__":
    print("Schools:", list_schools(""))
