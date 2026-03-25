from typing import Dict, List, Optional

from google_sheets_controller import (
    create_class_tab,
    get_school_sheet_id,
    get_user,
    make_user,
    update_user_schools,
)


def _parse_assigned_schools(csv_value: str) -> List[str]:
    if not csv_value:
        return []
    return sorted({s.strip() for s in csv_value.split(",") if s.strip()})


def create_principal(username: str, password: str, schools: List[str]) -> bool:
    username = username.strip()
    if not username or not password:
        print("create_principal failed: username and password are required")
        return False

    schools_csv = ",".join(sorted({s.strip() for s in schools if s and s.strip()}))

    created = make_user(username=username, password=password, role="principal", schools_assigned=schools_csv)
    if created:
        print(f"Principal '{username}' created with schools={schools_csv}")
    return created


def assign_school_to_principal(principal_username: str, school_name: str) -> bool:
    principal_username = principal_username.strip()
    if not principal_username:
        print("assign_school_to_principal failed: principal_username required")
        return False

    school_name = school_name.strip()
    if not school_name:
        print("assign_school_to_principal failed: school_name required")
        return False

    principal = get_user(principal_username)
    if not principal or principal.get("role") != "principal":
        print(f"assign_school_to_principal failed: '{principal_username}' is not a principal")
        return False

    current = _parse_assigned_schools(principal.get("schools_assigned", ""))
    updated = sorted(set(current + [school_name]))
    ok = update_user_schools(principal_username, updated)
    print(f"Principal '{principal_username}' assignment update={ok}, schools={updated}")
    return ok


def deassign_school_from_principal(principal_username: str, school_name: str) -> bool:
    principal_username = principal_username.strip()
    if not principal_username:
        print("deassign_school_from_principal failed: principal_username required")
        return False

    school_name = school_name.strip()
    if not school_name:
        print("deassign_school_from_principal failed: school_name required")
        return False

    principal = get_user(principal_username)
    if not principal or principal.get("role") != "principal":
        print(f"deassign_school_from_principal failed: '{principal_username}' is not a principal")
        return False

    current = _parse_assigned_schools(principal.get("schools_assigned", ""))
    if school_name not in current:
        return True

    updated = sorted([s for s in current if s != school_name])
    ok = update_user_schools(principal_username, updated)
    print(f"Principal '{principal_username}' deassignment update={ok}, schools={updated}")
    return ok


def view_principal_assignments() -> Dict[str, List[str]]:
    from google_sheets_controller import get_accounts

    assignments: Dict[str, List[str]] = {}
    for account in get_accounts():
        if account.get("role") == "principal":
            assignments[account["username"]] = _parse_assigned_schools(account.get("schools_assigned", ""))
    return assignments


def create_class(
    principal_username: str,
    school_name: str,
    class_name: str,
    session_name: Optional[str] = None,
) -> bool:
    principal_username = principal_username.strip()
    school_name = school_name.strip()
    if not principal_username or not school_name:
        print("create_class failed: principal_username and school_name are required")
        return False

    principal = get_user(principal_username)
    if not principal or principal.get("role") != "principal":
        print(f"create_class failed: '{principal_username}' is not a principal")
        return False

    assigned_schools = _parse_assigned_schools(principal.get("schools_assigned", ""))
    if school_name not in assigned_schools:
        print(f"create_class denied: principal '{principal_username}' not assigned to '{school_name}'")
        return False

    tab_name = class_name.strip().replace(" ", "")
    if not tab_name:
        print("create_class failed: class_name is empty")
        return False

    school_sheet_id = get_school_sheet_id(school_name=school_name, session_name=session_name)
    if not school_sheet_id:
        print(f"create_class failed: no active sheet mapping found for school '{school_name}'")
        return False

    ok = create_class_tab(school_sheet_id=school_sheet_id, class_name=tab_name)
    print(f"create_class result={ok} for {school_name} / {tab_name}")
    return ok


if __name__ == "__main__":
    print(view_principal_assignments())
