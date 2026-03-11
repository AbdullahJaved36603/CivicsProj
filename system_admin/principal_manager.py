"""Principal and super-user account management module."""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

import pandas as pd

from system_admin.google_sheets_controller import GoogleSheetsController, ValidationError


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class PrincipalManager:
    """Creates users, authenticates users, and handles principal-school assignments."""

    def __init__(self, controller: GoogleSheetsController) -> None:
        self.controller = controller
        self.controller.create_worksheet(
            "Users",
            ["user_id", "username", "password_hash", "role", "school_id", "is_active"],
        )

    def create_default_super_user(
        self,
        *,
        user_id: str = "SU-001",
        username: str = "super_admin",
        password: str = "admin123",
    ) -> Dict[str, str]:
        users = self.controller.read_sheet_or_empty("Users")
        if not users.empty and username in set(users.get("username", pd.Series(dtype=str)).astype(str).tolist()):
            return {"username": username, "status": "already_exists"}

        self.controller.append_data(
            "Users",
            {
                "user_id": user_id,
                "username": username,
                "password_hash": _hash_password(password),
                "role": "super_user",
                "school_id": "ALL",
                "is_active": "yes",
            },
        )
        return {"username": username, "status": "created"}

    def create_principal_account(
        self,
        principal_id: str,
        username: str,
        password: str,
        school_id: str,
    ) -> Dict[str, str]:
        self.controller.ensure_unique_value("Users", "user_id", principal_id)
        self.controller.ensure_unique_value("Users", "username", username)

        schools = self.controller.read_sheet_or_empty("Schools")
        if schools.empty or school_id not in set(schools["school_id"].astype(str).tolist()):
            raise ValidationError(f"School '{school_id}' does not exist.")

        self.controller.append_data(
            "Users",
            {
                "user_id": principal_id,
                "username": username,
                "password_hash": _hash_password(password),
                "role": "principal",
                "school_id": school_id,
                "is_active": "yes",
            },
        )
        return {"principal_id": principal_id, "username": username, "school_id": school_id}

    def assign_principal_to_school(self, username: str, school_id: str) -> int:
        changed = self.controller.update_rows(
            "Users",
            where_column="username",
            where_value=username,
            updates={"school_id": school_id},
        )
        self.controller.update_rows(
            "Schools",
            where_column="school_id",
            where_value=school_id,
            updates={"principal_username": username},
        )
        return changed

    def authenticate(self, username: str, password: str, role: Optional[str] = None) -> Optional[Dict[str, str]]:
        users = self.controller.read_sheet_or_empty("Users")
        if users.empty:
            return None

        user = users.loc[users["username"].astype(str).str.strip() == username.strip()]
        if user.empty:
            return None

        row = user.iloc[0]
        if str(row.get("is_active", "")).strip().lower() != "yes":
            return None

        if str(row.get("password_hash", "")).strip() != _hash_password(password):
            return None

        if role and str(row.get("role", "")).strip() != role:
            return None

        return {
            "user_id": str(row.get("user_id", "")),
            "username": str(row.get("username", "")),
            "role": str(row.get("role", "")),
            "school_id": str(row.get("school_id", "")),
        }

    def list_principals(self) -> pd.DataFrame:
        users = self.controller.read_sheet_or_empty("Users")
        if users.empty:
            return users
        return users.loc[users["role"].astype(str) == "principal"].reset_index(drop=True)

    def principal_capabilities_summary(self, username: str) -> Dict[str, str]:
        users = self.controller.read_sheet_or_empty("Users")
        principal = users.loc[users["username"].astype(str) == username]
        if principal.empty:
            raise ValidationError(f"Principal '{username}' not found.")

        school_id = str(principal.iloc[0].get("school_id", "")).strip()
        schools = self.controller.read_sheet_or_empty("Schools")
        school_match = schools.loc[schools["school_id"].astype(str) == school_id]
        pks_code = str(school_match.iloc[0].get("pks_code", "")).strip() if not school_match.empty else ""

        return {
            "school_id": school_id,
            "pks_code": pks_code,
            "permissions": "manage_teachers,assign_teachers_to_classes,view_school_analytics,monitor_class_performance,export_reports",
        }
