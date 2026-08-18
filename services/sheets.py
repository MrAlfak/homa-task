"""Google Sheets integration — matches Team Management Homa layout."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import gspread
import jdatetime
from google.oauth2.service_account import Credentials

from config import config

logger = logging.getLogger(__name__)

PERSONNEL_CACHE_TTL_SEC = 45.0
PROJECTS_CACHE_TTL_SEC = 45.0
# gspread.Spreadsheet.worksheet()/worksheets() re-fetch the *entire* spreadsheet
# metadata from the API on every call. Caching the title -> Worksheet mapping
# for a short window avoids one extra Sheets API round-trip per personal-sheet
# lookup (create_task, task lists, status updates, ...) and per Ideas-tab
# access — this is a common source of hitting Google Sheets' per-minute quota
# (which surfaces to users as "خطایی رخ داد" until they retry).
WORKSHEET_CACHE_TTL_SEC = 60.0

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

PERSONNEL_HEADERS = [
    "telegram_id",
    "name",
    "role",
    "active",
    "senior_admin",      # مدیر ارشد — TRUE marks a senior manager
    "view_all_tasks",    # مشاهده همه تسک — when TRUE, senior admin sees all tasks
]

# Extra Personnel columns auto-added on startup (English key → Persian header in sheet).
PERSONNEL_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("senior_admin", "مدیر ارشد"),
    ("view_all_tasks", "مشاهده همه تسک"),
    ("filming_access", "تصویر برداری"),
    ("content_access", "تولید محتوا"),
)

# Boolean Personnel columns that get a TRUE/FALSE dropdown (English + Persian headers).
PERSONNEL_BOOL_HEADER_ALIASES: tuple[tuple[str, ...], ...] = (
    ("active", "فعال"),
    ("senior_admin", "مدیر ارشد"),
    ("view_all_tasks", "مشاهده همه تسک"),
    ("filming_access", "تصویر برداری"),
    ("content_access", "تولید محتوا"),
)

# Main Tasks tab (row 1 headers in the customer's sheet)
TASKS_HEADERS = [
    "تسک",
    "پروژه",
    "مسوول تسک",
    "ایجاد کننده",
    "تاریخ ایجاد",
    "ددلاین",
    "اولویت",
    "ماه ",
]

# Personal employee tabs
PERSONAL_HEADERS = [
    "تسک",
    "پروژه",
    "مسوول تسک",
    "ایجاد کننده",
    "تاریخ ایجاد",
    "ددلاین",
    "اولویت",
    "وضعیت",
    "توضیحات",
]

IDEAS_HEADERS = [
    "ایده",
    "ثبت کننده",
    "نقش",
    "تاریخ ثبت",
    "telegram_id",
]

IDEAS_SHEET_NAME = "Ideas"

FILMING_SHEET_NAME = "Meetings"
FILMING_SHEET_ALIASES: tuple[str, ...] = (
    "Meetings",
    "Filming",
    "تصویر برداری",
)
FILMING_HEADERS = [
    "نام پروژه",
    "محل فیلم برداری",
    "روز",
    "ساعت",
    "تاریخ",
    "مسوول",
    "وضعیت",
    "ایجاد کننده",
]
FILMING_PROJECT_HEADER_ALIASES = frozenset({
    "نام پروژه",
    "پروژه",
    "project",
    "Project",
})

CONTENT_SHEET_NAME = "Design"
CONTENT_SHEET_ALIASES: tuple[str, ...] = (
    "Design",
    "Content",
    "دیزاین",
    "تولید محتوا",
)
# Design tab people (column «نام») — matches the sheet roster.
CONTENT_DESIGN_NAMES: tuple[str, ...] = ("علیپور", "مرادی", "بخشی", "بخشنده")
# Backward-compatible alias used by older call sites.
CONTENT_TEAM_COLUMNS = CONTENT_DESIGN_NAMES
CONTENT_TYPE_OPTIONS: tuple[str, ...] = ("پست", "استوری", "پست و استوری")
# User layout: نام | پروژه | پست | استوری | وضعیت | ایجاد کننده
CONTENT_HEADERS = [
    "نام",
    "پروژه",
    "پست",
    "استوری",
    "وضعیت",
    "ایجاد کننده",
]
CONTENT_PROJECT_HEADER_ALIASES = frozenset({"پروژه", "نام پروژه", "project", "Project"})

# Cross-project / general categories (shown first in the bot; auto-added to Projects tab).
GENERAL_PROJECT_CATEGORIES: tuple[str, ...] = (
    "عمومی",
    "آپلودها",
    "کارهای مشترک",
)

PROJECTS_SHEET_HEADER = "پروژه"
PROJECTS_HEADER_ALIASES = frozenset({
    PROJECTS_SHEET_HEADER,
    "project",
    "Project",
    "Projects",
    "نام پروژه",
})

PERSIAN_MONTHS = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

PRIORITIES = ("High", "Medium", "Low")

STATUS_OPEN = {"", "pending", "در انتظار", "⏳ در انتظار"}
STATUS_IN_PROGRESS = {"in_progress", "در حال انجام", "🔄 در حال انجام"}
STATUS_DONE = {"done", "انجام شده", "✅ انجام شده", "انجام شد"}
STATUS_CANCELLED = {
    "cancelled",
    "canceled",
    "لغو شده",
    "لغو شد",
    "❌ لغو شده",
    "تسک لغو شده",
}


@dataclass(frozen=True)
class Personnel:
    """Staff member from the Personnel sheet."""

    telegram_id: int
    name: str
    role: str
    active: bool
    senior_admin: bool = False
    view_all_tasks: bool = False
    filming_access: bool = False
    content_access: bool = False


@dataclass(frozen=True)
class Task:
    """Task row from Tasks or a personal employee sheet."""

    sheet_name: str
    row_index: int
    title: str
    project: str
    assignee_name: str
    created_by: str
    created_at: str
    due_date: str
    priority: str
    status: str
    description: str

    @property
    def id(self) -> str:
        return f"{self.sheet_name}:{self.row_index}"


@dataclass(frozen=True)
class Idea:
    """Idea row from the Ideas sheet."""

    text: str
    created_by: str
    role: str
    created_at: str
    telegram_id: int
    row_index: int


@dataclass(frozen=True)
class FilmingEntry:
    """Row from the تصویر برداری filming schedule tab."""

    row_index: int
    project: str
    location: str
    day: str
    hour: str
    date: str
    assignee_name: str
    status: str
    created_by: str

    @property
    def id(self) -> str:
        # ASCII prefix keeps Telegram callback_data under 64 bytes.
        return f"filming:{self.row_index}"

    @property
    def sheet_name(self) -> str:
        return FILMING_SHEET_NAME


@dataclass(frozen=True)
class ContentEntry:
    """Row from the Design tab (نام | پروژه | پست | استوری | …)."""

    row_index: int
    name: str
    project: str
    post: str
    story: str
    status: str
    created_by: str

    @property
    def id(self) -> str:
        return f"design:{self.row_index}"

    @property
    def sheet_name(self) -> str:
        return CONTENT_SHEET_NAME

    @property
    def assignee_name(self) -> str:
        return self.name

    @property
    def content_type(self) -> str:
        has_post = bool(self.post.strip())
        has_story = bool(self.story.strip())
        if has_post and has_story:
            return "پست و استوری"
        if has_post:
            return "پست"
        if has_story:
            return "استوری"
        return ""


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
        self.ensure_filming_schema()
        self.ensure_content_schema()

    def _get_or_rename_worksheet(
        self,
        preferred_title: str,
        aliases: tuple[str, ...],
    ) -> gspread.Worksheet | None:
        """Return preferred tab; rename a legacy Persian title to English if needed."""
        worksheets = self._all_worksheets()
        if preferred_title in worksheets:
            return worksheets[preferred_title]
        for alias in aliases:
            if alias == preferred_title:
                continue
            worksheet = worksheets.get(alias)
            if worksheet is None:
                continue
            try:
                worksheet.update_title(preferred_title)
                logger.info("Renamed worksheet %r -> %r", alias, preferred_title)
            except Exception:
                logger.exception("Failed renaming worksheet %r -> %r", alias, preferred_title)
                return worksheet
            self.invalidate_worksheet_cache()
            return worksheet
        return None

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

            for _key, persian_header in missing:
                col_index = len(headers) + 1
                ws.update_cell(1, col_index, persian_header)
                headers.append(persian_header)
                added.append(persian_header)

                row_count = max(len(ws.col_values(1)), 1)
                if row_count > 1:
                    defaults = [["FALSE"]] * (row_count - 1)
                    start = gspread.utils.rowcol_to_a1(2, col_index)
                    end = gspread.utils.rowcol_to_a1(row_count, col_index)
                    ws.update(
                        f"{start}:{end}",
                        defaults,
                        value_input_option="USER_ENTERED",
                    )

            if added:
                logger.info("Personnel sheet: added columns %s", added)

        self.ensure_personnel_bool_dropdowns()
        return added

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

    @staticmethod
    def _projects_data_start(col_values: list[str]) -> int:
        """Index in col_values where project names begin (0 = no header row)."""
        if not col_values:
            return 0
        if col_values[0].strip() in PROJECTS_HEADER_ALIASES:
            return 1
        return 0

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

    @staticmethod
    def sort_projects(projects: list[str]) -> list[str]:
        """General/cross-project names first, then the rest alphabetically."""
        general_set = set(GENERAL_PROJECT_CATEGORIES)
        general = [name for name in GENERAL_PROJECT_CATEGORIES if name in projects]
        other = sorted((name for name in projects if name not in general_set), key=str)
        return general + other

    @staticmethod
    def is_general_project(name: str) -> bool:
        return name.strip() in GENERAL_PROJECT_CATEGORIES

    @staticmethod
    def _parse_bool(value: str, *, default: bool = False) -> bool:
        cleaned = value.strip()
        if not cleaned:
            return default
        return cleaned.upper() in {"TRUE", "1", "YES", "بله", "Y"}

    @staticmethod
    def _record_telegram_id(record: dict[str, str]) -> int | None:
        """Resolve telegram id from Personnel row (English or Persian headers)."""
        for key in ("telegram_id", "Telegram ID", "telegram id", "شناسه تلگرام"):
            raw = str(record.get(key, "")).strip()
            if not raw:
                continue
            try:
                tid = int(float(raw))
            except (ValueError, TypeError):
                continue
            if tid > 0:
                return tid
        return None

    @staticmethod
    def _record_is_active(record: dict[str, str]) -> bool:
        """Empty/missing active column counts as active (default TRUE)."""
        raw = str(record.get("active", "")).strip()
        if not raw:
            return True
        return SheetsService._parse_bool(raw, default=True)

    @staticmethod
    def _shamsi_today() -> tuple[str, str]:
        """Return today's Jalali date (YYYY/MM/DD) and the Persian month label."""
        now = jdatetime.datetime.now()
        date_str = f"{now.year:04d}/{now.month:02d}/{now.day:02d}"
        month_str = PERSIAN_MONTHS[now.month - 1] + " "
        return date_str, month_str

    @staticmethod
    def shamsi_date_range(*, before: int = 15, after: int = 15) -> list[tuple[int, str]]:
        """Jalali dates from ``-before`` … ``+after`` relative to today.

        Each item is ``(day_offset, YYYY/MM/DD)``. Offset 0 is today.
        """
        today = jdatetime.date.today()
        result: list[tuple[int, str]] = []
        for offset in range(-before, after + 1):
            day = today + jdatetime.timedelta(days=offset)
            date_str = f"{day.year:04d}/{day.month:02d}/{day.day:02d}"
            result.append((offset, date_str))
        return result

    @staticmethod
    def recent_shamsi_dates(count: int = 30) -> list[tuple[int, str]]:
        """Upcoming Jalali dates from today forward (legacy helper)."""
        return [
            (offset, date_str)
            for offset, date_str in SheetsService.shamsi_date_range(before=0, after=max(0, count - 1))
        ]

    @staticmethod
    def shamsi_date_button_label(day_offset: int, date_str: str) -> str:
        """Human-readable label for a due-date picker button (kept short for large taps)."""
        short = date_str[5:] if len(date_str) >= 10 else date_str
        if day_offset == 0:
            return f"📅 امروز  {short}"
        if day_offset == 1:
            return f"فردا  {short}"
        if day_offset == -1:
            return f"دیروز  {short}"
        today = jdatetime.date.today()
        day = today + jdatetime.timedelta(days=day_offset)
        try:
            day_fa = jdatetime.date(day.year, day.month, day.day, locale=jdatetime.FA_LOCALE)
            weekday = day_fa.strftime("%A")
        except Exception:
            weekday = f"{day_offset:+d}"
        return f"{weekday}  {short}"

    @staticmethod
    def resolve_shamsi_date_offset(
        day_offset: int,
        *,
        before: int = 15,
        after: int = 15,
    ) -> str | None:
        for offset, date_str in SheetsService.shamsi_date_range(before=before, after=after):
            if offset == day_offset:
                return date_str
        return None

    @staticmethod
    def validate_shamsi_date(value: str) -> str | None:
        """Parse and normalize a Jalali date string (YYYY/MM/DD)."""
        clean = value.strip().lstrip("'").replace("-", "/")
        parts = clean.split("/")
        if len(parts) != 3:
            return None
        try:
            year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
            jdatetime.date(year, month, day)
        except (ValueError, TypeError):
            return None
        return f"{year:04d}/{month:02d}/{day:02d}"

    @staticmethod
    def _date_for_sheet(date_str: str) -> str:
        """Force Google Sheets to store Jalali dates as text, not serial numbers.

        Without the leading apostrophe, values like 1405/04/09 are auto-parsed as
        Gregorian dates and show up as broken numbers (e.g. 180697).
        """
        clean = date_str.strip().lstrip("'")
        return f"'{clean}" if clean else ""

    @staticmethod
    def _normalize_status(value: str) -> str:
        raw = value.strip()
        lower = raw.lower()
        if lower in STATUS_DONE or raw in STATUS_DONE:
            return "done"
        if lower in STATUS_CANCELLED or raw in STATUS_CANCELLED:
            return "cancelled"
        if lower in STATUS_IN_PROGRESS or raw in STATUS_IN_PROGRESS:
            return "in_progress"
        return "pending"

    @staticmethod
    def _status_to_sheet(status: str) -> str:
        return {
            "pending": "در انتظار",
            "in_progress": "در حال انجام",
            "done": "انجام شده",
            "cancelled": "لغو شده",
        }.get(status, status)

    @staticmethod
    def _row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
        padded = row + [""] * max(0, len(headers) - len(row))
        return dict(zip(headers, padded[: len(headers)], strict=False))

    @staticmethod
    def _is_blank_task_cell(value: object) -> bool:
        """True when column A has no real task title (empty or formula error)."""
        text = str(value).strip()
        if not text:
            return True
        # #REF!, #VALUE!, … left after insert_row shifts or manual edits
        return text.startswith("#")

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
        try:
            cell = worksheet.acell("A2", value_render_option="FORMULA")
            formula = str(cell.value or "").strip().upper()
        except Exception as exc:
            logger.debug("Could not read A2 formula on %s: %s", worksheet.title, exc)
            return False
        if not formula.startswith("="):
            return False
        return "FILTER" in formula and "TASKS!" in formula

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
        from services.auth import can_access_filming

        if not can_access_filming(personnel):
            return False
        entry = self.get_filming_entry_by_id(entry_id)
        if entry is None:
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
        return names or list(CONTENT_DESIGN_NAMES)

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
        from services.auth import can_access_content

        if not can_access_content(personnel):
            return False
        entry = self.get_content_entry_by_id(entry_id)
        if entry is None:
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

    @staticmethod
    def _role_label(role: str) -> str:
        return {
            "admin": "مدیر",
            "employee": "کارمند",
            "senior_admin": "مدیر ارشد",
        }.get(role, role)

    @classmethod
    def _personnel_from_record(cls, record: dict[str, str], telegram_id: int) -> Personnel:
        """Build Personnel from a sheet row (supports English or Persian column names)."""
        member_role = str(record.get("role", "employee")).strip().lower()
        senior_admin = cls._parse_bool(
            str(record.get("senior_admin", record.get("مدیر ارشد", "FALSE")))
        )
        view_all_tasks = cls._parse_bool(
            str(record.get("view_all_tasks", record.get("مشاهده همه تسک", "FALSE")))
        )
        filming_access = cls._parse_bool(
            str(record.get("filming_access", record.get("تصویر برداری", "FALSE")))
        )
        content_access = cls._parse_bool(
            str(record.get("content_access", record.get("تولید محتوا", "FALSE")))
        )
        if member_role == "senior_admin":
            senior_admin = True
        return Personnel(
            telegram_id=telegram_id,
            name=str(record.get("name", "")).strip(),
            role=member_role,
            active=cls._record_is_active(record),
            senior_admin=senior_admin,
            view_all_tasks=view_all_tasks,
            filming_access=filming_access,
            content_access=content_access,
        )

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
            raw_id = str(record.get("telegram_id", "")).strip()
            if not raw_id:
                continue
            try:
                if int(float(raw_id)) != telegram_id:
                    continue
            except (ValueError, TypeError):
                continue
            if not self._parse_bool(str(record.get("active", "TRUE"))):
                continue
            person = self._personnel_from_record(record, telegram_id)
            if role and person.role != role:
                continue
            matches.append(person)
        if not matches:
            return None
        if role:
            return matches[0]
        for member in matches:
            if member.role == "admin":
                return member
        for member in matches:
            if member.senior_admin:
                return member
        return matches[0]

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
            elif person.role == "admin" and existing.role != "admin":
                seen[tid] = person
            elif person.senior_admin and not existing.senior_admin:
                seen[tid] = person
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
            elif person.role == "admin" and existing.role != "admin":
                seen[tid] = person
            elif person.senior_admin and not existing.senior_admin:
                seen[tid] = person
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
        ]
        main_row_index = self._insert_formatted_row(self._tasks_ws, main_row)

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
        )

    def _parse_task_row(
        self,
        *,
        sheet_name: str,
        headers: list[str],
        row: list[str],
        row_index: int,
    ) -> Task | None:
        record = self._row_to_dict(headers, row)
        title = str(record.get("تسک", "")).strip()
        if not title:
            return None
        assignee = str(record.get("مسوول تسک", "")).strip()
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
        )

    def get_all_tasks(self, status: str | None = None) -> list[Task]:
        """Return tasks across all personnel personal sheets (for senior admins)."""
        tasks: list[Task] = []
        for person in self.get_active_personnel():
            if person.role == "admin":
                continue
            tasks.extend(self.get_tasks_for_assignee(person, status=status))
        return tasks

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

    def _find_task_by_id(self, task_id: str) -> Task | None:
        """Resolve a task id (sheet:row) without filtering by assignee."""
        try:
            sheet_name, row_str = task_id.split(":", 1)
            row_index = int(row_str)
        except ValueError:
            return None

        if sheet_name == "Tasks":
            worksheet = self._tasks_ws
            headers = TASKS_HEADERS
        else:
            worksheet = self._personal_worksheet(sheet_name)
            headers = PERSONAL_HEADERS
        if worksheet is None:
            return None

        row_values = worksheet.row_values(row_index)
        if not row_values:
            return None
        actual_headers = worksheet.row_values(1)
        return self._parse_task_row(
            sheet_name=sheet_name,
            headers=actual_headers if actual_headers else headers,
            row=row_values,
            row_index=row_index,
        )

    def get_task_by_id(self, task_id: str, personnel: Personnel) -> Task | None:
        from services.auth import can_view_all_tasks

        if can_view_all_tasks(personnel):
            task = self._find_task_by_id(task_id)
            if task is not None:
                return task

        for task in self.get_tasks_for_assignee(personnel, status=None):
            if task.id == task_id:
                return task
        for task in self.get_tasks_for_assignee(personnel, status="done"):
            if task.id == task_id:
                return task
        for task in self.get_tasks_for_assignee(personnel, status="cancelled"):
            if task.id == task_id:
                return task
        return None

    def update_task_status(self, task_id: str, personnel: Personnel, status: str) -> bool:
        from services.auth import is_admin

        task = self.get_task_by_id(task_id, personnel)
        if task is None:
            return False
        # Only the assignee (or full admin) may change task status.
        if task.assignee_name != personnel.name and not is_admin(personnel):
            return False

        sheet_value = self._status_to_sheet(status)
        personal_ws = self._personal_worksheet(task.assignee_name)
        if personal_ws is not None:
            headers = personal_ws.row_values(1)
            try:
                status_col = headers.index("وضعیت") + 1
            except ValueError:
                return False
            # Only touch وضعیت — FILTER mirror tabs must not overwrite A:G spill.
            personal_ws.update_cell(task.row_index, status_col, sheet_value)
            return True

        return False

    @staticmethod
    def _parse_due_as_jalali(value: str) -> jdatetime.date | None:
        """Parse a sheet due-date cell into a Jalali date (or None)."""
        normalized = SheetsService.validate_shamsi_date(value)
        if not normalized:
            return None
        year, month, day = (int(p) for p in normalized.split("/"))
        return jdatetime.date(year, month, day)

    @staticmethod
    def _task_match_key(title: str, assignee: str, due_date: str) -> str:
        due = SheetsService.validate_shamsi_date(due_date) or due_date.strip().lstrip("'")
        return f"{assignee.strip().lower()}|{title.strip().lower()}|{due}"

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

    def sync_overdue_row_colors(self) -> dict[str, int]:
        """Paint overdue *open* rows red on Tasks (+ legacy personal); clear others.

        FILTER personal tabs are never written (spill ranges). Returns counts.
        """
        overdue_color = {"red": 0.96, "green": 0.78, "blue": 0.78}
        overdue_open = self.list_overdue_open_tasks()
        overdue_keys = {
            self._task_match_key(t.title, t.assignee_name, t.due_date) for t in overdue_open
        }
        requests: list[dict] = []
        painted = 0
        cleared = 0

        def _process_worksheet(
            worksheet: gspread.Worksheet,
            headers: list[str],
            *,
            allow_write: bool,
        ) -> None:
            nonlocal painted, cleared
            if not allow_write:
                return
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                return
            actual_headers = all_values[0] or headers
            col_count = max(len(actual_headers), len(headers), 8)
            for index, row in enumerate(all_values[1:], start=2):
                task = self._parse_task_row(
                    sheet_name=worksheet.title,
                    headers=actual_headers,
                    row=row,
                    row_index=index,
                )
                if task is None:
                    continue
                is_overdue = (
                    self._task_match_key(task.title, task.assignee_name, task.due_date)
                    in overdue_keys
                )
                color = overdue_color if is_overdue else None
                requests.append(
                    self._row_color_request(
                        sheet_id=worksheet.id,
                        row_index=index,
                        col_count=col_count,
                        color=color,
                    )
                )
                if is_overdue:
                    painted += 1
                else:
                    cleared += 1

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

        chunk_size = 40
        for start in range(0, len(requests), chunk_size):
            chunk = requests[start : start + chunk_size]
            try:
                self._spreadsheet.batch_update({"requests": chunk})
            except Exception as exc:
                logger.warning("Overdue color batch failed (%d requests): %s", len(chunk), exc)

        return {
            "painted": painted,
            "cleared": cleared,
            "requests": len(requests),
            "overdue_open": len(overdue_open),
        }

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
