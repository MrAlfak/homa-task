"""Sheet layout constants, dataclasses, and pure helpers (no Google I/O)."""

from __future__ import annotations

from dataclasses import dataclass, replace
import datetime

import jdatetime

TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))


def tehran_now() -> jdatetime.datetime:
    """Current Jalali datetime strictly pinned to Iran (+03:30) timezone."""
    return jdatetime.datetime.now(TEHRAN_TZ)


def tehran_today() -> jdatetime.date:
    """Current Jalali date strictly pinned to Iran (+03:30) timezone."""
    return tehran_now().date()


def today_jalali_str() -> str:
    """Current Jalali date formatted as YYYY/MM/DD."""
    today = tehran_today()
    return f"{today.year:04d}/{today.month:02d}/{today.day:02d}"


PERSONNEL_CACHE_TTL_SEC = 45.0
PROJECTS_CACHE_TTL_SEC = 45.0
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
    "senior_admin",
    "view_all_tasks",
]

PERSONNEL_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("senior_admin", "مدیر ارشد"),
    ("view_all_tasks", "مشاهده همه تسک"),
    ("filming_access", "تصویر برداری"),
    ("content_access", "تولید محتوا"),
    ("mobile", "موبایل"),
    ("sms_enabled", "ارسال پیامک"),
    ("telegram_notify", "ارسال تلگرام"),
    ("reports_access", "گزارش مدیر"),
    ("report_status", "گزارش وضعیت"),
    ("report_people", "گزارش نفرات"),
    ("report_project", "گزارش پروژه"),
    ("report_month", "گزارش ماه"),
    ("report_deadline", "گزارش ددلاین"),
    ("report_weekly", "گزارش هفتگی"),
)

PERSONNEL_BOOL_HEADER_ALIASES: tuple[tuple[str, ...], ...] = (
    ("active", "فعال"),
    ("senior_admin", "مدیر ارشد"),
    ("view_all_tasks", "مشاهده همه تسک"),
    ("filming_access", "تصویر برداری"),
    ("content_access", "تولید محتوا"),
    ("sms_enabled", "ارسال پیامک"),
    ("telegram_notify", "ارسال تلگرام"),
    ("reports_access", "گزارش مدیر"),
    ("report_status", "گزارش وضعیت"),
    ("report_people", "گزارش نفرات"),
    ("report_project", "گزارش پروژه"),
    ("report_month", "گزارش ماه"),
    ("report_deadline", "گزارش ددلاین"),
    ("report_weekly", "گزارش هفتگی"),
)

PERSONNEL_BOOL_KEYS = frozenset(
    alias.strip().lower()
    for aliases in PERSONNEL_BOOL_HEADER_ALIASES
    for alias in aliases
    if alias.strip()
)

PERSONNEL_MOBILE_KEYS = (
    "موبایل",
    "mobile",
    "phone",
    "شماره موبایل",
    "شماره",
)
PERSONNEL_MOBILE_HEADER_ALIASES = (
    "موبایل",
    "mobile",
    "phone",
    "شماره موبایل",
)
PERSONNEL_SMS_KEYS = ("ارسال پیامک", "sms_enabled", "sms")
PERSONNEL_TELEGRAM_NOTIFY_KEYS = (
    "ارسال تلگرام",
    "telegram_notify",
    "telegram",
    "پیام تلگرام",
)
PERSONNEL_REPORTS_ACCESS_KEYS = ("گزارش مدیر", "reports_access")
PERSONNEL_REPORT_STATUS_KEYS = ("گزارش وضعیت", "report_status")
PERSONNEL_REPORT_PEOPLE_KEYS = ("گزارش نفرات", "report_people")
PERSONNEL_REPORT_PROJECT_KEYS = ("گزارش پروژه", "report_project")
PERSONNEL_REPORT_MONTH_KEYS = ("گزارش ماه", "report_month")
PERSONNEL_REPORT_DEADLINE_KEYS = ("گزارش ددلاین", "report_deadline")
PERSONNEL_REPORT_WEEKLY_KEYS = ("گزارش هفتگی", "report_weekly")
REPORT_KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("status", "📊 وضعیت کل"),
    ("people", "👤 تسک باز هر نفر"),
    ("project", "📁 به تفکیک پروژه"),
    ("deadline", "⏰ ددلاین و عقب‌افتاده"),
    ("month", "📅 این ماه / ماه قبل"),
    ("summary", "🗂 خلاصه هفتگی"),
)

