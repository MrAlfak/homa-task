"""Google Sheets integration — matches Team Management Homa layout."""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

import gspread
import jdatetime
from google.oauth2.service_account import Credentials

from config import config
from services.sheets_models import (
    CONTENT_DESIGN_NAMES,
    CONTENT_HEADERS,
    CONTENT_PROJECT_HEADER_ALIASES,
    CONTENT_SHEET_ALIASES,
    CONTENT_SHEET_NAME,
    EDITING_SHEET_ALIASES,
    EDITING_SHEET_NAME,
    FILMING_HEADERS,
    FILMING_PROJECT_HEADER_ALIASES,
    FILMING_SHEET_ALIASES,
    FILMING_SHEET_NAME,
    DROPDOWN_RTL_HEADERS,
    GENERAL_PROJECT_CATEGORIES,
    IDEAS_HEADERS,
    IDEAS_SHEET_NAME,
    PERSONAL_HEADERS,
    PERSONNEL_BOOL_HEADER_ALIASES,
    PERSONNEL_CACHE_TTL_SEC,
    PERSONNEL_EXTRA_COLUMNS,
    PERSONNEL_MOBILE_HEADER_ALIASES,
    PRIORITIES,
    PROJECTS_CACHE_TTL_SEC,
    PROJECTS_HEADER_ALIASES,
    PROJECTS_SHEET_HEADER,
    SCOPES,
    SMS_LOG_HEADERS,
    SMS_LOG_SHEET_NAME,
    SMS_SETTINGS_CACHE_TTL_SEC,
    SMS_SETTINGS_DEFAULT_ROWS,
    SMS_SETTINGS_HEADERS,
    SMS_SHEET_NAME,
    STATUS_HEADER,
    STATUS_SHEET_VALUES,
    SYSTEM_TAB_ORDER,
    TASKS_HEADERS,
    TEMPLATE_HEADERS,
    TEMPLATE_RECURRENCE_VALUES,
    TEMPLATE_SHEET_ALIASES,
    TEMPLATE_SHEET_NAME,
    TEMPLATE_TEST_ROW,
    TEMPLATE_TEST_TITLE,
    WORKSHEET_CACHE_TTL_SEC,
    ContentEntry,
    FilmingEntry,
    Idea,
    Personnel,
    SmsSettings,
    Task,
    TemplateEntry,
    coalesce_personnel,
    date_for_sheet,
    is_blank_task_cell,
    is_general_project,
    is_personnel_bool_header,
    normalize_sheet_title,
    normalize_status,
    overlay_status_from_personal,
    paginate,
    parse_bool,
    parse_due_as_jalali,
    parse_task_id,
    personnel_from_record,
    projects_data_start,
    recent_shamsi_dates,
    record_is_active,
    record_telegram_id,
    resolve_shamsi_date_offset,
    role_label,
    row_to_dict,
    shamsi_date_button_label,
    shamsi_date_range,
    shamsi_today,
    sms_settings_from_records,
    sort_projects,
    status_to_sheet,
    task_match_key,
    template_from_record,
    validate_shamsi_date,
)

logger = logging.getLogger(__name__)


def _col_to_a1(index: int) -> str:
    """1-based column index → A1 letter (1=A, 27=AA)."""
    if index <= 0:
        return "A"
    letters: list[str] = []
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))

# Re-export public names so existing `from services.sheets import …` keep working.
__all__ = [
    "CONTENT_DESIGN_NAMES",
    "CONTENT_SHEET_NAME",
    "FILMING_SHEET_NAME",
    "GENERAL_PROJECT_CATEGORIES",
    "PERSONAL_HEADERS",
    "PRIORITIES",
    "TASKS_HEADERS",
    "ContentEntry",
    "FilmingEntry",
    "Idea",
    "Personnel",
    "SheetsService",
    "Task",
    "get_sheets_service",
    "paginate",
]


