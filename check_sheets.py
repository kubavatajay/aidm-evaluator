"""Standalone Google Sheets connection checker.

Run this AFTER filling in .streamlit/secrets.toml to confirm your service
account can reach the spreadsheet — without launching the full app:

    python check_sheets.py

It reads the same secrets the app uses, connects, writes a test row, reads it
back, and deletes it. Every failure prints a plain-language fix.
"""

from __future__ import annotations

import os
import sys

SECRETS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml"
)


def _load_secrets() -> dict:
    if not os.path.exists(SECRETS_PATH):
        sys.exit(
            f"✗ No secrets file at {SECRETS_PATH}\n"
            "  Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml "
            "and fill it in."
        )
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # pip install tomli on older Pythons
    with open(SECRETS_PATH, "rb") as fh:
        return tomllib.load(fh)


def main() -> None:
    secrets = _load_secrets()

    if "gcp_service_account" not in secrets:
        sys.exit("✗ Missing [gcp_service_account] section in secrets.toml.")
    if "spreadsheet_key" not in secrets:
        sys.exit("✗ Missing spreadsheet_key in secrets.toml.")

    sa = dict(secrets["gcp_service_account"])
    key = secrets["spreadsheet_key"]
    email = sa.get("client_email", "(unknown)")

    print(f"• Service account: {email}")
    print(f"• Spreadsheet key: {key}")

    if "\\n" in sa.get("private_key", "") and "\n" not in sa.get("private_key", ""):
        print("⚠ private_key looks like it has literal backslash-n. In TOML double "
              "quotes, \\n becomes a real newline automatically — this is usually "
              "fine, continuing.")

    try:
        from storage import SheetsBackend, new_record
    except Exception as exc:
        sys.exit(f"✗ Could not import storage.py: {exc}")

    try:
        backend = SheetsBackend(sa, key)
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "PERMISSION_DENIED" in msg or "permission" in msg.lower():
            hint = (f"\n  → Share the sheet (Editor) with: {email}")
        elif "not been used" in msg or "disabled" in msg.lower() or "SERVICE_DISABLED" in msg:
            hint = "\n  → Enable the Google Sheets API AND Google Drive API on the project."
        elif "Requested entity was not found" in msg or "404" in msg:
            hint = "\n  → Check spreadsheet_key — it's the long ID in the sheet's URL."
        sys.exit(f"✗ Connection failed: {msg}{hint}")

    print("✓ Connected and header row ensured.")

    # Write/read/delete a harmless test row.
    rec = new_record(mentor="__connection_test__", resident="__test__",
                     skill="__test__", final_rating="C", note="checker")
    try:
        backend.add_evaluation(rec)
        rows = backend.list_evaluations()
        found = any(r.get("id") == rec["id"] for r in rows)
        backend.delete_evaluation(rec["id"])
    except Exception as exc:
        sys.exit(f"✗ Read/write test failed: {exc}")

    if found:
        print("✓ Wrote, read back, and cleaned up a test row.")
        print("\n🎉 Google Sheets is configured correctly. Launch with: streamlit run app.py")
    else:
        sys.exit("✗ Wrote a row but couldn't read it back — check the worksheet.")


if __name__ == "__main__":
    main()
