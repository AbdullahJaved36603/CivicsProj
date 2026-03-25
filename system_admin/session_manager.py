from typing import List

from google_sheets_controller import (
    create_folder,
    create_school_sheet_record,
    create_sheet,
    create_session_record,
    deactivate_school_sheet_records,
    deactivate_session_record,
    delete_folder,
    get_session_folder_id,
    list_school_records,
    list_session_records,
    normalize_session_name,
    resolve_sheet_editor_email,
    session_folder_name,
)


def create_session(
    session_name: str,
    initialize_existing_schools: bool = True,
    default_editor_email: str = "",
) -> str:
    clean_session = normalize_session_name(session_name)
    if not clean_session:
        print("create_session failed: session_name is required")
        return ""

    if get_session_folder_id(clean_session):
        print(f"Session '{clean_session}' already exists")
        return ""

    folder_name = session_folder_name(clean_session)
    folder_id = create_folder(folder_name)
    if not folder_id:
        print(f"Failed to create session folder for '{clean_session}'")
        return ""

    create_session_record(clean_session, folder_id)

    if initialize_existing_schools:
        schools = list_school_records(active_only=True)
        for school in schools:
            school_name = school["school_name"]
            editor = resolve_sheet_editor_email(school.get("default_editor_email") or default_editor_email)
            sheet_url = create_sheet(school_name, folder_id, editor)
            if sheet_url:
                create_school_sheet_record(
                    session_name=clean_session,
                    school_name=school_name,
                    folder_id=folder_id,
                    sheet_url=sheet_url,
                    editor_email=editor,
                )

    print(f"Session '{clean_session}' created with folder_id={folder_id}")
    return folder_id


def delete_session(session_name: str) -> bool:
    clean_session = normalize_session_name(session_name)
    if not clean_session:
        print("delete_session failed: session_name is required")
        return False

    folder_id = get_session_folder_id(clean_session)
    if not folder_id:
        print(f"Session '{clean_session}' not found")
        return False

    deleted_in_drive = delete_folder(folder_id)
    if not deleted_in_drive:
        print("Drive folder delete did not succeed or operation unsupported; deactivating metadata only")

    session_updated = deactivate_session_record(clean_session)
    deactivate_school_sheet_records(session_name=clean_session)

    ok = session_updated
    print(f"Session '{clean_session}' deletion result={ok}")
    return ok


def list_sessions() -> List[str]:
    sessions = [r["session_name"] for r in list_session_records(active_only=True)]
    return sessions


if __name__ == "__main__":
    print("Sessions:", list_sessions())