class SheetsService:
    """Read/write operations against the configured Google Spreadsheet."""

    def __init__(self) -> None:
        credentials = Credentials.from_service_account_file(
            str(config.google_credentials_path),
            scopes=SCOPES,
        )
        client = gspread.authorize(credentials)
        self._spreadsheet = client.open_by_key(config.google_sheet_id)
        self._worksheet_cache: tuple[float, dict[str, gspread.Worksheet]] | None = None
        self._personnel_records_cache: tuple[float, list[dict[str, str]]] | None = None
        self._projects_cache: tuple[float, list[str]] | None = None
        self._sms_settings_cache: tuple[float, SmsSettings] | None = None
        self._filter_formula_cache: dict[int, bool] = {}
        self._overdue_red_rows: dict[tuple[int, int], int] = {}
        self._personal_tasks_cache: tuple[float, list[Task]] | None = None

        worksheets = self._all_worksheets(force_refresh=True)
        self.ensure_english_sheet_titles()
        worksheets = self._all_worksheets(force_refresh=True)
        try:
            self._personnel_ws = worksheets["Personnel"]
            self._tasks_ws = worksheets["Tasks"]
            self._projects_ws = worksheets["Projects"]
        except KeyError as exc:
            raise RuntimeError(
                f"Required worksheet tab {exc} not found in the spreadsheet."
            ) from exc

        self.ensure_personnel_schema()
        self.ensure_projects_schema()
        self.ensure_tasks_status_column()
        self.ensure_all_status_and_priority_dropdowns()
        self.ensure_sheet_vazirmatn_font()
        self.ensure_dropdown_right_align()
        self.ensure_filming_schema()
        self.ensure_content_schema()
        self.ensure_sms_schema()
        self.ensure_template_schema()

    def _get_or_rename_worksheet(
        self,
        preferred_title: str,
        aliases: tuple[str, ...],
    ) -> gspread.Worksheet | None:
        """Return preferred tab; rename a legacy Persian title to English if needed."""
        worksheets = self._all_worksheets()
        if preferred_title in worksheets:
            return worksheets[preferred_title]
        wanted = {normalize_sheet_title(preferred_title)}
        wanted.update(normalize_sheet_title(alias) for alias in aliases)
        for title, worksheet in worksheets.items():
            if normalize_sheet_title(title) not in wanted:
                continue
            if title == preferred_title:
                return worksheet
            try:
                worksheet.update_title(preferred_title)
                logger.info("Renamed worksheet %r -> %r", title, preferred_title)
            except Exception:
                logger.exception("Failed renaming worksheet %r -> %r", title, preferred_title)
                return worksheet
            self.invalidate_worksheet_cache()
            return worksheet
        return None

    def ensure_english_sheet_titles(self) -> None:
        """Keep system tabs in English and a stable left-to-right order."""
        pairs = (
            (TEMPLATE_SHEET_NAME, TEMPLATE_SHEET_ALIASES),
            (FILMING_SHEET_NAME, FILMING_SHEET_ALIASES),
            (CONTENT_SHEET_NAME, CONTENT_SHEET_ALIASES),
            (EDITING_SHEET_NAME, EDITING_SHEET_ALIASES),
            (IDEAS_SHEET_NAME, ("Ideas", "ایده", "ایده ها")),
            (SMS_SHEET_NAME, ("SMS", "پیامک")),
            (SMS_LOG_SHEET_NAME, ("SMS_Log", "SMS Log", "لاگ پیامک")),
        )
        for preferred, aliases in pairs:
            self._get_or_rename_worksheet(preferred, aliases)

        worksheets = self._all_worksheets(force_refresh=True)
        ordered: list[gspread.Worksheet] = []
        used: set[int] = set()
        for title in SYSTEM_TAB_ORDER:
            worksheet = worksheets.get(title)
            if worksheet is None or worksheet.id in used:
                continue
            ordered.append(worksheet)
            used.add(worksheet.id)
        for worksheet in self._spreadsheet.worksheets():
            if worksheet.id not in used:
                ordered.append(worksheet)
                used.add(worksheet.id)
        current = [ws.id for ws in self._spreadsheet.worksheets()]
        desired = [ws.id for ws in ordered]
        if current == desired:
            return
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": worksheet.id, "index": index},
                    "fields": "index",
                }
            }
            for index, worksheet in enumerate(ordered)
        ]
        try:
            self._spreadsheet.batch_update({"requests": requests})
            self.invalidate_worksheet_cache()
            logger.info("Sheet tab order unified (%d tabs)", len(ordered))
        except Exception:
            logger.exception("Failed reordering worksheets")

    def _all_worksheets(self, *, force_refresh: bool = False) -> dict[str, gspread.Worksheet]:
        """Title -> Worksheet map, cached briefly to avoid repeated metadata fetches.

        ``Spreadsheet.worksheet(title)`` re-downloads the *entire* spreadsheet
        metadata on every call in gspread, so looking up personal sheets or the
        Ideas tab on every user action multiplies Sheets API traffic. A single
        cached fetch shared across lookups keeps us well inside the API quota.
        """
        now = time.monotonic()
        if not force_refresh and self._worksheet_cache is not None:
            cached_at, mapping = self._worksheet_cache
            if now - cached_at < WORKSHEET_CACHE_TTL_SEC:
                return mapping
        mapping = {ws.title: ws for ws in self._spreadsheet.worksheets()}
        self._worksheet_cache = (now, mapping)
        return mapping

    def invalidate_worksheet_cache(self) -> None:
        """Drop cached worksheet list (e.g. after creating a new tab)."""
        self._worksheet_cache = None
        self._filter_formula_cache.clear()

    def invalidate_personnel_cache(self) -> None:
        """Drop cached Personnel rows (e.g. after admin edits the sheet)."""
        self._personnel_records_cache = None

    def invalidate_projects_cache(self) -> None:
        """Drop cached Projects list (e.g. after adding a new category)."""
        self._projects_cache = None

    def _get_personnel_records(self) -> list[dict[str, str]]:
        """Cached Personnel rows to avoid full-sheet reads on every message."""
        now = time.monotonic()
        if self._personnel_records_cache is not None:
            cached_at, records = self._personnel_records_cache
            if now - cached_at < PERSONNEL_CACHE_TTL_SEC:
                return records
        records = self._personnel_ws.get_all_records()
        self._personnel_records_cache = (now, records)
        return records

    @staticmethod
    def _header_exists(headers: list[str], english: str, persian: str) -> bool:
        normalized = {h.strip().lower() for h in headers if h.strip()}
        return (
            english.lower() in normalized
            or persian in headers
            or english in headers
        )

    def ensure_personnel_schema(self) -> list[str]:
        """Add missing Personnel columns and TRUE/FALSE dropdowns on bool fields."""
        ws = self._personnel_ws
        headers = [h for h in ws.row_values(1)]
        added: list[str] = []

        missing = [
            (key, persian_header)
            for key, persian_header in PERSONNEL_EXTRA_COLUMNS
            if not self._header_exists(headers, key, persian_header)
        ]
        if missing:
            required_cols = len(headers) + len(missing)
            if ws.col_count < required_cols:
                ws.add_cols(required_cols - ws.col_count)

            for key, persian_header in missing:
                col_index = len(headers) + 1
                ws.update_cell(1, col_index, persian_header)
                headers.append(persian_header)
                added.append(persian_header)

                if not is_personnel_bool_header(key, persian_header):
                    continue
                row_count = max(len(ws.col_values(1)), 1)
                if row_count > 1:
                    default_flag = "TRUE" if key == "telegram_notify" else "FALSE"
                    defaults = [[default_flag]] * (row_count - 1)
                    start = gspread.utils.rowcol_to_a1(2, col_index)
                    end = gspread.utils.rowcol_to_a1(row_count, col_index)
                    ws.update(
                        f"{start}:{end}",
                        defaults,
                        value_input_option="USER_ENTERED",
                    )

            if added:
                logger.info("Personnel sheet: added columns %s", added)

        if added or self._force_sheet_schema():
            self.ensure_personnel_bool_dropdowns()
        self.ensure_personnel_mobile_column()
        return added

    @staticmethod
    def _force_sheet_schema() -> bool:
        return os.getenv("FORCE_SHEET_SCHEMA", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def ensure_tasks_status_column(self) -> None:
        """Append وضعیت on Tasks and put a dropdown on the whole column."""
        worksheet = self._tasks_ws
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        if STATUS_HEADER not in headers:
            col_index = len(headers) + 1
            if worksheet.col_count < col_index:
                worksheet.add_cols(col_index - worksheet.col_count)
            worksheet.update_cell(1, col_index, STATUS_HEADER)
            logger.info("Tasks sheet: added %s column", STATUS_HEADER)
            headers = [str(h).strip() for h in worksheet.row_values(1)]
        self._apply_tasks_status_dropdown(headers)

    def _apply_tasks_status_dropdown(self, headers: list[str] | None = None) -> None:
        worksheet = self._tasks_ws
        if headers is None:
            headers = [str(h).strip() for h in worksheet.row_values(1)]
        try:
            col_index = headers.index(STATUS_HEADER)
        except ValueError:
            return
        end_row = max(int(worksheet.row_count or 0), 2000)
        try:
            self._spreadsheet.batch_update(
                {
                    "requests": [
                        {
                            "setDataValidation": {
                                "range": {
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 1,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": col_index,
                                    "endColumnIndex": col_index + 1,
                                },
                                "rule": {
                                    "condition": {
                                        "type": "ONE_OF_LIST",
                                        "values": [
                                            {"userEnteredValue": item}
                                            for item in STATUS_SHEET_VALUES
                                        ],
                                    },
                                    "showCustomUi": True,
                                    "strict": False,
                                    "inputMessage": "وضعیت را از لیست انتخاب کنید",
                                },
                            }
                        }
                    ]
                }
            )
            logger.info("Tasks sheet: status dropdown on column %s through row %s", col_index + 1, end_row)
        except Exception:
            logger.exception("Failed applying Tasks status dropdown")

    def ensure_all_status_and_priority_dropdowns(self) -> None:
        """Apply unified dropdown data validation for اولویت and وضعیت across all sheets."""
        requests: list[dict] = []
        for worksheet in self._all_worksheets().values():
            headers = [str(header).strip() for header in worksheet.row_values(1)]
            if not headers:
                continue
            end_row = max(int(worksheet.row_count or 0), 2000)
            sheet_id = int(worksheet.id)
            for col_index, header in enumerate(headers):
                if header == "اولویت":
                    requests.append(
                        {
                            "setDataValidation": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": col_index,
                                    "endColumnIndex": col_index + 1,
                                },
                                "rule": {
                                    "condition": {
                                        "type": "ONE_OF_LIST",
                                        "values": [
                                            {"userEnteredValue": item}
                                            for item in PRIORITIES
                                        ],
                                    },
                                    "showCustomUi": True,
                                    "strict": False,
                                    "inputMessage": "اولویت را انتخاب کنید",
                                },
                            }
                        }
                    )
                elif header == "وضعیت":
                    requests.append(
                        {
                            "setDataValidation": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": col_index,
                                    "endColumnIndex": col_index + 1,
                                },
                                "rule": {
                                    "condition": {
                                        "type": "ONE_OF_LIST",
                                        "values": [
                                            {"userEnteredValue": item}
                                            for item in STATUS_SHEET_VALUES
                                        ],
                                    },
                                    "showCustomUi": True,
                                    "strict": False,
                                    "inputMessage": "وضعیت را از لیست انتخاب کنید",
                                },
                            }
                        }
                    )
        if not requests:
            return
        chunk_size = 20
        for start in range(0, len(requests), chunk_size):
            try:
                self._spreadsheet.batch_update({"requests": requests[start : start + chunk_size]})
            except Exception:
                logger.exception("Failed applying unified status/priority dropdowns batch")
        logger.info("Unified dropdowns applied to %d columns across sheets", len(requests))

    def ensure_sheet_vazirmatn_font(self) -> None:
        """Set Vazirmatn on the whole workbook, including numbers and dates."""
        requests: list[dict] = [
            {
                "updateSpreadsheetProperties": {
                    "properties": {
                        "defaultFormat": {
                            "textFormat": {"fontFamily": "Vazirmatn"},
                        }
                    },
                    "fields": "defaultFormat.textFormat.fontFamily",
                }
            }
        ]
        for worksheet in self._all_worksheets().values():
            requests.append(
                {
                    "repeatCell": {
                        "range": {"sheetId": int(worksheet.id)},
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"fontFamily": "Vazirmatn"},
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.fontFamily",
                    }
                }
            )
        try:
            chunk_size = 12
            for start in range(0, len(requests), chunk_size):
                self._spreadsheet.batch_update({"requests": requests[start : start + chunk_size]})
            logger.info("Applied Vazirmatn to %d worksheet(s)", len(self._all_worksheets()))
        except Exception:
            logger.exception("Failed applying Vazirmatn across the spreadsheet")

    def _dropdown_right_align_request(
        self,
        *,
        sheet_id: int,
        col_index: int,
        end_row: int,
        start_row: int = 0,
    ) -> dict:
        return {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "RIGHT",
                        "textDirection": "RIGHT_TO_LEFT",
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.textDirection",
            }
        }

    def ensure_dropdown_right_align(self) -> None:
        """Right-align Persian dropdown columns without flipping the whole sheet."""
        requests: list[dict] = []
        for worksheet in self._all_worksheets().values():
            headers = [str(header).strip() for header in worksheet.row_values(1)]
            if not headers:
                continue
            end_row = max(int(worksheet.row_count or 0), 2000)
            sheet_id = int(worksheet.id)
            seen: set[int] = set()
            for col_index, header in enumerate(headers):
                if header not in DROPDOWN_RTL_HEADERS or col_index in seen:
                    continue
                seen.add(col_index)
                requests.append(
                    self._dropdown_right_align_request(
                        sheet_id=sheet_id,
                        col_index=col_index,
                        end_row=end_row,
                    )
                )
        if not requests:
            return
        try:
            chunk_size = 12
            for start in range(0, len(requests), chunk_size):
                self._spreadsheet.batch_update({"requests": requests[start : start + chunk_size]})
            logger.info("Right-aligned %d dropdown column(s)", len(requests))
        except Exception:
            logger.exception("Failed right-aligning dropdown columns")

    def ensure_personnel_bool_dropdowns(self) -> None:
        """Apply TRUE/FALSE list dropdowns on Personnel boolean columns."""
        worksheet = self._personnel_ws
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        if not headers:
            return

        alias_lookup = {
            alias.strip().lower(): aliases
            for aliases in PERSONNEL_BOOL_HEADER_ALIASES
            for alias in aliases
            if alias.strip()
        }
        matched_cols: list[int] = []
        seen_groups: set[tuple[str, ...]] = set()
        for index, header in enumerate(headers):
            key = header.strip().lower()
            aliases = alias_lookup.get(key)
            if aliases is None or aliases in seen_groups:
                continue
            seen_groups.add(aliases)
            matched_cols.append(index)

        if not matched_cols:
            return

        end_row = max(int(worksheet.row_count or 0), 1000)
        requests: list[dict] = []
        for col_index in matched_cols:
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": "TRUE"},
                                    {"userEnteredValue": "FALSE"},
                                ],
                            },
                            "showCustomUi": True,
                            "strict": True,
                            "inputMessage": "TRUE یا FALSE را انتخاب کنید",
                        },
                    }
                }
            )

        try:
            self._spreadsheet.batch_update({"requests": requests})
            logger.info(
                "Personnel sheet: TRUE/FALSE dropdowns on %d column(s)",
                len(matched_cols),
            )
        except Exception:
            logger.exception("Failed applying Personnel TRUE/FALSE dropdowns")

    def ensure_personnel_mobile_column(self) -> None:
        """Keep موبایل as free text so phone numbers are not blocked by TRUE/FALSE rules."""
        worksheet = self._personnel_ws
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        if not headers:
            return
        mobile_aliases = {alias.strip().lower() for alias in PERSONNEL_MOBILE_HEADER_ALIASES if alias.strip()}
        mobile_cols = [
            index
            for index, header in enumerate(headers)
            if header.strip().lower() in mobile_aliases
        ]
        if not mobile_cols:
            return

        end_row = max(int(worksheet.row_count or 0), 1000)
        requests: list[dict] = []
        for col_index in mobile_cols:
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "rule": None,
                    }
                }
            )
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {"type": "TEXT"},
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
            )
        try:
            self._spreadsheet.batch_update({"requests": requests})
        except Exception:
            logger.exception("Failed clearing Personnel mobile validation")

    _projects_data_start = staticmethod(projects_data_start)

    def ensure_projects_schema(self) -> list[str]:
        """Ensure Projects tab has a header and default cross-project categories."""
        ws = self._projects_ws
        col_values = ws.col_values(1)
        added: list[str] = []

        if not col_values:
            rows = [[PROJECTS_SHEET_HEADER], *[[name] for name in GENERAL_PROJECT_CATEGORIES]]
            end_row = len(rows)
            ws.update(
                f"A1:A{end_row}",
                rows,
                value_input_option="USER_ENTERED",
            )
            logger.info("Projects sheet: initialized with header and %s", list(GENERAL_PROJECT_CATEGORIES))
            self.invalidate_projects_cache()
            return list(GENERAL_PROJECT_CATEGORIES)

        data_start = self._projects_data_start(col_values)
        if data_start == 1:
            existing_names = {v.strip() for v in col_values[1:] if v.strip()}
            next_row = len(col_values) + 1
        else:
            existing_names = {v.strip() for v in col_values if v.strip()}
            next_row = len(col_values) + 1

        to_add = [name for name in GENERAL_PROJECT_CATEGORIES if name not in existing_names]
        for name in to_add:
            ws.update_cell(next_row, 1, name)
            next_row += 1
            added.append(name)

        if added:
            logger.info("Projects sheet: added categories %s", added)
            self.invalidate_projects_cache()
        return added

    sort_projects = staticmethod(sort_projects)
    is_general_project = staticmethod(is_general_project)
    _parse_bool = staticmethod(parse_bool)
    _record_telegram_id = staticmethod(record_telegram_id)
    _record_is_active = staticmethod(record_is_active)
    _shamsi_today = staticmethod(shamsi_today)
    shamsi_date_range = staticmethod(shamsi_date_range)
    recent_shamsi_dates = staticmethod(recent_shamsi_dates)
    shamsi_date_button_label = staticmethod(shamsi_date_button_label)
    resolve_shamsi_date_offset = staticmethod(resolve_shamsi_date_offset)
    validate_shamsi_date = staticmethod(validate_shamsi_date)
    _date_for_sheet = staticmethod(date_for_sheet)
    _normalize_status = staticmethod(normalize_status)
    _status_to_sheet = staticmethod(status_to_sheet)
    _row_to_dict = staticmethod(row_to_dict)
    _is_blank_task_cell = staticmethod(is_blank_task_cell)
    _role_label = staticmethod(role_label)
    _parse_due_as_jalali = staticmethod(parse_due_as_jalali)
    _task_match_key = staticmethod(task_match_key)

    def _row_is_writable(self, row: list[str], col_count: int) -> bool:
        """A row can be reused when it has no real task in the first column."""
        padded = row + [""] * max(0, col_count - len(row))
        return self._is_blank_task_cell(padded[0])

    def _find_writable_row(self, worksheet: gspread.Worksheet, col_count: int) -> int:
        """Return the first data row that can be overwritten (row 2+).

        Scans from the top so zombie rows (empty task title but leftover status
        dropdowns) get reused instead of always appending below intact tasks.
        Falls back to the first row after the last non-empty sheet row.

        Not used for personal employee tabs — those always append (see
        ``_find_append_row``) so FILTER/ARRAYFORMULA rows are never overwritten.
        """
        all_values = worksheet.get_all_values()
        if len(all_values) < 2:
            return 2

        for index in range(1, len(all_values)):
            if self._row_is_writable(all_values[index], col_count):
                return index + 1

        return len(all_values) + 1

    def _personal_sheet_uses_tasks_filter(self, worksheet: gspread.Worksheet) -> bool:
        """True when this personal tab mirrors Tasks via FILTER (bot must not write rows)."""
        ws_id = int(worksheet.id)
        cached = self._filter_formula_cache.get(ws_id)
        if cached is not None:
            return cached
        try:
            cell = worksheet.acell("A2", value_render_option="FORMULA")
            formula = str(cell.value or "").strip().upper()
        except Exception as exc:
            logger.debug("Could not read A2 formula on %s: %s", worksheet.title, exc)
            self._filter_formula_cache[ws_id] = False
            return False
        uses_filter = formula.startswith("=") and "FILTER" in formula and "TASKS!" in formula
        self._filter_formula_cache[ws_id] = uses_filter
        return uses_filter

    def _row2_has_formula_template(self, worksheet: gspread.Worksheet) -> bool:
        """True when A2 holds a sheet formula (FILTER / ARRAYFORMULA / QUERY)."""
        if self._personal_sheet_uses_tasks_filter(worksheet):
            return True
        try:
            cell = worksheet.acell("A2", value_render_option="FORMULA")
            value = str(cell.value or "").strip()
        except Exception as exc:
            logger.debug("Could not read A2 formula: %s", exc)
            return False
        return value.startswith("=")

    def _find_append_row(self, worksheet: gspread.Worksheet) -> int:
        """Next row for a new task — always below existing data, never reclaims row 2+."""
        all_values = worksheet.get_all_values()
        target = max(2, len(all_values) + 1)
        # Some personal tabs keep a formula in A2; never overwrite it.
        if target <= 2 and self._row2_has_formula_template(worksheet):
            return 3
        return target

    def _copy_row_format(
        self,
        worksheet: gspread.Worksheet,
        template_row: int,
        target_row: int,
        *,
        col_count: int,
    ) -> None:
        """Copy visual formatting from template row (dropdowns, colors)."""
        try:
            sheet_id = worksheet.id
            width = max(col_count, 1)
            self._spreadsheet.batch_update(
                {
                    "requests": [
                        {
                            "copyPaste": {
                                "source": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": template_row - 1,
                                    "endRowIndex": template_row,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": width,
                                },
                                "destination": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": target_row - 1,
                                    "endRowIndex": target_row,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": width,
                                },
                                "pasteType": "PASTE_FORMAT",
                            }
                        }
                    ]
                }
            )
        except Exception as exc:
            logger.warning("Could not copy row format: %s", exc)

    def _insert_formatted_row(
        self,
        worksheet: gspread.Worksheet,
        row: list[str],
        *,
        append_only: bool = False,
    ) -> int:
        """Write a new row without insert_row (no row shifting / #REF! breakage).

        When ``append_only`` is True (personal employee tabs), always writes below
        existing rows and never reclaims a blank-looking row 2 — that pattern was
        wiping FILTER/ARRAYFORMULA templates and making prior tasks disappear.

        On the main Tasks / Ideas tabs, reclaims the first row with an empty or
        ``#REF!`` task title so zombie rows do not accumulate.

        Personal tabs that mirror Tasks via FILTER must never receive direct
        task rows — see ``create_task`` and ``_personal_sheet_uses_tasks_filter``.
        """
        if self._personal_sheet_uses_tasks_filter(worksheet):
            raise RuntimeError(
                f"Refusing to write task rows on formula-driven tab {worksheet.title!r}"
            )
        col_count = len(row)
        target_row = (
            self._find_append_row(worksheet)
            if append_only
            else self._find_writable_row(worksheet, col_count)
        )
        start = gspread.utils.rowcol_to_a1(target_row, 1)
        end = gspread.utils.rowcol_to_a1(target_row, col_count)
        worksheet.update(
            f"{start}:{end}",
            [row],
            value_input_option="USER_ENTERED",
        )
        if target_row > 2:
            self._copy_row_format(
                worksheet,
                template_row=2,
                target_row=target_row,
                col_count=col_count,
            )
        return target_row

    def _ensure_ideas_worksheet(self) -> gspread.Worksheet:
        worksheet = self._all_worksheets().get(IDEAS_SHEET_NAME)
        if worksheet is None:
            worksheet = self._spreadsheet.add_worksheet(
                title=IDEAS_SHEET_NAME,
                rows=500,
                cols=len(IDEAS_HEADERS),
            )
            worksheet.append_row(IDEAS_HEADERS, value_input_option="USER_ENTERED")
            logger.info("Created worksheet %s", IDEAS_SHEET_NAME)
            self.invalidate_worksheet_cache()
            return worksheet

        if not worksheet.row_values(1):
            worksheet.append_row(IDEAS_HEADERS, value_input_option="USER_ENTERED")
        return worksheet

    def _ensure_named_worksheet(
        self,
        title: str,
        *,
        rows: int,
        cols: int,
        headers: list[str],
        default_rows: list[list[str]] | None = None,
    ) -> gspread.Worksheet:
        worksheet = self._all_worksheets().get(title)
        if worksheet is None:
            worksheet = self._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
            payload = [headers]
            if default_rows:
                payload.extend(default_rows)
            end = gspread.utils.rowcol_to_a1(len(payload), len(headers))
            worksheet.update(f"A1:{end}", payload, value_input_option="USER_ENTERED")
            logger.info("Created worksheet %s", title)
            self.invalidate_worksheet_cache()
            return worksheet
        existing = [str(h).strip() for h in worksheet.row_values(1)]
        if not existing:
            payload = [headers]
            if default_rows:
                payload.extend(default_rows)
            end = gspread.utils.rowcol_to_a1(len(payload), len(headers))
            worksheet.update(f"A1:{end}", payload, value_input_option="USER_ENTERED")
        return worksheet

    def ensure_sms_schema(self) -> None:
        """Create SMS settings + log tabs if they are missing."""
        self._ensure_named_worksheet(
            SMS_SHEET_NAME,
            rows=40,
            cols=len(SMS_SETTINGS_HEADERS),
            headers=list(SMS_SETTINGS_HEADERS),
            default_rows=[list(row) for row in SMS_SETTINGS_DEFAULT_ROWS],
        )
        self._ensure_named_worksheet(
            SMS_LOG_SHEET_NAME,
            rows=1000,
            cols=len(SMS_LOG_HEADERS),
            headers=list(SMS_LOG_HEADERS),
        )

    def ensure_template_schema(self) -> None:
        """Create the Templates tab, dropdowns, and an inactive sample row."""
        worksheet = self._get_or_rename_worksheet(TEMPLATE_SHEET_NAME, TEMPLATE_SHEET_ALIASES)
        if worksheet is None:
            worksheet = self._ensure_named_worksheet(
                TEMPLATE_SHEET_NAME,
                rows=200,
                cols=len(TEMPLATE_HEADERS),
                headers=list(TEMPLATE_HEADERS),
                default_rows=[list(TEMPLATE_TEST_ROW)],
            )
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        missing = [name for name in TEMPLATE_HEADERS if name not in headers]
        if missing:
            required_cols = len(headers) + len(missing)
            if worksheet.col_count < required_cols:
                worksheet.add_cols(required_cols - worksheet.col_count)
            for name in missing:
                col_index = len(headers) + 1
                worksheet.update_cell(1, col_index, name)
                headers.append(name)
        self._ensure_template_test_row(worksheet, headers)
        self._apply_template_dropdowns(worksheet, headers)

    def _ensure_template_test_row(self, worksheet: gspread.Worksheet, headers: list[str]) -> None:
        values = worksheet.get_all_values()
        title_idx = headers.index("تسک") if "تسک" in headers else 1
        for row in values[1:]:
            title = row[title_idx].strip() if title_idx < len(row) else ""
            if title == TEMPLATE_TEST_TITLE:
                return
        worksheet.append_row(list(TEMPLATE_TEST_ROW), value_input_option="USER_ENTERED")

    def _apply_template_dropdowns(self, worksheet: gspread.Worksheet, headers: list[str]) -> None:
        end_row = max(int(worksheet.row_count or 0), 200)
        requests: list[dict] = []
        dropdowns: list[tuple[str, tuple[str, ...]]] = [
            ("فعال", ("TRUE", "FALSE")),
            ("تکرارشوندگی", TEMPLATE_RECURRENCE_VALUES),
            ("اولویت", PRIORITIES),
        ]
        for header, options in dropdowns:
            if header not in headers:
                continue
            col_index = headers.index(header)
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": worksheet.id,
                            "startRowIndex": 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": item} for item in options],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                }
            )
        if not requests:
            return
        try:
            self._spreadsheet.batch_update({"requests": requests})
        except Exception:
            logger.exception("Failed applying Templates dropdowns")

    def list_template_entries(self) -> list[TemplateEntry]:
        worksheet = self._all_worksheets().get(TEMPLATE_SHEET_NAME)
        if worksheet is None:
            self.ensure_template_schema()
            worksheet = self._all_worksheets().get(TEMPLATE_SHEET_NAME)
        if worksheet is None:
            return []
        values = worksheet.get_all_values()
        if len(values) <= 1:
            return []
        headers = [str(h).strip() for h in values[0]]
        entries: list[TemplateEntry] = []
        for index, row in enumerate(values[1:], start=2):
            record = self._row_to_dict(headers, row)
            entry = template_from_record(record, index)
            if entry is not None:
                entries.append(entry)
        return entries

    def update_template_run(self, row_index: int, *, last_run: str, next_run: str) -> None:
        worksheet = self._all_worksheets().get(TEMPLATE_SHEET_NAME)
        if worksheet is None:
            return
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        updates: list[dict] = []
        if "آخرین اجرا" in headers:
            cell = gspread.utils.rowcol_to_a1(row_index, headers.index("آخرین اجرا") + 1)
            updates.append({"range": cell, "values": [[self._date_for_sheet(last_run)]]})
        if "اجرای بعدی" in headers:
            cell = gspread.utils.rowcol_to_a1(row_index, headers.index("اجرای بعدی") + 1)
            updates.append({"range": cell, "values": [[self._date_for_sheet(next_run)]]})
        if updates:
            worksheet.batch_update(updates, value_input_option="USER_ENTERED")

    def get_sms_settings(self) -> SmsSettings:
        now = time.monotonic()
        if self._sms_settings_cache is not None:
            cached_at, settings = self._sms_settings_cache
            if now - cached_at < SMS_SETTINGS_CACHE_TTL_SEC:
                return settings
        worksheet = self._all_worksheets().get(SMS_SHEET_NAME)
        if worksheet is None:
            settings = SmsSettings()
        else:
            try:
                records = worksheet.get_all_records()
            except Exception:
                logger.exception("SMS settings read failed")
                records = []
            settings = sms_settings_from_records(records)
        self._sms_settings_cache = (now, settings)
        return settings

    def append_sms_log(
        self,
        *,
        name: str,
        mobile: str,
        kind: str,
        text: str,
        send_id: str,
        status: str,
        detail: str = "",
    ) -> None:
        worksheet = self._all_worksheets().get(SMS_LOG_SHEET_NAME)
        if worksheet is None:
            self.ensure_sms_schema()
            worksheet = self._all_worksheets().get(SMS_LOG_SHEET_NAME)
        if worksheet is None:
            return
        stamp = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
        kind_label = {
            "new_task": "تسک جدید",
            "overdue": "عقب‌افتاده",
            "announce": "اطلاعیه",
            "filming": "تصویر برداری",
            "content": "تولید محتوا",
        }.get(kind, kind)
        worksheet.append_row(
            [
                stamp,
                name,
                mobile,
                kind_label,
                (text or "")[:500],
                send_id,
                status,
                (detail or "")[:250],
            ],
            value_input_option="USER_ENTERED",
        )

    def ensure_filming_schema(self) -> gspread.Worksheet:
        """Ensure the Meetings tab exists with the expected headers."""
        worksheet = self._get_or_rename_worksheet(FILMING_SHEET_NAME, FILMING_SHEET_ALIASES)
        if worksheet is None:
            worksheet = self._spreadsheet.add_worksheet(
                title=FILMING_SHEET_NAME,
                rows=1000,
                cols=len(FILMING_HEADERS),
            )
            worksheet.append_row(FILMING_HEADERS, value_input_option="USER_ENTERED")
            logger.info("Created worksheet %s", FILMING_SHEET_NAME)
            self.invalidate_worksheet_cache()
        self._ensure_project_column_dropdown(
            worksheet,
            header_aliases=FILMING_PROJECT_HEADER_ALIASES,
            log_label="Meetings",
        )
        return worksheet

        headers = [h.strip() for h in worksheet.row_values(1)]
        if not headers:
            worksheet.update(
                f"A1:{gspread.utils.rowcol_to_a1(1, len(FILMING_HEADERS))}",
                [FILMING_HEADERS],
                value_input_option="USER_ENTERED",
            )
            self._ensure_project_column_dropdown(
                worksheet,
                header_aliases=FILMING_PROJECT_HEADER_ALIASES,
                log_label="Meetings",
            )
            return worksheet

        # Accept both مسوول / مسئول spellings without duplicating columns.
        header_set = set(headers)
        missing = []
        for header in FILMING_HEADERS:
            if header == "مسوول" and ("مسوول" in header_set or "مسئول" in header_set):
                continue
            if header not in header_set:
                missing.append(header)
        if missing:
            start_col = len(headers) + 1
            if worksheet.col_count < start_col + len(missing) - 1:
                worksheet.add_cols(start_col + len(missing) - 1 - worksheet.col_count)
            for offset, header in enumerate(missing):
                worksheet.update_cell(1, start_col + offset, header)
            logger.info("Meetings sheet: added columns %s", missing)

        if missing or self._force_sheet_schema():
            self._ensure_project_column_dropdown(
                worksheet,
                header_aliases=FILMING_PROJECT_HEADER_ALIASES,
                log_label="Meetings",
            )
        return worksheet

    def _filming_worksheet(self) -> gspread.Worksheet:
        return self.ensure_filming_schema()

    def _parse_filming_row(
        self,
        *,
        headers: list[str],
        row: list[str],
        row_index: int,
    ) -> FilmingEntry | None:
        record = self._row_to_dict(headers, row)
        project = str(record.get("نام پروژه", "")).strip()
        if not project:
            return None
        return FilmingEntry(
            row_index=row_index,
            project=project,
            location=str(record.get("محل فیلم برداری", "")).strip(),
            day=str(record.get("روز", "")).strip(),
            hour=str(record.get("ساعت", "")).strip(),
            date=str(record.get("تاریخ", "")).strip().lstrip("'"),
            assignee_name=str(
                record.get("مسوول") or record.get("مسئول") or ""
            ).strip(),
            status=self._normalize_status(str(record.get("وضعیت", "")).strip()),
            created_by=str(record.get("ایجاد کننده", "")).strip(),
        )

    def create_filming_entry(
        self,
        *,
        project: str,
        location: str,
        day: str,
        hour: str,
        date: str,
        assignee: Personnel,
        created_by_name: str,
    ) -> FilmingEntry:
        worksheet = self._filming_worksheet()
        row = [
            project.strip(),
            location.strip(),
            day.strip(),
            hour.strip(),
            self._date_for_sheet(date.strip()),
            assignee.name,
            "در انتظار",
            created_by_name,
        ]
        row_index = self._insert_formatted_row(worksheet, row, append_only=True)
        return FilmingEntry(
            row_index=row_index,
            project=project.strip(),
            location=location.strip(),
            day=day.strip(),
            hour=hour.strip(),
            date=date.strip().lstrip("'"),
            assignee_name=assignee.name,
            status="pending",
            created_by=created_by_name,
        )

    def list_filming_entries(self, status: str | None = None) -> list[FilmingEntry]:
        worksheet = self._filming_worksheet()
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return []
        headers = all_values[0] or FILMING_HEADERS
        entries: list[FilmingEntry] = []
        for index, row in enumerate(all_values[1:], start=2):
            entry = self._parse_filming_row(headers=headers, row=row, row_index=index)
            if entry is None:
                continue
            if status is None:
                if entry.status in {"done", "cancelled"}:
                    continue
            elif entry.status != status:
                continue
            entries.append(entry)
        return entries

    def get_filming_entry_by_id(self, entry_id: str) -> FilmingEntry | None:
        try:
            sheet_name, row_str = entry_id.split(":", 1)
            row_index = int(row_str)
        except ValueError:
            return None
        if sheet_name not in {"filming", FILMING_SHEET_NAME, *FILMING_SHEET_ALIASES}:
            return None
        worksheet = self._filming_worksheet()
        headers = worksheet.row_values(1) or FILMING_HEADERS
        row_values = worksheet.row_values(row_index)
        if not row_values:
            return None
        return self._parse_filming_row(headers=headers, row=row_values, row_index=row_index)

    def update_filming_status(self, entry_id: str, personnel: Personnel, status: str) -> bool:
        from services.auth import can_update_filming_entry

        entry = self.get_filming_entry_by_id(entry_id)
        if entry is None or not can_update_filming_entry(personnel, entry):
            return False
        worksheet = self._filming_worksheet()
        headers = worksheet.row_values(1)
        try:
            status_col = headers.index("وضعیت") + 1
        except ValueError:
            return False
        worksheet.update_cell(entry.row_index, status_col, self._status_to_sheet(status))
        return True

    def get_filming_sheet_url(self) -> str:
        worksheet = self._filming_worksheet()
        return f"{config.google_sheet_url}?gid={worksheet.id}"

    def ensure_content_schema(self) -> gspread.Worksheet:
        """Ensure Design tab matches نام|پروژه|پست|استوری|وضعیت|ایجاد کننده."""
        worksheet = self._get_or_rename_worksheet(CONTENT_SHEET_NAME, CONTENT_SHEET_ALIASES)
        if worksheet is None:
            worksheet = self._spreadsheet.add_worksheet(
                title=CONTENT_SHEET_NAME,
                rows=1000,
                cols=len(CONTENT_HEADERS),
            )
            worksheet.append_row(CONTENT_HEADERS, value_input_option="USER_ENTERED")
            logger.info("Created worksheet %s", CONTENT_SHEET_NAME)
            self.invalidate_worksheet_cache()
            self.ensure_design_project_dropdown(worksheet)
            return worksheet

        headers = [h.strip() for h in worksheet.row_values(1)]
        if not headers:
            worksheet.update(
                f"A1:{gspread.utils.rowcol_to_a1(1, len(CONTENT_HEADERS))}",
                [CONTENT_HEADERS],
                value_input_option="USER_ENTERED",
            )
            self.ensure_design_project_dropdown(worksheet)
            return worksheet

        # Migrate legacy project header name only.
        if "پروژه" not in headers:
            for index, header in enumerate(headers):
                if header in CONTENT_PROJECT_HEADER_ALIASES and header != "پروژه":
                    worksheet.update_cell(1, index + 1, "پروژه")
                    headers[index] = "پروژه"
                    logger.info("Design sheet: renamed column %r -> پروژه", header)
                    break

        # Split legacy combined type column into پست + استوری if needed.
        if "پست / استوری" in headers and "پست" not in headers:
            try:
                legacy_idx = headers.index("پست / استوری")
                worksheet.update_cell(1, legacy_idx + 1, "پست")
                headers[legacy_idx] = "پست"
                logger.info("Design sheet: renamed 'پست / استوری' -> پست")
            except ValueError:
                pass

        missing = [h for h in CONTENT_HEADERS if h not in headers]
        if missing:
            start_col = len(headers) + 1
            if worksheet.col_count < start_col + len(missing) - 1:
                worksheet.add_cols(start_col + len(missing) - 1 - worksheet.col_count)
            for offset, header in enumerate(missing):
                worksheet.update_cell(1, start_col + offset, header)
            logger.info("Design sheet: added columns %s", missing)

        if missing or self._force_sheet_schema():
            self.ensure_design_project_dropdown(worksheet)
        return worksheet

    def ensure_design_project_dropdown(self, worksheet: gspread.Worksheet | None = None) -> None:
        """Dropdown on Design!پروژه from the Projects sheet list."""
        target = worksheet or self._all_worksheets().get(CONTENT_SHEET_NAME)
        if target is None:
            return
        self._ensure_project_column_dropdown(
            target,
            header_aliases=CONTENT_PROJECT_HEADER_ALIASES,
            log_label="Design",
        )

    def _ensure_project_column_dropdown(
        self,
        worksheet: gspread.Worksheet,
        *,
        header_aliases: frozenset[str],
        log_label: str,
    ) -> None:
        """Attach Projects!A2:A dropdown to the matching project column."""
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        try:
            project_col = next(i for i, h in enumerate(headers) if h in header_aliases)
        except StopIteration:
            return

        projects_title = self._projects_ws.title.replace("'", "''")
        end_row = max(int(worksheet.row_count or 0), 1000)
        try:
            self._spreadsheet.batch_update(
                {
                    "requests": [
                        {
                            "setDataValidation": {
                                "range": {
                                    "sheetId": worksheet.id,
                                    "startRowIndex": 1,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": project_col,
                                    "endColumnIndex": project_col + 1,
                                },
                                "rule": {
                                    "condition": {
                                        "type": "ONE_OF_RANGE",
                                        "values": [
                                            {
                                                "userEnteredValue": (
                                                    f"='{projects_title}'!$A$2:$A"
                                                )
                                            }
                                        ],
                                    },
                                    "showCustomUi": True,
                                    "strict": False,
                                    "inputMessage": "پروژه را از لیست انتخاب کنید",
                                },
                            }
                        }
                    ]
                }
            )
            logger.info(
                "%s sheet: project dropdown linked to %s!A2:A",
                log_label,
                projects_title,
            )
        except Exception:
            logger.exception("Failed applying %s project dropdown", log_label)

    def _content_worksheet(self) -> gspread.Worksheet:
        return self.ensure_content_schema()

    def get_design_names(self) -> list[str]:
        """People names for Design picker (sheet column نام, else defaults)."""
        worksheet = self._content_worksheet()
        headers = [h.strip() for h in worksheet.row_values(1)]
        if "نام" not in headers:
            return list(CONTENT_DESIGN_NAMES)
        name_col = headers.index("نام") + 1
        values = worksheet.col_values(name_col)[1:]
        names: list[str] = []
        seen: set[str] = set()
        for raw in values:
            name = str(raw).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        if names:
            return names
        flagged = [p.name for p in self.get_active_personnel() if p.content_access]
        seen_flagged: set[str] = set()
        unique_flagged: list[str] = []
        for name in flagged:
            if name and name not in seen_flagged:
                seen_flagged.add(name)
                unique_flagged.append(name)
        return unique_flagged or list(CONTENT_DESIGN_NAMES)

    @staticmethod
    def _content_project_from_record(record: dict[str, str]) -> str:
        for key in ("پروژه", "نام پروژه", "project", "Project"):
            value = str(record.get(key, "")).strip()
            if value:
                return value
        return ""

    def _parse_content_row(
        self,
        *,
        headers: list[str],
        row: list[str],
        row_index: int,
    ) -> ContentEntry | None:
        record = self._row_to_dict(headers, row)
        name = str(record.get("نام", "")).strip()
        project = self._content_project_from_record(record)
        post = str(record.get("پست", "")).strip()
        story = str(record.get("استوری", "")).strip()
        # Legacy combined column fallback.
        legacy_type = str(record.get("پست / استوری", "")).strip()
        if legacy_type and not post and not story:
            if "استوری" in legacy_type and "پست" in legacy_type:
                post, story = "✓", "✓"
            elif "استوری" in legacy_type:
                story = "✓"
            else:
                post = legacy_type or "✓"
        # Legacy person-as-column layout.
        if not name:
            for column in CONTENT_DESIGN_NAMES:
                if str(record.get(column, "")).strip():
                    name = column
                    break
        # Roster-only rows (name without project) are not work entries.
        if not name or not project:
            return None
        return ContentEntry(
            row_index=row_index,
            name=name,
            project=project,
            post=post,
            story=story,
            status=self._normalize_status(str(record.get("وضعیت", "")).strip()),
            created_by=str(record.get("ایجاد کننده", "")).strip(),
        )

    def create_content_entry(
        self,
        *,
        name: str,
        project: str,
        include_post: bool,
        include_story: bool,
        created_by_name: str,
    ) -> ContentEntry:
        person = name.strip()
        if not person:
            raise ValueError("Design entry name is required")
        if not include_post and not include_story:
            raise ValueError("At least one of post/story must be selected")

        worksheet = self._content_worksheet()
        headers = worksheet.row_values(1) or CONTENT_HEADERS
        # Write by header order so extra leftover columns are left untouched.
        values_by_header = {
            "نام": person,
            "پروژه": project.strip(),
            "پست": "✓" if include_post else "",
            "استوری": "✓" if include_story else "",
            "وضعیت": "در انتظار",
            "ایجاد کننده": created_by_name,
        }
        row = [values_by_header.get(h.strip(), "") for h in headers]
        # If expected headers are missing from a messy sheet, append canonical row.
        if "نام" not in {h.strip() for h in headers}:
            row = [
                person,
                project.strip(),
                "✓" if include_post else "",
                "✓" if include_story else "",
                "در انتظار",
                created_by_name,
            ]
        row_index = self._insert_formatted_row(worksheet, row, append_only=True)
        return ContentEntry(
            row_index=row_index,
            name=person,
            project=project.strip(),
            post="✓" if include_post else "",
            story="✓" if include_story else "",
            status="pending",
            created_by=created_by_name,
        )

    def list_content_entries(self, status: str | None = None) -> list[ContentEntry]:
        worksheet = self._content_worksheet()
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return []
        headers = all_values[0] or CONTENT_HEADERS
        entries: list[ContentEntry] = []
        for index, row in enumerate(all_values[1:], start=2):
            entry = self._parse_content_row(headers=headers, row=row, row_index=index)
            if entry is None:
                continue
            if status is None:
                if entry.status in {"done", "cancelled"}:
                    continue
            elif entry.status != status:
                continue
            entries.append(entry)
        return entries

    def get_content_entry_by_id(self, entry_id: str) -> ContentEntry | None:
        try:
            sheet_name, row_str = entry_id.split(":", 1)
            row_index = int(row_str)
        except ValueError:
            return None
        if sheet_name not in {"design", "content", CONTENT_SHEET_NAME, *CONTENT_SHEET_ALIASES}:
            return None
        worksheet = self._content_worksheet()
        headers = worksheet.row_values(1) or CONTENT_HEADERS
        row_values = worksheet.row_values(row_index)
        if not row_values:
            return None
        return self._parse_content_row(headers=headers, row=row_values, row_index=row_index)

    def update_content_status(self, entry_id: str, personnel: Personnel, status: str) -> bool:
        from services.auth import can_update_content_entry

        entry = self.get_content_entry_by_id(entry_id)
        if entry is None or not can_update_content_entry(personnel, entry):
            return False
        worksheet = self._content_worksheet()
        headers = worksheet.row_values(1)
        try:
            status_col = headers.index("وضعیت") + 1
        except ValueError:
            return False
        worksheet.update_cell(entry.row_index, status_col, self._status_to_sheet(status))
        return True

    def get_content_sheet_url(self) -> str:
        worksheet = self._content_worksheet()
        return f"{config.google_sheet_url}?gid={worksheet.id}"

    def find_personnel_by_name_hint(self, name_hint: str) -> Personnel | None:
        """Find active personnel whose name contains the hint (e.g. column surname)."""
        hint = name_hint.strip()
        if not hint:
            return None
        matches = [
            member
            for member in self.get_active_personnel()
            if hint in member.name
        ]
        if len(matches) == 1:
            return matches[0]
        exact = [m for m in matches if m.name.strip() == hint]
        return exact[0] if len(exact) == 1 else (matches[0] if matches else None)

    _personnel_from_record = staticmethod(personnel_from_record)

    def create_idea(self, personnel: Personnel, text: str) -> Idea:
        worksheet = self._ensure_ideas_worksheet()
        created_at, _ = self._shamsi_today()
        role_label = self._role_label(personnel.role)
        row = [
            text,
            personnel.name,
            role_label,
            self._date_for_sheet(created_at),
            str(personnel.telegram_id),
        ]
        row_index = self._insert_formatted_row(worksheet, row)
        return Idea(
            text=text,
            created_by=personnel.name,
            role=role_label,
            created_at=created_at,
            telegram_id=personnel.telegram_id,
            row_index=row_index,
        )

    def get_recent_ideas(self, limit: int = 15) -> list[Idea]:
        worksheet = self._ensure_ideas_worksheet()
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return []

        headers = all_values[0]
        ideas: list[Idea] = []
        for index, row in enumerate(all_values[1:], start=2):
            record = self._row_to_dict(headers, row)
            idea_text = str(record.get("ایده", "")).strip()
            if not idea_text:
                continue
            raw_id = str(record.get("telegram_id", "")).strip()
            try:
                telegram_id = int(float(raw_id)) if raw_id else 0
            except (ValueError, TypeError):
                telegram_id = 0
            ideas.append(
                Idea(
                    text=idea_text,
                    created_by=str(record.get("ثبت کننده", "")).strip(),
                    role=str(record.get("نقش", "")).strip(),
                    created_at=str(record.get("تاریخ ثبت", "")).strip(),
                    telegram_id=telegram_id,
                    row_index=index,
                )
            )
        return list(reversed(ideas[-limit:]))

    def get_ideas_sheet_url(self) -> str:
        worksheet = self._ensure_ideas_worksheet()
        return f"{config.google_sheet_url}?gid={worksheet.id}"

    def get_personnel_by_telegram_id(self, telegram_id: int, role: str | None = None) -> Personnel | None:
        records = self._get_personnel_records()
        matches: list[Personnel] = []
        for record in records:
            tid = self._record_telegram_id(record)
            if tid != telegram_id:
                continue
            if not self._record_is_active(record):
                continue
            person = self._personnel_from_record(record, telegram_id)
            if role and person.role != role:
                continue
            matches.append(person)
        if not matches:
            return None
        chosen = matches[0]
        if not role:
            for member in matches:
                if member.role == "admin":
                    chosen = member
                    break
            else:
                for member in matches:
                    if member.senior_admin:
                        chosen = member
                        break
        for member in matches:
            chosen = coalesce_personnel(chosen, member)
        return chosen

    def get_broadcast_recipients(self) -> list[Personnel]:
        """All active Personnel rows with a valid Telegram id (private DM targets)."""
        records = self._get_personnel_records()
        seen: dict[int, Personnel] = {}
        for record in records:
            if not self._record_is_active(record):
                continue
            tid = self._record_telegram_id(record)
            if tid is None:
                continue
            person = self._personnel_from_record(record, tid)
            existing = seen.get(tid)
            if existing is None:
                seen[tid] = person
            else:
                seen[tid] = coalesce_personnel(existing, person)
        return sorted(seen.values(), key=lambda p: p.name)

    def get_active_personnel(self, role: str | None = None) -> list[Personnel]:
        records = self._get_personnel_records()
        seen: dict[int, Personnel] = {}
        for record in records:
            if not self._record_is_active(record):
                continue
            tid = self._record_telegram_id(record)
            if tid is None:
                continue
            person = self._personnel_from_record(record, tid)
            if role and person.role != role:
                continue
            existing = seen.get(tid)
            if existing is None:
                seen[tid] = person
            else:
                seen[tid] = coalesce_personnel(existing, person)
        return sorted(seen.values(), key=lambda p: p.name)

    def get_active_employees(self) -> list[Personnel]:
        return self.get_active_personnel(role="employee")

    def get_projects(self) -> list[str]:
        """Cached Projects list (Sheets API calls are rate-limited per minute)."""
        now = time.monotonic()
        if self._projects_cache is not None:
            cached_at, projects = self._projects_cache
            if now - cached_at < PROJECTS_CACHE_TTL_SEC:
                return projects

        values = self._projects_ws.col_values(1)
        data_start = self._projects_data_start(values)
        projects: list[str] = []
        seen: set[str] = set()
        for value in values[data_start:]:
            name = value.strip()
            if name and name not in seen:
                seen.add(name)
                projects.append(name)
        projects = self.sort_projects(projects)
        self._projects_cache = (now, projects)
        return projects

    def _personal_worksheet(self, employee_name: str) -> gspread.Worksheet | None:
        return self._all_worksheets().get(employee_name)

    def create_task(
        self,
        *,
        title: str,
        project: str,
        assignee: Personnel,
        created_by_name: str,
        priority: str,
        due_date: str = "",
    ) -> Task:
        created_at, month = self._shamsi_today()
        priority = priority if priority in PRIORITIES else "Medium"
        # Default deadline to today when the caller does not supply one.
        effective_due = due_date.strip() or created_at

        main_row = [
            title,
            project,
            assignee.name,
            created_by_name,
            self._date_for_sheet(created_at),
            self._date_for_sheet(effective_due),
            priority,
            month,
            self._status_to_sheet("pending"),
        ]
        main_row_index = self._insert_formatted_row(self._tasks_ws, main_row)
        self._personal_tasks_cache = None

        personal_ws = self._personal_worksheet(assignee.name)
        uses_filter_mirror = (
            personal_ws is not None and self._personal_sheet_uses_tasks_filter(personal_ws)
        )

        # Legacy personal tabs (no FILTER): duplicate the row for status/description.
        # FILTER tabs (e.g. Bakhshande): only Tasks is written; A2 FILTER shows tasks.
        personal_row_index = main_row_index
        if personal_ws is not None and not uses_filter_mirror:
            personal_row = [
                title,
                project,
                assignee.name,
                created_by_name,
                self._date_for_sheet(created_at),
                self._date_for_sheet(effective_due),
                priority,
                "در انتظار",
                "",
            ]
            personal_row_index = self._insert_formatted_row(
                personal_ws,
                personal_row,
                append_only=True,
            )

        task_sheet = "Tasks" if uses_filter_mirror or personal_ws is None else assignee.name
        task_row = main_row_index if uses_filter_mirror or personal_ws is None else personal_row_index
        task_gid = (
            self._tasks_ws.id
            if uses_filter_mirror or personal_ws is None
            else personal_ws.id
        )

        return Task(
            sheet_name=task_sheet,
            row_index=task_row,
            title=title,
            project=project,
            assignee_name=assignee.name,
            created_by=created_by_name,
            created_at=created_at,
            due_date=effective_due,
            priority=priority,
            status="pending",
            description="",
            sheet_gid=task_gid,
        )

    def _parse_task_row(
        self,
        *,
        sheet_name: str,
        headers: list[str],
        row: list[str],
        row_index: int,
        sheet_gid: int = 0,
    ) -> Task | None:
        record = self._row_to_dict(headers, row)
        title = str(record.get("تسک", "")).strip()
        if not title:
            return None
        assignee = str(
            record.get(
                "مسوول تسک",
                record.get("مسئول تسک", record.get("i", "")),
            )
        ).strip()
        status_raw = str(record.get("وضعیت", "")).strip()
        return Task(
            sheet_name=sheet_name,
            row_index=row_index,
            title=title,
            project=str(record.get("پروژه", "")).strip(),
            assignee_name=assignee,
            created_by=str(record.get("ایجاد کننده", "")).strip(),
            created_at=str(record.get("تاریخ ایجاد", "")).strip(),
            due_date=str(record.get("ددلاین", "")).strip(),
            priority=str(record.get("اولویت", "")).strip(),
            status=self._normalize_status(status_raw),
            description=str(record.get("توضیحات", "")).strip(),
            sheet_gid=sheet_gid,
        )

    def get_all_tasks(self, status: str | None = None) -> list[Task]:
        """Return tasks across all personnel personal sheets (for senior admins)."""
        tasks: list[Task] = []
        for person in self.get_active_personnel():
            if person.role == "admin":
                continue
            tasks.extend(self.get_tasks_for_assignee(person, status=status))
        return tasks

    def list_main_tasks(self) -> list[Task]:
        """All rows from the Tasks tab, including done/cancelled (for reports)."""
        all_values = self._tasks_ws.get_all_values()
        if len(all_values) <= 1:
            return []
        headers = all_values[0]
        tasks: list[Task] = []
        for index, row in enumerate(all_values[1:], start=2):
            task = self._parse_task_row(
                sheet_name="Tasks",
                headers=headers,
                row=row,
                row_index=index,
                sheet_gid=int(self._tasks_ws.id),
            )
            if task is not None:
                tasks.append(task)
        personal = self._collect_personal_tasks()
        if personal:
            tasks = overlay_status_from_personal(tasks, personal)
        return tasks

    def _personal_worksheets(self) -> list[gspread.Worksheet]:
        system = {normalize_sheet_title(name) for name in SYSTEM_TAB_ORDER}
        found: list[gspread.Worksheet] = []
        for title, worksheet in self._all_worksheets().items():
            if normalize_sheet_title(title) in system:
                continue
            found.append(worksheet)
        return found

    def _collect_personal_tasks(self, *, force: bool = False) -> list[Task]:
        now = time.monotonic()
        if not force and self._personal_tasks_cache is not None:
            cached_at, rows = self._personal_tasks_cache
            if now - cached_at < PERSONNEL_CACHE_TTL_SEC:
                return rows
        collected: list[Task] = []
        for worksheet in self._personal_worksheets():
            if self._personal_sheet_uses_tasks_filter(worksheet):
                continue
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                continue
            headers = all_values[0]
            sheet_id = int(worksheet.id)
            for index, row in enumerate(all_values[1:], start=2):
                task = self._parse_task_row(
                    sheet_name=worksheet.title,
                    headers=headers,
                    row=row,
                    row_index=index,
                    sheet_gid=sheet_id,
                )
                if task is not None:
                    collected.append(task)
        self._personal_tasks_cache = (now, collected)
        return collected

    def sync_tasks_status_from_personal(self) -> dict[str, int]:
        """Write personal-tab وضعیت onto matching rows in Tasks."""
        self.ensure_tasks_status_column()
        all_values = self._tasks_ws.get_all_values()
        if len(all_values) <= 1:
            return {"updated": 0, "scanned": 0, "tabs": 0}
        headers = [str(header).strip() for header in all_values[0]]
        try:
            status_col = headers.index(STATUS_HEADER) + 1
        except ValueError:
            return {"updated": 0, "scanned": 0, "tabs": 0}

        main_tasks: list[Task] = []
        for index, row in enumerate(all_values[1:], start=2):
            task = self._parse_task_row(
                sheet_name="Tasks",
                headers=all_values[0],
                row=row,
                row_index=index,
                sheet_gid=int(self._tasks_ws.id),
            )
            if task is not None:
                main_tasks.append(task)

        personal = self._collect_personal_tasks(force=True)
        merged = overlay_status_from_personal(main_tasks, personal)
        by_row = {task.row_index: task.status for task in merged}
        original = {task.row_index: task.status for task in main_tasks}
        updates: list[dict] = []
        col_letter = _col_to_a1(status_col)
        for row_index, status in by_row.items():
            if original.get(row_index) == status:
                continue
            updates.append(
                {
                    "range": f"{col_letter}{row_index}",
                    "values": [[self._status_to_sheet(status)]],
                }
            )

        chunk_size = 80
        for start in range(0, len(updates), chunk_size):
            chunk = updates[start : start + chunk_size]
            self._tasks_ws.batch_update(chunk, value_input_option="USER_ENTERED")

        logger.info(
            "Tasks status synced from personal tabs: updated=%s scanned=%s tabs=%s",
            len(updates),
            len(personal),
            len(self._personal_worksheets()),
        )
        return {
            "updated": len(updates),
            "scanned": len(personal),
            "tabs": len(self._personal_worksheets()),
        }

    def get_tasks_for_personnel(self, personnel: Personnel, status: str | None = None) -> list[Task]:
        """Tasks visible to this user (own tasks, or all if senior admin with view_all_tasks)."""
        from services.auth import can_view_all_tasks

        if can_view_all_tasks(personnel):
            return self.get_all_tasks(status=status)
        return self.get_tasks_for_assignee(personnel, status=status)

    def get_tasks_for_assignee(self, personnel: Personnel, status: str | None = None) -> list[Task]:
        personal_ws = self._personal_worksheet(personnel.name)
        if personal_ws is not None:
            return self._get_tasks_from_sheet(
                personal_ws,
                personnel.name,
                PERSONAL_HEADERS,
                personnel.name,
                status,
            )

        return self._get_tasks_from_sheet(
            self._tasks_ws,
            "Tasks",
            TASKS_HEADERS,
            personnel.name,
            status,
        )

    def _get_tasks_from_sheet(
        self,
        worksheet: gspread.Worksheet,
        sheet_name: str,
        headers: list[str],
        assignee_name: str,
        status: str | None,
    ) -> list[Task]:
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:
            return []

        actual_headers = all_values[0]
        tasks: list[Task] = []
        for index, row in enumerate(all_values[1:], start=2):
            task = self._parse_task_row(
                sheet_name=sheet_name,
                headers=actual_headers if actual_headers else headers,
                row=row,
                row_index=index,
                sheet_gid=int(worksheet.id),
            )
            if task is None:
                continue
            if task.assignee_name != assignee_name:
                continue
            if status is None:
                if task.status in {"done", "cancelled"}:
                    continue
            elif task.status != status:
                continue
            tasks.append(task)
        return tasks

    def _worksheet_by_gid(self, sheet_gid: int) -> gspread.Worksheet | None:
        if int(self._tasks_ws.id) == sheet_gid:
            return self._tasks_ws
        for worksheet in self._all_worksheets().values():
            if int(worksheet.id) == sheet_gid:
                return worksheet
        return None

    def _write_status_cell(
        self,
        worksheet: gspread.Worksheet,
        row_index: int,
        status: str,
        *,
        create_column: bool = False,
    ) -> bool:
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        try:
            status_col = headers.index(STATUS_HEADER) + 1
        except ValueError:
            if not create_column:
                return False
            status_col = len(headers) + 1
            if worksheet.col_count < status_col:
                worksheet.add_cols(status_col - worksheet.col_count)
            worksheet.update_cell(1, status_col, STATUS_HEADER)
        worksheet.update_cell(row_index, status_col, self._status_to_sheet(status))
        return True

    def _tasks_row_for(self, task: Task) -> int | None:
        if task.sheet_name == "Tasks" or (
            task.sheet_gid and int(task.sheet_gid) == int(self._tasks_ws.id)
        ):
            return task.row_index
        all_values = self._tasks_ws.get_all_values()
        if len(all_values) <= 1:
            return None
        headers = all_values[0] or TASKS_HEADERS
        want = self._task_match_key(task.title, task.assignee_name, task.due_date)
        for index, row in enumerate(all_values[1:], start=2):
            parsed = self._parse_task_row(
                sheet_name="Tasks",
                headers=headers,
                row=row,
                row_index=index,
                sheet_gid=int(self._tasks_ws.id),
            )
            if parsed is None:
                continue
            if self._task_match_key(parsed.title, parsed.assignee_name, parsed.due_date) == want:
                return index
        return None

    def _find_task_by_id(self, task_id: str) -> Task | None:
        """Resolve a compact ``t:gid:row`` id, or a legacy ``sheet:row`` id."""
        parsed = parse_task_id(task_id)
        if parsed is None:
            return None
        sheet_gid, sheet_name, row_index = parsed
        if sheet_gid is not None:
            worksheet = self._worksheet_by_gid(sheet_gid)
            headers = TASKS_HEADERS if worksheet is self._tasks_ws else PERSONAL_HEADERS
        elif sheet_name == "Tasks":
            worksheet = self._tasks_ws
            headers = TASKS_HEADERS
        else:
            worksheet = self._personal_worksheet(sheet_name or "")
            headers = PERSONAL_HEADERS
        if worksheet is None:
            return None

        row_values = worksheet.row_values(row_index)
        if not row_values:
            return None
        actual_headers = worksheet.row_values(1)
        return self._parse_task_row(
            sheet_name=worksheet.title,
            headers=actual_headers if actual_headers else headers,
            row=row_values,
            row_index=row_index,
            sheet_gid=int(worksheet.id),
        )

    def get_task_by_id(self, task_id: str, personnel: Personnel) -> Task | None:
        from services.auth import can_view_all_tasks, is_admin

        task = self._find_task_by_id(task_id)
        if task is None:
            return None
        if can_view_all_tasks(personnel) or is_admin(personnel):
            return task
        if task.assignee_name == personnel.name:
            return task
        return None

    def update_task_status(self, task_id: str, personnel: Personnel, status: str) -> bool:
        from services.auth import is_admin, is_senior_admin

        task = self.get_task_by_id(task_id, personnel)
        if task is None:
            return False
        if (
            task.assignee_name != personnel.name
            and not is_admin(personnel)
            and not is_senior_admin(personnel)
        ):
            return False

        self._personal_tasks_cache = None
        updated = False
        personal_ws = self._personal_worksheet(task.assignee_name)
        if personal_ws is not None:
            # Only touch وضعیت — FILTER mirror tabs must not overwrite A:G spill.
            target_row = (
                task.row_index
                if (not task.sheet_gid or int(task.sheet_gid) == int(personal_ws.id))
                else None
            )
            if target_row is None and not self._personal_sheet_uses_tasks_filter(personal_ws):
                target_row = task.row_index
            if target_row is not None:
                if self._write_status_cell(personal_ws, target_row, status):
                    updated = True

        tasks_row = self._tasks_row_for(task)
        if tasks_row is not None:
            if self._write_status_cell(self._tasks_ws, tasks_row, status, create_column=True):
                updated = True
        elif personal_ws is None:
            if self._write_status_cell(
                self._tasks_ws, task.row_index, status, create_column=True
            ):
                updated = True

        return updated

    def _write_task_field(
        self,
        worksheet: gspread.Worksheet,
        row_index: int,
        header_name: str,
        value: str,
        *,
        create_column: bool = False,
    ) -> bool:
        headers = [str(h).strip() for h in worksheet.row_values(1)]
        try:
            col = headers.index(header_name) + 1
        except ValueError:
            if not create_column:
                return False
            col = len(headers) + 1
            if worksheet.col_count < col:
                worksheet.add_cols(col - worksheet.col_count)
            worksheet.update_cell(1, col, header_name)
        worksheet.update_cell(row_index, col, value)
        return True

    def update_task_note(self, task_id: str, personnel: Personnel, note: str) -> bool:
        task = self.get_task_by_id(task_id, personnel)
        if task is None:
            return False
        self._personal_tasks_cache = None
        updated = False
        personal_ws = self._personal_worksheet(task.assignee_name)
        if personal_ws is not None:
            target_row = (
                task.row_index
                if (not task.sheet_gid or int(task.sheet_gid) == int(personal_ws.id))
                else None
            )
            if target_row is None and not self._personal_sheet_uses_tasks_filter(personal_ws):
                target_row = task.row_index
            if target_row is not None:
                if self._write_task_field(personal_ws, target_row, "توضیحات", note, create_column=True):
                    updated = True
        tasks_row = self._tasks_row_for(task)
        if tasks_row is not None:
            if self._write_task_field(self._tasks_ws, tasks_row, "توضیحات", note, create_column=True):
                updated = True
        return updated

    def update_task_due_date(self, task_id: str, personnel: Personnel, due_date: str) -> bool:
        from services.auth import is_admin, is_senior_admin

        task = self.get_task_by_id(task_id, personnel)
        if task is None or not (is_admin(personnel) or is_senior_admin(personnel)):
            return False
        self._personal_tasks_cache = None
        updated = False
        tasks_row = self._tasks_row_for(task)
        if tasks_row is not None:
            if self._write_task_field(self._tasks_ws, tasks_row, "ددلاین", due_date):
                updated = True
        personal_ws = self._personal_worksheet(task.assignee_name)
        if personal_ws is not None and not self._personal_sheet_uses_tasks_filter(personal_ws):
            target_row = (
                task.row_index
                if (not task.sheet_gid or int(task.sheet_gid) == int(personal_ws.id))
                else None
            )
            if target_row is not None:
                if self._write_task_field(personal_ws, target_row, "ددلاین", due_date):
                    updated = True
        return updated

    def update_task_priority(self, task_id: str, personnel: Personnel, priority: str) -> bool:
        from services.auth import is_admin, is_senior_admin

        task = self.get_task_by_id(task_id, personnel)
        if task is None or not (is_admin(personnel) or is_senior_admin(personnel)):
            return False
        if priority not in PRIORITIES:
            return False
        self._personal_tasks_cache = None
        updated = False
        tasks_row = self._tasks_row_for(task)
        if tasks_row is not None:
            if self._write_task_field(self._tasks_ws, tasks_row, "اولویت", priority):
                updated = True
        personal_ws = self._personal_worksheet(task.assignee_name)
        if personal_ws is not None and not self._personal_sheet_uses_tasks_filter(personal_ws):
            target_row = (
                task.row_index
                if (not task.sheet_gid or int(task.sheet_gid) == int(personal_ws.id))
                else None
            )
            if target_row is not None:
                if self._write_task_field(personal_ws, target_row, "اولویت", priority):
                    updated = True
        return updated

    def get_open_tasks_count(self, personnel: Personnel) -> int:
        tasks = self.get_tasks_for_assignee(personnel, status=None)
        return sum(1 for t in tasks if t.status not in ("done", "cancelled"))

    def list_overdue_open_tasks(self) -> list[Task]:
        """Open (not done) tasks whose Jalali due date is before today."""
        today = jdatetime.date.today()
        overdue: list[Task] = []
        for person in self.get_active_personnel():
            if person.role == "admin":
                continue
            for task in self.get_tasks_for_assignee(person, status=None):
                due = self._parse_due_as_jalali(task.due_date)
                if due is None:
                    continue
                if due < today:
                    overdue.append(task)
        return overdue

    def _row_color_request(
        self,
        *,
        sheet_id: int,
        row_index: int,
        col_count: int,
        color: dict[str, float] | None,
    ) -> dict:
        """Build a Sheets API repeatCell request for one row's background."""
        cell_format: dict = {
            "userEnteredFormat": {
                "backgroundColor": color
                if color is not None
                else {"red": 1.0, "green": 1.0, "blue": 1.0},
            }
        }
        return {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_index - 1,
                    "endRowIndex": row_index,
                    "startColumnIndex": 0,
                    "endColumnIndex": max(col_count, 1),
                },
                "cell": cell_format,
                "fields": "userEnteredFormat.backgroundColor",
            }
        }

    def sync_overdue_row_colors(self) -> tuple[dict[str, int], list[Task]]:
        """Paint newly overdue open rows; unpaint rows that are no longer overdue.

        FILTER personal tabs are never written (spill ranges). Returns counts.
        """
        overdue_color = {"red": 0.96, "green": 0.78, "blue": 0.78}
        overdue_open = self.list_overdue_open_tasks()
        overdue_keys = {
            self._task_match_key(t.title, t.assignee_name, t.due_date) for t in overdue_open
        }
        wanted_red: dict[tuple[int, int], int] = {}

        def _process_worksheet(
            worksheet: gspread.Worksheet,
            headers: list[str],
            *,
            allow_write: bool,
        ) -> None:
            if not allow_write:
                return
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                return
            actual_headers = all_values[0] or headers
            col_count = max(len(actual_headers), len(headers), 8)
            sheet_id = int(worksheet.id)
            for index, row in enumerate(all_values[1:], start=2):
                task = self._parse_task_row(
                    sheet_name=worksheet.title,
                    headers=actual_headers,
                    row=row,
                    row_index=index,
                    sheet_gid=sheet_id,
                )
                if task is None:
                    continue
                is_overdue = (
                    self._task_match_key(task.title, task.assignee_name, task.due_date)
                    in overdue_keys
                )
                if is_overdue:
                    wanted_red[(sheet_id, index)] = col_count

        _process_worksheet(self._tasks_ws, TASKS_HEADERS, allow_write=True)

        for person in self.get_active_personnel():
            if person.role == "admin":
                continue
            personal_ws = self._personal_worksheet(person.name)
            if personal_ws is None:
                continue
            if self._personal_sheet_uses_tasks_filter(personal_ws):
                continue
            _process_worksheet(personal_ws, PERSONAL_HEADERS, allow_write=True)

        requests: list[dict] = []
        for key, col_count in wanted_red.items():
            if key in self._overdue_red_rows:
                continue
            sheet_id, row_index = key
            requests.append(
                self._row_color_request(
                    sheet_id=sheet_id,
                    row_index=row_index,
                    col_count=col_count,
                    color=overdue_color,
                )
            )
        for key, col_count in self._overdue_red_rows.items():
            if key in wanted_red:
                continue
            sheet_id, row_index = key
            requests.append(
                self._row_color_request(
                    sheet_id=sheet_id,
                    row_index=row_index,
                    col_count=col_count,
                    color=None,
                )
            )

        painted = sum(1 for key in wanted_red if key not in self._overdue_red_rows)
        cleared = sum(1 for key in self._overdue_red_rows if key not in wanted_red)

        chunk_size = 40
        for start in range(0, len(requests), chunk_size):
            chunk = requests[start : start + chunk_size]
            try:
                self._spreadsheet.batch_update({"requests": chunk})
            except Exception as extra:
                logger.warning("Overdue color batch failed (%d requests): %s", len(chunk), extra)

        self._overdue_red_rows = wanted_red
        return {
            "painted": painted,
            "cleared": cleared,
            "requests": len(requests),
            "overdue_open": len(overdue_open),
        }, overdue_open

    def get_sheet_url(self, personnel: Personnel) -> str:
        """Return a direct link to the most relevant worksheet tab for this user."""
        from services.auth import can_view_all_tasks

        base = config.google_sheet_url
        if personnel.role == "admin" or can_view_all_tasks(personnel):
            tab_name = "Tasks"
        else:
            tab_name = personnel.name if self._personal_worksheet(personnel.name) else "Tasks"
        worksheet = self._all_worksheets().get(tab_name)
        if worksheet is not None:
            return f"{base}?gid={worksheet.id}"
        return base


@lru_cache(maxsize=1)
def get_sheets_service() -> SheetsService:
    """Singleton Sheets service (cached for the process lifetime)."""
    return SheetsService()
