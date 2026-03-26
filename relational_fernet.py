from __future__ import annotations

import importlib

try:
    from system_admin.config import RELATIONAL_PASSWORD_KEY
except Exception as exc:  # pragma: no cover - depends on runtime path
    raise RuntimeError("Unable to load RELATIONAL_PASSWORD_KEY from system_admin.config") from exc


try:
    fernet_module = importlib.import_module("cryptography.fernet")
    Fernet = getattr(fernet_module, "Fernet")
except Exception as exc:  # pragma: no cover - dependency availability differs by env
    raise RuntimeError(
        "cryptography is required for relational_fernet. Install with: pip install cryptography"
    ) from exc


relational_fernet = Fernet(RELATIONAL_PASSWORD_KEY)