DROPDOWN_RTL_HEADERS: frozenset[str] = frozenset(
    {
        "وضعیت",
        "اولویت",
        "پروژه",
        "نام پروژه",
        "فعال",
        "تکرارشوندگی",
        "پست",
        "استوری",
        "نقش",
        "مسوول تسک",
        "مسئول تسک",
        *{alias for group in PERSONNEL_BOOL_HEADER_ALIASES for alias in group},
    }
)

PERSONNEL_NAME_KEYS = ("name", "نام", "اسم", "Name")
PERSONNEL_ROLE_KEYS = ("role", "نقش", "Role")
PERSONNEL_TELEGRAM_ID_KEYS = (
    "telegram_id",
    "Telegram ID",
    "telegram id",
    "شناسه تلگرام",
)

TASKS_HEADERS = [
    "تسک",
    "پروژه",
    "مسوول تسک",
    "ایجاد کننده",
    "تاریخ ایجاد",
    "ددلاین",
    "اولویت",
    "ماه ",
    "وضعیت",
]

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

STATUS_HEADER = "وضعیت"

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
CONTENT_DESIGN_NAMES: tuple[str, ...] = ("علیپور", "مرادی", "بخشی", "بخشنده")
CONTENT_TEAM_COLUMNS = CONTENT_DESIGN_NAMES
CONTENT_TYPE_OPTIONS: tuple[str, ...] = ("پست", "استوری", "پست و استوری")
CONTENT_HEADERS = [
    "تاریخ",
    "نام",
    "پروژه",
    "پست",
    "استوری",
    "تعداد پست",
    "تعداد استوری",
    "وضعیت",
    "ایجاد کننده",
]
CONTENT_PROJECT_HEADER_ALIASES = frozenset({"پروژه", "نام پروژه", "project", "Project"})

CONTENT_REPORT_SHEET_NAME = "Content_Report"
CONTENT_REPORT_SHEET_ALIASES: tuple[str, ...] = (
    "Content_Report",
    "Content Report",
    "گزارش محتوا",
    "تجمیع محتوا",
    "Content Summary",
)


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
STATUS_IN_PROGRESS = {
    "in_progress",
    "در حال انجام",
    "درحال انجام",
    "در حال انجامه",
    "درحال انجامه",
    "🔄 در حال انجام",
}
STATUS_DONE = {
    "done",
    "انجام شده",
    "انجام شد",
    "تمام شده",
    "تمام شد",
    "✅ انجام شده",
    "✅ انجام شد",
}
STATUS_CANCELLED = {
    "cancelled",
    "canceled",
    "لغو شده",
    "لغو شد",
    "❌ لغو شده",
    "تسک لغو شده",
}

TASKS_PAGE_SIZE = 20
PROJECTS_PAGE_SIZE = 20

SMS_SHEET_NAME = "SMS"
SMS_LOG_SHEET_NAME = "SMS_Log"
SMS_SETTINGS_CACHE_TTL_SEC = 45.0
SMS_SETTINGS_HEADERS = ["کلید", "مقدار", "توضیح"]
SMS_LOG_HEADERS = [
    "تاریخ",
    "نام",
    "موبایل",
    "نوع",
    "متن",
    "sendID",
    "وضعیت",
    "توضیح",
]
SMS_SETTINGS_DEFAULT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("فعال", "FALSE", "تا وقتی FALSE است هیچ پیامکی ارسال نمی‌شود"),
    ("شماره فرستنده", "9998882753", "شماره خط پنل پیامک (از)"),
    ("نوع ارسال", "1", "1=پیام کوتاه  2=صوتی  3=واتساپ  4=بله  5=آی‌گپ"),
    ("تلاش مجدد", "2", "اگر ارسال خطا داد، چند بار تکرار شود (۰ تا ۱۰)"),
    ("پیامک هنگام ثبت تسک", "TRUE", "بعد از ثبت تسک / تصویربرداری / دیزاین برای مسئول پیامک برود"),
    ("پیامک تسک عقب‌افتاده", "TRUE", "یادآوری روزانه تسک‌های عقب‌افتاده"),
    ("پیامک اطلاعیه همگانی", "FALSE", "همراه اعلان تلگرام، پیامک کوتاه هم برود"),
    ("پترن تسک جدید", "", "کد الگو از پنل. اگر خالی باشد متن آزاد ارسال می‌شود"),
    ("پترن عقب‌افتاده", "", "کد الگوی یادآوری ددلاین"),
    ("پترن اطلاعیه", "", "کد الگوی اطلاعیه همگانی"),
    ("قالب شماره", "9xxxxxxxxx", "در ستون موبایل پرسنل: بدون صفر و بدون +۹۸ مثل 9120000000"),
    ("نکته کلید اتصال", "فقط در سرور", "API Key را در شیت نگذارید؛ باید SMS_API_KEY در env سرور باشد"),
    ("نکته آی‌پی", "whitelist", "آی‌پی خروجی سرور را در پنل مجاز کنید"),
)

