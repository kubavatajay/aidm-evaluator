"""Persistence layer for the AIDM Bootcamp Evaluator.

Two interchangeable backends implement the same small interface:

    add_evaluation(record)        -> str (id)
    list_evaluations()            -> list[dict]   (newest first)
    delete_evaluation(record_id)  -> None

- LocalBackend   : a JSON file under ./data. Zero setup; runs out of the box.
- SheetsBackend  : a Google Sheet via a service account. Free, durable, shareable.

The app calls get_backend(), which auto-selects Sheets when credentials are
present in st.secrets and otherwise falls back to local storage. Photos are
stored as compressed base64 *inside* each record, so a single Google Sheet (or
single JSON file) is the only thing that needs to persist — no second service.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import uuid
from datetime import datetime, timezone

# Columns, in order, used for the Google Sheet header row and CSV-ish framing.
FIELDS = [
    "id",
    "timestamp",
    "mentor",
    "resident",
    "skill",
    "date",
    "ai_rating",
    "ai_rationale",
    "final_rating",
    "mentor_comment",
    "note",
    "photo",  # base64-encoded JPEG, or "" if none
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LOCAL_FILE = os.path.join(DATA_DIR, "evaluations.json")


# ---------------------------------------------------------------------------
# Image handling — keep photos small enough to live in one spreadsheet cell.
# ---------------------------------------------------------------------------
# Google Sheets caps a single cell at 50,000 characters. We compress until the
# base64 payload comfortably fits, degrading dimensions/quality as needed.
_CELL_LIMIT = 45000


def compress_image_to_b64(raw_bytes: bytes) -> str:
    """Compress an uploaded image to a base64 JPEG that fits in a sheet cell.

    Returns "" if Pillow can't read the bytes.
    """
    try:
        from PIL import Image, ImageOps
    except Exception:
        # Pillow missing — store nothing rather than a giant raw blob.
        return ""

    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img)  # respect phone orientation
        img = img.convert("RGB")
    except Exception:
        return ""

    for max_dim, quality in [(900, 70), (720, 60), (560, 50), (420, 45), (320, 40)]:
        candidate = img.copy()
        candidate.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        candidate.save(buf, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        if len(b64) <= _CELL_LIMIT:
            return b64

    # Last resort: smallest setting even if slightly over (rare).
    return b64


def b64_to_bytes(b64: str) -> bytes | None:
    """Decode a stored base64 photo back to raw JPEG bytes."""
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def new_record(**kwargs) -> dict:
    """Build a fully-populated record dict with sane defaults."""
    rec = {field: "" for field in FIELDS}
    rec["id"] = uuid.uuid4().hex
    rec["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec.update({k: v for k, v in kwargs.items() if k in FIELDS})
    return rec


# ---------------------------------------------------------------------------
# Local JSON backend
# ---------------------------------------------------------------------------
class LocalBackend:
    name = "Local file"

    def __init__(self, path: str = LOCAL_FILE):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write([])

    def _read(self) -> list[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, rows: list[dict]) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def add_evaluation(self, record: dict) -> str:
        with self._lock:
            rows = self._read()
            rows.append(record)
            self._write(rows)
        return record["id"]

    def list_evaluations(self) -> list[dict]:
        rows = self._read()
        rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return rows

    def delete_evaluation(self, record_id: str) -> None:
        with self._lock:
            rows = [r for r in self._read() if r.get("id") != record_id]
            self._write(rows)


# ---------------------------------------------------------------------------
# Google Sheets backend
# ---------------------------------------------------------------------------
class SheetsBackend:
    name = "Google Sheets"

    def __init__(self, service_account_info: dict, spreadsheet_key: str,
                 worksheet_name: str = "evaluations"):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            service_account_info, scopes=scopes
        )
        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(spreadsheet_key)
        try:
            self._ws = self._sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self._ws = self._sh.add_worksheet(
                title=worksheet_name, rows=1000, cols=len(FIELDS)
            )
        self._ensure_header()

    def _ensure_header(self) -> None:
        header = self._ws.row_values(1)
        if header != FIELDS:
            self._ws.update(
                range_name="A1", values=[FIELDS], value_input_option="RAW"
            )

    def add_evaluation(self, record: dict) -> str:
        row = [str(record.get(field, "")) for field in FIELDS]
        self._ws.append_row(row, value_input_option="RAW")
        return record["id"]

    def list_evaluations(self) -> list[dict]:
        records = self._ws.get_all_records(expected_headers=FIELDS)
        rows = [{field: str(r.get(field, "")) for field in FIELDS} for r in records]
        rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return rows

    def delete_evaluation(self, record_id: str) -> None:
        # get_all_values includes the header at index 0, so data starts at row 2.
        all_values = self._ws.get_all_values()
        id_col = FIELDS.index("id")
        for offset, values in enumerate(all_values[1:], start=2):
            if len(values) > id_col and values[id_col] == record_id:
                self._ws.delete_rows(offset)
                return


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------
def get_backend():
    """Return (backend, info_message).

    Selects Google Sheets when a service account + spreadsheet key are present
    in st.secrets; otherwise falls back to the local JSON store.
    """
    try:
        import streamlit as st
        secrets = st.secrets
    except Exception:
        secrets = {}

    sa = None
    key = None
    if "gcp_service_account" in secrets and "spreadsheet_key" in secrets:
        sa = dict(secrets["gcp_service_account"])
        key = secrets["spreadsheet_key"]

    if sa and key:
        try:
            backend = SheetsBackend(sa, key)
            return backend, "Connected to Google Sheets."
        except Exception as exc:  # fall back rather than crash the app
            return (
                LocalBackend(),
                f"Google Sheets unavailable ({exc}). Using local storage.",
            )

    return LocalBackend(), "Using local storage (no Google Sheets configured)."