TEMPLATE_SHEET_NAME = "Templates"
TEMPLATE_SHEET_ALIASES: tuple[str, ...] = (
    "Templates",
    "Template",
    "قالب",
)
EDITING_SHEET_NAME = "Editing"
EDITING_SHEET_ALIASES: tuple[str, ...] = (
    "Editing",
    "Tadvin",
    "تدوین",
)
SYSTEM_TAB_ORDER: tuple[str, ...] = (
    "Projects",
    "Tasks",
    "Personnel",
    "Templates",
    "SMS",
    "SMS_Log",
    "Meetings",
    "Design",
    "Content_Report",
    "Ideas",
    "Ref",
    "Editing",
)
TEMPLATE_HEADERS = [
    "فعال",
    "تسک",
    "پروژه",
    "مسوول تسک",
    "اولویت",
    "تکرارشوندگی",
    "روز مبنا",
    "مهلت (روز)",
    "تاریخ شروع",
    "آخرین اجرا",
    "اجرای بعدی",
]
TEMPLATE_RECURRENCE_VALUES = (
    "روزانه",
    "هفتگی",
    "ماهانه",
    "سه ماهه",
    "شش ماهه",
    "سالانه",
)
TEMPLATE_RECURRENCE_MAP = {
    "روزانه": "daily",
    "daily": "daily",
    "هفتگی": "weekly",
    "weekly": "weekly",
    "ماهانه": "monthly",
    "monthly": "monthly",
    "سه ماهه": "quarterly",
    "quarterly": "quarterly",
    "شش ماهه": "semiannual",
    "semiannual": "semiannual",
    "سالانه": "yearly",
    "yearly": "yearly",
}
TEMPLATE_WEEKDAYS = (
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنجشنبه",
    "جمعه",
)
TEMPLATE_WEEKDAY_INDEX = {
    "شنبه": 0,
    "یکشنبه": 1,
    "دوشنبه": 2,
    "سه‌شنبه": 3,
    "سه شنبه": 3,
    "سهشنبه": 3,
    "چهارشنبه": 4,
    "پنجشنبه": 5,
    "پنج‌شنبه": 5,
    "جمعه": 6,
}
TEMPLATE_CREATED_BY = "Templates"
TEMPLATE_TEST_TITLE = "تست قالب ماهانه"
TEMPLATE_TEST_ROW: tuple[str, ...] = (
    "FALSE",
    TEMPLATE_TEST_TITLE,
    "عمومی",
    "Alfak, Dehghanian",
    "Low",
    "ماهانه",
    "1",
    "5",
    "1405/07/01",
    "",
    "",
)

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


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
    mobile: str = ""
    sms_enabled: bool = False
    telegram_notify: bool = False
    reports_access: bool = False
    report_status: bool = False
    report_people: bool = False
    report_project: bool = False
    report_month: bool = False
    report_deadline: bool = False
    report_weekly: bool = False


@dataclass(frozen=True)
class SmsSettings:
    """Runtime flags from the SMS settings tab."""

    enabled: bool = False
    sender: str = "auto"
    send_type: int = 1
    try_send: int = 2
    on_new_task: bool = True
    on_overdue: bool = True
    on_announce: bool = False
    pattern_new_task: str = ""
    pattern_overdue: str = ""
    pattern_announce: str = ""


def _settings_map(rows: list[dict[str, str]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for row in rows:
        key = str(row.get("کلید", row.get("key", ""))).strip()
        if not key:
            continue
        mapped[key] = str(row.get("مقدار", row.get("value", ""))).strip()
    return mapped


def _settings_int(raw: str, default: int, *, minimum: int, maximum: int) -> int:
    digits = str(raw or "").strip().translate(_PERSIAN_DIGITS)
    try:
        value = int(digits)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def sms_settings_from_records(records: list[dict[str, str]]) -> SmsSettings:
    values = _settings_map(records)
    sender = values.get("شماره فرستنده", "auto").strip() or "auto"
    return SmsSettings(
        enabled=parse_bool(values.get("فعال", "FALSE")),
        sender=sender,
        send_type=_settings_int(values.get("نوع ارسال", "1"), 1, minimum=1, maximum=5),
        try_send=_settings_int(values.get("تلاش مجدد", "2"), 2, minimum=0, maximum=10),
        on_new_task=parse_bool(values.get("پیامک هنگام ثبت تسک", "TRUE"), default=True),
        on_overdue=parse_bool(values.get("پیامک تسک عقب‌افتاده", "TRUE"), default=True),
        on_announce=parse_bool(values.get("پیامک اطلاعیه همگانی", "FALSE")),
        pattern_new_task=values.get("پترن تسک جدید", "").strip(),
        pattern_overdue=values.get("پترن عقب‌افتاده", "").strip(),
        pattern_announce=values.get("پترن اطلاعیه", "").strip(),
    )


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
    sheet_gid: int = 0

    @property
    def id(self) -> str:
        return encode_task_id(self.sheet_gid, self.row_index, self.sheet_name)


@dataclass(frozen=True)
class TemplateEntry:
    """One recurring task rule from the قالب tab."""

    row_index: int
    enabled: bool
    title: str
    project: str
    assignees_raw: str
    priority: str
    recurrence: str
    day_base: str
    lead_days: int
    start_date: str
    last_run: str
    next_run: str

    @property
    def assignee_names(self) -> list[str]:
        return split_assignee_names(self.assignees_raw)


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
        return f"filming:{self.row_index}"

    @property
    def sheet_name(self) -> str:
        return FILMING_SHEET_NAME


@dataclass(frozen=True)
class ContentEntry:
    """Row from the Design tab (تاریخ | نام | پروژه | پست | استوری | تعداد پست | تعداد استوری | وضعیت | ایجاد کننده)."""

    row_index: int
    name: str
    project: str
    post: str
    story: str
    status: str
    created_by: str
    date: str = ""
    post_count: int = 0
    story_count: int = 0

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
    def effective_post_count(self) -> int:
        if self.post_count > 0:
            return self.post_count
        return 1 if self.post.strip() else 0

    @property
    def effective_story_count(self) -> int:
        if self.story_count > 0:
            return self.story_count
        return 1 if self.story.strip() else 0

    @property
    def content_type(self) -> str:
        has_post = bool(self.post.strip()) or self.post_count > 0
        has_story = bool(self.story.strip()) or self.story_count > 0
        if has_post and has_story:
            return "پست و استوری"
        if has_post:
            return "پست"
        if has_story:
            return "استوری"
        return ""


@dataclass(frozen=True)
class ContentSummaryItem:
    """Aggregated stats for an admin and project within a date range."""

    name: str
    project: str
    post_count: int
    story_count: int
    total_count: int


def get_jalali_period_dates(
    period_type: str,
    ref_date: jdatetime.date | None = None,
) -> tuple[str, str, str]:
    """Calculate (from_date, to_date, period_label) for Jalali periods.

    period_type: '1_to_1' (1st of month to ref_date) or '15_to_15' (15th to ref_date).
    """
    if ref_date is None:
        ref_date = tehran_today()

    y, m, d = ref_date.year, ref_date.month, ref_date.day

    if period_type == "15_to_15":
        if d >= 15:
            from_d = jdatetime.date(y, m, 15)
        else:
            if m > 1:
                from_d = jdatetime.date(y, m - 1, 15)
            else:
                from_d = jdatetime.date(y - 1, 12, 15)
        to_d = ref_date
        month_label = PERSIAN_MONTHS[from_d.month - 1]
        title = f"دوره ۱۵ {month_label} تا {to_d.day:02d} {PERSIAN_MONTHS[to_d.month - 1]}"
    else:
        # Default '1_to_1'
        from_d = jdatetime.date(y, m, 1)
        to_d = ref_date
        month_label = PERSIAN_MONTHS[from_d.month - 1]
        title = f"دوره یکم تا {to_d.day:02d} {month_label}"

    from_str = f"{from_d.year:04d}/{from_d.month:02d}/{from_d.day:02d}"
    to_str = f"{to_d.year:04d}/{to_d.month:02d}/{to_d.day:02d}"
    return from_str, to_str, title



def encode_task_id(sheet_gid: int, row_index: int, sheet_name: str = "") -> str:
    """ASCII callback id. Prefer worksheet gid so Persian tab names stay off the wire."""
    if sheet_gid:
        return f"t:{sheet_gid}:{row_index}"
    return f"{sheet_name}:{row_index}"


def parse_task_id(task_id: str) -> tuple[int | None, str | None, int] | None:
    """Return (sheet_gid, legacy_sheet_name, row_index) or None."""
    raw = (task_id or "").strip()
    if not raw:
        return None
    if raw.startswith("t:"):
        parts = raw.split(":")
        if len(parts) != 3:
            return None
        try:
            return int(parts[1]), None, int(parts[2])
        except ValueError:
            return None
    sheet_name, sep, row_str = raw.rpartition(":")
    if not sep or not sheet_name:
        return None
    try:
        return None, sheet_name, int(row_str)
    except ValueError:
        return None


def normalize_mobile(value: str) -> str:
    """Return Iranian mobile as 10 digits starting with 9, or empty if invalid."""
    raw = str(value or "").strip().translate(_PERSIAN_DIGITS)
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) >= 12:
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits.lstrip("0")
        if not digits.startswith("9"):
            return ""
    if len(digits) == 10 and digits.startswith("9"):
        return digits
    return ""


def is_personnel_bool_header(key: str, header: str) -> bool:
    return key.strip().lower() in PERSONNEL_BOOL_KEYS or header.strip().lower() in PERSONNEL_BOOL_KEYS


def parse_bool(value: str, *, default: bool = False) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return default
    return cleaned.upper() in {"TRUE", "1", "YES", "بله", "Y"}


def record_value(record: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        raw = str(record.get(key, "")).strip()
        if raw:
            return raw
    return ""


def record_telegram_id(record: dict[str, str]) -> int | None:
    for key in PERSONNEL_TELEGRAM_ID_KEYS:
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


def record_is_active(record: dict[str, str]) -> bool:
    raw = str(record.get("active", record.get("فعال", ""))).strip()
    if not raw:
        return True
    return parse_bool(raw, default=True)


def personnel_from_record(record: dict[str, str], telegram_id: int) -> Personnel:
    member_role = record_value(record, PERSONNEL_ROLE_KEYS).lower() or "employee"
    senior_admin = parse_bool(
        str(record.get("senior_admin", record.get("مدیر ارشد", "FALSE")))
    )
    view_all_tasks = parse_bool(
        str(record.get("view_all_tasks", record.get("مشاهده همه تسک", "FALSE")))
    )
    filming_access = parse_bool(
        str(record.get("filming_access", record.get("تصویر برداری", "FALSE")))
    )
    content_access = parse_bool(
        str(record.get("content_access", record.get("تولید محتوا", "FALSE")))
    )
    sms_enabled = parse_bool(record_value(record, PERSONNEL_SMS_KEYS))
    telegram_notify = parse_bool(record_value(record, PERSONNEL_TELEGRAM_NOTIFY_KEYS))
    reports_access = parse_bool(record_value(record, PERSONNEL_REPORTS_ACCESS_KEYS))
    report_status = parse_bool(record_value(record, PERSONNEL_REPORT_STATUS_KEYS))
    report_people = parse_bool(record_value(record, PERSONNEL_REPORT_PEOPLE_KEYS))
    report_project = parse_bool(record_value(record, PERSONNEL_REPORT_PROJECT_KEYS))
    report_month = parse_bool(record_value(record, PERSONNEL_REPORT_MONTH_KEYS))
    report_deadline = parse_bool(record_value(record, PERSONNEL_REPORT_DEADLINE_KEYS))
    report_weekly = parse_bool(record_value(record, PERSONNEL_REPORT_WEEKLY_KEYS))
    if member_role == "senior_admin":
        senior_admin = True
    return Personnel(
        telegram_id=telegram_id,
        name=record_value(record, PERSONNEL_NAME_KEYS),
        role=member_role,
        active=record_is_active(record),
        senior_admin=senior_admin,
        view_all_tasks=view_all_tasks,
        filming_access=filming_access,
        content_access=content_access,
        mobile=normalize_mobile(record_value(record, PERSONNEL_MOBILE_KEYS)),
        sms_enabled=sms_enabled,
        telegram_notify=telegram_notify,
        reports_access=reports_access,
        report_status=report_status,
        report_people=report_people,
        report_project=report_project,
        report_month=report_month,
        report_deadline=report_deadline,
        report_weekly=report_weekly,
    )


def coalesce_personnel(existing: Personnel, incoming: Personnel) -> Personnel:
    """Merge duplicate Personnel rows so mobile/SMS flags are not lost."""
    preferred = existing
    if incoming.role == "admin" and existing.role != "admin":
        preferred = incoming
    elif incoming.senior_admin and not existing.senior_admin and existing.role != "admin":
        preferred = incoming
    other = incoming if preferred is existing else existing
    return Personnel(
        telegram_id=preferred.telegram_id,
        name=preferred.name or other.name,
        role=preferred.role,
        active=preferred.active or other.active,
        senior_admin=preferred.senior_admin or other.senior_admin,
        view_all_tasks=preferred.view_all_tasks or other.view_all_tasks,
        filming_access=preferred.filming_access or other.filming_access,
        content_access=preferred.content_access or other.content_access,
        mobile=preferred.mobile or other.mobile,
        sms_enabled=preferred.sms_enabled or other.sms_enabled,
        telegram_notify=preferred.telegram_notify or other.telegram_notify,
        reports_access=preferred.reports_access or other.reports_access,
        report_status=preferred.report_status or other.report_status,
        report_people=preferred.report_people or other.report_people,
        report_project=preferred.report_project or other.report_project,
        report_month=preferred.report_month or other.report_month,
        report_deadline=preferred.report_deadline or other.report_deadline,
        report_weekly=preferred.report_weekly or other.report_weekly,
    )


def role_label(role: str) -> str:
    return {
        "admin": "مدیر",
        "employee": "کارمند",
        "senior_admin": "مدیر ارشد",
    }.get(role, role)


def normalize_status(value: str) -> str:
    raw = " ".join(str(value).strip().split())
    lower = raw.lower()
    if lower in STATUS_DONE or raw in STATUS_DONE:
        return "done"
    if lower in STATUS_CANCELLED or raw in STATUS_CANCELLED:
        return "cancelled"
    if lower in STATUS_IN_PROGRESS or raw in STATUS_IN_PROGRESS:
        return "in_progress"
    return "pending"


STATUS_SHEET_VALUES = ("در انتظار", "در حال انجام", "انجام شده", "لغو شده")


def status_to_sheet(status: str) -> str:
    return {
        "pending": "در انتظار",
        "in_progress": "در حال انجام",
        "done": "انجام شده",
        "cancelled": "لغو شده",
    }.get(status, status)


def row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * max(0, len(headers) - len(row))
    return dict(zip(headers, padded[: len(headers)]))


def is_blank_task_cell(value: object) -> bool:
    text = str(value).strip()
    if not text:
        return True
    return text.startswith("#")


def projects_data_start(col_values: list[str]) -> int:
    if not col_values:
        return 0
    if col_values[0].strip() in PROJECTS_HEADER_ALIASES:
        return 1
    return 0


def sort_projects(projects: list[str]) -> list[str]:
    general_set = set(GENERAL_PROJECT_CATEGORIES)
    general = [name for name in GENERAL_PROJECT_CATEGORIES if name in projects]
    other = sorted((name for name in projects if name not in general_set), key=str)
    return general + other


def is_general_project(name: str) -> bool:
    return name.strip() in GENERAL_PROJECT_CATEGORIES


def shamsi_today() -> tuple[str, str]:
    now = tehran_now()
    date_str = f"{now.year:04d}/{now.month:02d}/{now.day:02d}"
    month_str = PERSIAN_MONTHS[now.month - 1] + " "
    return date_str, month_str


def shamsi_date_range(*, before: int = 0, after: int = 6) -> list[tuple[int, str]]:
    today = tehran_today()
    result: list[tuple[int, str]] = []
    for offset in range(-before, after + 1):
        day = today + jdatetime.timedelta(days=offset)
        date_str = f"{day.year:04d}/{day.month:02d}/{day.day:02d}"
        result.append((offset, date_str))
    return result


def recent_shamsi_dates(count: int = 30) -> list[tuple[int, str]]:
    return [
        (offset, date_str)
        for offset, date_str in shamsi_date_range(before=0, after=max(0, count - 1))
    ]


def shamsi_date_button_label(day_offset: int, date_str: str) -> str:
    short = date_str[5:] if len(date_str) >= 10 else date_str
    if day_offset == 0:
        return f"📅 امروز  {short}"
    if day_offset == 1:
        return f"فردا  {short}"
    if day_offset == -1:
        return f"دیروز  {short}"
    today = tehran_today()
    day = today + jdatetime.timedelta(days=day_offset)
    try:
        day_fa = jdatetime.date(day.year, day.month, day.day, locale=jdatetime.FA_LOCALE)
        weekday = day_fa.strftime("%A")
    except Exception:
        weekday = f"{day_offset:+d}"
    return f"{weekday}  {short}"


def resolve_shamsi_date_offset(
    day_offset: int,
    *,
    before: int = 0,
    after: int = 6,
) -> str | None:
    for offset, date_str in shamsi_date_range(before=before, after=after):
        if offset == day_offset:
            return date_str
    return None


def validate_shamsi_date(value: str) -> str | None:
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


def date_for_sheet(date_str: str) -> str:
    clean = date_str.strip().lstrip("'")
    return f"'{clean}" if clean else ""


def normalize_sheet_title(title: str) -> str:
    """Compare tab names ignoring tatweel and extra spaces."""
    cleaned = "".join(ch for ch in (title or "") if ch != "\u0640")
    return " ".join(cleaned.split())


def parse_due_as_jalali(value: str) -> jdatetime.date | None:
    normalized = validate_shamsi_date(value)
    if not normalized:
        return None
    year, month, day = (int(p) for p in normalized.split("/"))
    return jdatetime.date(year, month, day)


def jalali_to_str(day: jdatetime.date) -> str:
    return f"{day.year:04d}/{day.month:02d}/{day.day:02d}"


def split_assignee_names(raw: str) -> list[str]:
    text = (raw or "").replace("،", ",").replace("؛", ",").replace(";", ",")
    names: list[str] = []
    seen: set[str] = set()
    for chunk in text.split(","):
        name = chunk.strip()
        if name.startswith("و "):
            name = name[2:].strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def parse_recurrence(value: str) -> str | None:
    return TEMPLATE_RECURRENCE_MAP.get(value.strip().lower()) or TEMPLATE_RECURRENCE_MAP.get(
        value.strip()
    )


def parse_day_number(value: str) -> int | None:
    digits = (value or "").strip().translate(_PERSIAN_DIGITS)
    if not digits:
        return None
    try:
        number = int(digits)
    except ValueError:
        return None
    if 1 <= number <= 31:
        return number
    return None


def weekday_index(value: str) -> int | None:
    key = (value or "").strip().replace("ي", "ی")
    return TEMPLATE_WEEKDAY_INDEX.get(key)


def add_jalali_months(day: jdatetime.date, months: int) -> jdatetime.date:
    month0 = day.month - 1 + months
    year = day.year + month0 // 12
    month = month0 % 12 + 1
    for candidate in range(min(day.day, 31), 0, -1):
        try:
            return jdatetime.date(year, month, candidate)
        except ValueError:
            continue
    return jdatetime.date(year, month, 1)


def clamp_jalali_day(year: int, month: int, day: int) -> jdatetime.date:
    for candidate in range(min(max(day, 1), 31), 0, -1):
        try:
            return jdatetime.date(year, month, candidate)
        except ValueError:
            continue
    return jdatetime.date(year, month, 1)


def due_date_from_lead(today: jdatetime.date, lead_days: int) -> str:
    due = today + jdatetime.timedelta(days=max(0, lead_days))
    return jalali_to_str(due)


def next_run_on_or_after(
    *,
    recurrence: str,
    day_base: str,
    start: jdatetime.date | None,
    on_or_after: jdatetime.date,
) -> jdatetime.date | None:
    kind = parse_recurrence(recurrence)
    if kind is None:
        return None
    if kind == "daily":
        return on_or_after
    if kind == "weekly":
        want = weekday_index(day_base)
        if want is None:
            want = 0
        cursor = on_or_after
        for _ in range(8):
            if cursor.weekday() == want:
                return cursor
            cursor = cursor + jdatetime.timedelta(days=1)
        return None
    if kind == "monthly":
        target_day = parse_day_number(day_base) or 1
        year, month = on_or_after.year, on_or_after.month
        for _ in range(16):
            candidate = clamp_jalali_day(year, month, target_day)
            if candidate >= on_or_after:
                return candidate
            month += 1
            if month > 12:
                month = 1
                year += 1
        return None
    step = {"quarterly": 3, "semiannual": 6, "yearly": 12}[kind]
    cursor = start or on_or_after
    if cursor < on_or_after:
        guard = 0
        while cursor < on_or_after and guard < 48:
            cursor = add_jalali_months(cursor, step)
            guard += 1
    return cursor


def template_from_record(record: dict[str, str], row_index: int) -> TemplateEntry | None:
    title = str(record.get("تسک", "")).strip()
    if not title:
        return None
    lead_raw = str(record.get("مهلت (روز)", "")).strip().translate(_PERSIAN_DIGITS)
    try:
        lead_days = int(lead_raw) if lead_raw else 0
    except ValueError:
        lead_days = 0
    priority = str(record.get("اولویت", "")).strip() or "Medium"
    if priority not in PRIORITIES:
        priority = "Medium"
    return TemplateEntry(
        row_index=row_index,
        enabled=parse_bool(str(record.get("فعال", ""))),
        title=title,
        project=str(record.get("پروژه", "")).strip(),
        assignees_raw=str(record.get("مسوول تسک", "")).strip(),
        priority=priority,
        recurrence=str(record.get("تکرارشوندگی", "")).strip(),
        day_base=str(record.get("روز مبنا", "")).strip(),
        lead_days=max(0, lead_days),
        start_date=str(record.get("تاریخ شروع", "")).strip(),
        last_run=str(record.get("آخرین اجرا", "")).strip(),
        next_run=str(record.get("اجرای بعدی", "")).strip(),
    )


def template_is_due(entry: TemplateEntry, today: jdatetime.date) -> bool:
    if not entry.enabled or not entry.title or not entry.assignee_names:
        return False
    today_str = jalali_to_str(today)
    last_run = validate_shamsi_date(entry.last_run) or ""
    if last_run == today_str:
        return False
    next_run = parse_due_as_jalali(entry.next_run)
    if next_run is None:
        start = parse_due_as_jalali(entry.start_date)
        next_run = next_run_on_or_after(
            recurrence=entry.recurrence,
            day_base=entry.day_base,
            start=start,
            on_or_after=today,
        )
    if next_run is None:
        return False
    return next_run <= today


def task_match_key(title: str, assignee: str, due_date: str) -> str:
    due = validate_shamsi_date(due_date) or due_date.strip().lstrip("'")
    return f"{assignee.strip().lower()}|{title.strip().lower()}|{due}"


def task_soft_key(title: str, assignee: str) -> str:
    return f"{assignee.strip().lower()}|{title.strip().lower()}"


def overlay_status_from_personal(main_tasks: list[Task], personal_tasks: list[Task]) -> list[Task]:
    """Copy وضعیت from personal tabs onto matching Tasks rows.

    Personal sheets are the source of truth when an employee marks done /
    in-progress there. Match by assignee+title+due, then assignee+title.
    """
    unused = list(personal_tasks)
    updated: list[Task] = []
    for task in main_tasks:
        full = task_match_key(task.title, task.assignee_name, task.due_date)
        soft = task_soft_key(task.title, task.assignee_name)
        match_index = next(
            (
                index
                for index, personal in enumerate(unused)
                if task_match_key(personal.title, personal.assignee_name, personal.due_date) == full
            ),
            None,
        )
        if match_index is None:
            match_index = next(
                (
                    index
                    for index, personal in enumerate(unused)
                    if task_soft_key(personal.title, personal.assignee_name) == soft
                ),
                None,
            )
        if match_index is None:
            updated.append(task)
            continue
        personal = unused.pop(match_index)
        if personal.status == task.status:
            updated.append(task)
        else:
            updated.append(replace(task, status=personal.status))
    return updated


def paginate(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    """Return (slice, clamped_page, total_pages)."""
    if page_size <= 0:
        page_size = 1
    total_pages = max(1, (len(items) + page_size - 1) // page_size) if items else 1
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start : start + page_size], page, total_pages
