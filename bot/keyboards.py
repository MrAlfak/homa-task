"""Telegram inline and reply keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from services.sheets_models import (
    GENERAL_PROJECT_CATEGORIES,
    PRIORITIES,
    PROJECTS_PAGE_SIZE,
    REPORT_KIND_LABELS,
    TASKS_PAGE_SIZE,
    Personnel,
    Task,
    paginate,
    shamsi_date_button_label,
    shamsi_date_range,
)

OPEN_SHEET_BUTTON = "📊 باز کردن شیت"
REPORTS_BUTTON = "📊 گزارش‌ها"
IDEAS_BUTTON = "💡 ایده‌ها"
FILMING_BUTTON = "🎥 تصویر برداری"
CREATE_FILMING_BUTTON = "➕ ثبت تصویر برداری"
LIST_FILMING_BUTTON = "📋 لیست تصویر برداری"
OPEN_FILMING_SHEET_BUTTON = "📊 شیت تصویر برداری"
CONTENT_BUTTON = "✍️ تولید محتوا"
CREATE_CONTENT_BUTTON = "➕ ثبت تولید محتوا"
LIST_CONTENT_BUTTON = "📋 لیست تولید محتوا"
OPEN_CONTENT_SHEET_BUTTON = "📊 شیت دیزاین"
TEAM_TASKS_BUTTON = "👥 تسک‌های گروه"
MY_TASKS_BUTTON = "📌 تسک‌های من"
ADMIN_MY_TASKS_BUTTON = "📋 تسک‌های من"
DONE_TASKS_BUTTON = "✅ تسک‌های انجام‌شده"
CREATE_TASK_BUTTON = "➕ ثبت تسک جدید"
# Reply keyboards may omit emoji on older clients — match all variants.
CREATE_TASK_TEXTS = frozenset({
    CREATE_TASK_BUTTON,
    "ثبت تسک جدید",
    "+ ثبت تسک جدید",
    "➕ثبت تسک جدید",
})

MY_TASKS_TEXTS = frozenset(
    {MY_TASKS_BUTTON, "تسک‌های من", "تسک های من", "📌تسک‌های من", "📌تسک های من"}
    | {f"📌 تسک‌های من ({i})" for i in range(1, 101)}
    | {f"📌 تسک های من ({i})" for i in range(1, 101)}
    | {f"📌تسک‌های من ({i})" for i in range(1, 101)}
    | {f"📌تسک های من ({i})" for i in range(1, 101)}
)
ADMIN_MY_TASKS_TEXTS = frozenset(
    {ADMIN_MY_TASKS_BUTTON, "📋تسک‌های من", "📋تسک های من", "📋 تسک های من"}
    | {f"📋 تسک‌های من ({i})" for i in range(1, 101)}
    | {f"📋 تسک های من ({i})" for i in range(1, 101)}
    | {f"📋تسک‌های من ({i})" for i in range(1, 101)}
    | {f"📋تسک های من ({i})" for i in range(1, 101)}
)
MY_TASKS_ALL_TEXTS = MY_TASKS_TEXTS | ADMIN_MY_TASKS_TEXTS
DONE_TASKS_TEXTS = frozenset({
    DONE_TASKS_BUTTON,
    "تسک‌های انجام‌شده",
    "تسک‌های انجام شده",
    "تسک های انجام شده",
    "✅ تسک‌های انجام شده",
    "✅ تسک های انجام شده",
})
TEAM_TASKS_TEXTS = frozenset({
    TEAM_TASKS_BUTTON,
    "👥 تسک کارمندان",
    "👥 همه تسک‌ها",
    "تسک‌های گروه",
    "تسک های گروه",
    "تسک‌های تیم",
    "تسک های تیم",
    "👥 تسک‌های تیم",
    "👥 تسک های تیم",
})
IDEAS_TEXTS = frozenset({IDEAS_BUTTON, "ایده‌ها", "ایده ها"})
FILMING_TEXTS = frozenset({FILMING_BUTTON, "تصویر برداری", "تصویربرداری"})
CREATE_FILMING_TEXTS = frozenset({CREATE_FILMING_BUTTON, "ثبت تصویر برداری", "ثبت تصویربرداری"})
LIST_FILMING_TEXTS = frozenset({LIST_FILMING_BUTTON, "لیست تصویر برداری", "لیست تصویربرداری"})
OPEN_FILMING_SHEET_TEXTS = frozenset({OPEN_FILMING_SHEET_BUTTON, "شیت تصویر برداری"})
CONTENT_TEXTS = frozenset({CONTENT_BUTTON, "تولید محتوا", "تولیدمحتوا"})
CREATE_CONTENT_TEXTS = frozenset({CREATE_CONTENT_BUTTON, "ثبت تولید محتوا", "ثبت تولیدمحتوا"})
LIST_CONTENT_TEXTS = frozenset({LIST_CONTENT_BUTTON, "لیست تولید محتوا", "لیست تولیدمحتوا"})
OPEN_CONTENT_SHEET_TEXTS = frozenset({OPEN_CONTENT_SHEET_BUTTON, "شیت دیزاین", "شیت تولید محتوا"})
OPEN_SHEET_TEXTS = frozenset({OPEN_SHEET_BUTTON, "باز کردن شیت"})
REPORTS_TEXTS = frozenset({REPORTS_BUTTON, "گزارش‌ها", "گزارشها", "گزارش ها"})
CONFIRM_ANNOUNCE_BUTTON = "✅ تأیید و ارسال برای همه"
CANCEL_ANNOUNCE_BUTTON = "❌ انصراف اعلان"

SPECIAL_SECTIONS_BUTTON = "🗂 بخش‌های تخصصی"
BACK_TO_MAIN_MENU_BUTTON = "🔙 بازگشت به منوی اصلی"

SPECIAL_SECTIONS_TEXTS = frozenset({SPECIAL_SECTIONS_BUTTON, "بخش‌های تخصصی", "بخش های تخصصی"})
BACK_TO_MAIN_MENU_TEXTS = frozenset({BACK_TO_MAIN_MENU_BUTTON, "بازگشت به منوی اصلی", "بازگشت"})

# Actual reply-keyboard labels on the main menu. Announce confirm/cancel stay
# out: those must not reset FSM (or a text-step) before their own handlers run.
REPLY_MENU_TEXTS = (
    CREATE_TASK_TEXTS
    | MY_TASKS_ALL_TEXTS
    | DONE_TASKS_TEXTS
    | TEAM_TASKS_TEXTS
    | IDEAS_TEXTS
    | FILMING_TEXTS
    | CONTENT_TEXTS
    | OPEN_SHEET_TEXTS
    | REPORTS_TEXTS
    | SPECIAL_SECTIONS_TEXTS
    | BACK_TO_MAIN_MENU_TEXTS
)


def is_my_tasks_text(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if t in MY_TASKS_ALL_TEXTS:
        return True
    normalized = (
        t.replace("\u064a", "\u06cc")  # ي -> ی
        .replace("\u0643", "\u06a9")  # ك -> ک
        .replace("\u200c", " ")       # نیم‌فاصله -> فاصله
        .replace("📌", "")
        .replace("📋", "")
        .strip()
    )
    return normalized.startswith("تسک های من")


def is_done_tasks_text(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if t in DONE_TASKS_TEXTS:
        return True
    normalized = (
        t.replace("\u064a", "\u06cc")
        .replace("\u0643", "\u06a9")
        .replace("\u200c", " ")
        .replace("✅", "")
        .strip()
    )
    return normalized.startswith("تسک های انجام شده")


def is_team_tasks_text(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if t in TEAM_TASKS_TEXTS:
        return True
    normalized = (
        t.replace("\u064a", "\u06cc")
        .replace("\u0643", "\u06a9")
        .replace("\u200c", " ")
        .replace("👥", "")
        .strip()
    )
    return (
        normalized.startswith("تسک های گروه")
        or normalized.startswith("تسک های تیم")
        or normalized.startswith("تسک کارمندان")
        or normalized.startswith("همه تسک ها")
    )


def is_menu_text(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    if t in REPLY_MENU_TEXTS:
        return True
    return is_my_tasks_text(t) or is_done_tasks_text(t) or is_team_tasks_text(t)

STATUS_LABELS = {
    "pending": "⏳ در انتظار",
    "in_progress": "🔄 در حال انجام",
    "done": "✅ انجام شده",
    "cancelled": "❌ لغو شده",
}


def main_menu_keyboard(personnel: Personnel, open_tasks_count: int | None = None) -> ReplyKeyboardMarkup:
    """Build clean, uncluttered reply menu from permissions."""
    from services.auth import (
        can_create_tasks,
        can_view_all_tasks,
        is_admin,
    )

    rows: list[list[KeyboardButton]] = []

    # Row 1: Create Task (if authorized)
    if can_create_tasks(personnel):
        rows.append([KeyboardButton(text=CREATE_TASK_BUTTON)])

    # Row 2: My Tasks (with badge if open_tasks_count > 0) + Team/Done tasks
    my_label = "📌 تسک‌های من"
    if open_tasks_count is not None and open_tasks_count > 0:
        my_label = f"📌 تسک‌های من ({open_tasks_count})"
    elif is_admin(personnel):
        my_label = "📋 تسک‌های من"

    if can_view_all_tasks(personnel):
        rows.append([
            KeyboardButton(text=TEAM_TASKS_BUTTON),
            KeyboardButton(text=my_label),
        ])
        rows.append([
            KeyboardButton(text=DONE_TASKS_BUTTON),
            KeyboardButton(text=SPECIAL_SECTIONS_BUTTON),
        ])
    else:
        rows.append([
            KeyboardButton(text=my_label),
            KeyboardButton(text=DONE_TASKS_BUTTON),
        ])
        rows.append([
            KeyboardButton(text=SPECIAL_SECTIONS_BUTTON),
            KeyboardButton(text=OPEN_SHEET_BUTTON),
        ])

    if can_view_all_tasks(personnel):
        rows.append([KeyboardButton(text=OPEN_SHEET_BUTTON)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def special_sections_keyboard(personnel: Personnel) -> ReplyKeyboardMarkup:
    """Submenu for specialized features (filming, content, reports, ideas)."""
    from services.auth import (
        can_access_content,
        can_access_filming,
        can_access_reports,
    )

    rows: list[list[KeyboardButton]] = []
    access_row: list[KeyboardButton] = []
    if can_access_filming(personnel):
        access_row.append(KeyboardButton(text=FILMING_BUTTON))
    if can_access_content(personnel):
        access_row.append(KeyboardButton(text=CONTENT_BUTTON))
    if access_row:
        rows.append(access_row)

    r2: list[KeyboardButton] = [KeyboardButton(text=IDEAS_BUTTON)]
    if can_access_reports(personnel):
        r2.append(KeyboardButton(text=REPORTS_BUTTON))
    rows.append(r2)

    rows.append([KeyboardButton(text=BACK_TO_MAIN_MENU_BUTTON)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)



def admin_main_keyboard() -> ReplyKeyboardMarkup:
    """Legacy helper — prefer main_menu_keyboard(personnel)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CREATE_TASK_BUTTON)],
            [KeyboardButton(text=ADMIN_MY_TASKS_BUTTON), KeyboardButton(text=IDEAS_BUTTON)],
            [KeyboardButton(text=OPEN_SHEET_BUTTON)],
        ],
        resize_keyboard=True,
    )


def senior_admin_keyboard() -> ReplyKeyboardMarkup:
    """Legacy helper — prefer main_menu_keyboard(personnel)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CREATE_TASK_BUTTON)],
            [KeyboardButton(text=TEAM_TASKS_BUTTON), KeyboardButton(text=MY_TASKS_BUTTON)],
            [KeyboardButton(text=IDEAS_BUTTON), KeyboardButton(text=OPEN_SHEET_BUTTON)],
        ],
        resize_keyboard=True,
    )


def employee_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MY_TASKS_BUTTON), KeyboardButton(text=DONE_TASKS_BUTTON)],
            [KeyboardButton(text=IDEAS_BUTTON), KeyboardButton(text=OPEN_SHEET_BUTTON)],
        ],
        resize_keyboard=True,
    )


def ideas_menu_keyboard(sheet_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ ثبت ایده جدید", callback_data="idea:new")],
            [InlineKeyboardButton(text="📋 لیست ایده‌ها", callback_data="idea:list")],
            [InlineKeyboardButton(text="📊 باز کردن تب Ideas", url=sheet_url)],
        ]
    )


def filming_menu_keyboard(sheet_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=CREATE_FILMING_BUTTON, callback_data="film:new")],
            [InlineKeyboardButton(text=LIST_FILMING_BUTTON, callback_data="film:list")],
            [InlineKeyboardButton(text=OPEN_FILMING_SHEET_BUTTON, url=sheet_url)],
        ]
    )


def content_menu_keyboard(sheet_url: str, report_url: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=CREATE_CONTENT_BUTTON, callback_data="content:new")],
        [InlineKeyboardButton(text=LIST_CONTENT_BUTTON, callback_data="content:list")],
        [InlineKeyboardButton(text="📊 گزارش تجمیعی محتوا", callback_data="content:report")],
        [InlineKeyboardButton(text=OPEN_CONTENT_SHEET_BUTTON, url=sheet_url)],
    ]
    if report_url:
        buttons.append([InlineKeyboardButton(text="📈 شیت گزارش محتوا", url=report_url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def content_report_keyboard(report_url: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📅 دوره یکم تا امروز", callback_data="content:rep:1_to_1")],
        [InlineKeyboardButton(text="📅 دوره ۱۵ تا امروز", callback_data="content:rep:15_to_15")],
    ]
    if report_url:
        buttons.append([InlineKeyboardButton(text="📈 باز کردن شیت گزارش محتوا", url=report_url)])
    buttons.append([InlineKeyboardButton(text="🔙 منوی تولید محتوا", callback_data="content:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def filming_weekday_keyboard() -> InlineKeyboardMarkup:
    weekdays = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for day in weekdays:
        row.append(InlineKeyboardButton(text=day, callback_data=f"filmday:{day}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="film:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


DATE_PICKER_BEFORE = 0
DATE_PICKER_AFTER = 6  # today + 6 days = one week


def _week_date_grid(
    *,
    callback_prefix: str,
    before: int = DATE_PICKER_BEFORE,
    after: int = DATE_PICKER_AFTER,
) -> list[list[InlineKeyboardButton]]:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for offset, date_str in shamsi_date_range(before=before, after=after):
        row.append(
            InlineKeyboardButton(
                text=shamsi_date_button_label(offset, date_str)[:64],
                callback_data=f"{callback_prefix}:{offset}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def filming_date_inline_keyboard(
    *,
    before: int = DATE_PICKER_BEFORE,
    after: int = DATE_PICKER_AFTER,
) -> InlineKeyboardMarkup:
    """One-week picker (today through +6) plus manual date."""
    buttons = _week_date_grid(callback_prefix="filmdate", before=before, after=after)
    buttons.append(
        [InlineKeyboardButton(text="✏️ ورود دستی تاریخ", callback_data="filmdate:manual")]
    )
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="film:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filming_list_keyboard(entries: list) -> InlineKeyboardMarkup:
    from services.sheets import FilmingEntry

    buttons: list[list[InlineKeyboardButton]] = []
    for entry in entries[:20]:
        if not isinstance(entry, FilmingEntry):
            continue
        prefix = STATUS_LABELS.get(entry.status, entry.status)
        label = f"{prefix} | {entry.project[:20]} | {entry.assignee_name[:12]}"
        buttons.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"film:view:{entry.id}")]
        )
    if not buttons:
        buttons.append([InlineKeyboardButton(text="موردی یافت نشد", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="🔙 منوی تصویر برداری", callback_data="film:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filming_detail_keyboard(entry_id: str, *, can_update: bool, status: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if can_update and status in {"pending", "in_progress"}:
        if status == "pending":
            buttons.append(
                [InlineKeyboardButton(text="🔄 شروع کار", callback_data=f"film:status:{entry_id}:in_progress")]
            )
        buttons.append(
            [InlineKeyboardButton(text="✅ انجام شد", callback_data=f"film:status:{entry_id}:done")]
        )
        buttons.append(
            [InlineKeyboardButton(text="❌ لغو شده", callback_data=f"film:status:{entry_id}:cancelled")]
        )
    buttons.append([InlineKeyboardButton(text="🔙 لیست", callback_data="film:list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def content_list_keyboard(entries: list) -> InlineKeyboardMarkup:
    from services.sheets import ContentEntry

    buttons: list[list[InlineKeyboardButton]] = []
    for entry in entries[:20]:
        if not isinstance(entry, ContentEntry):
            continue
        prefix = STATUS_LABELS.get(entry.status, entry.status)
        label = (
            f"{prefix} | {entry.name[:12] or '—'} | "
            f"{entry.project[:14] or '—'} | {entry.content_type[:10] or '—'}"
        )
        buttons.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"content:view:{entry.id}")]
        )
    if not buttons:
        buttons.append([InlineKeyboardButton(text="موردی یافت نشد", callback_data="noop")])
    buttons.append([InlineKeyboardButton(text="🔙 منوی تولید محتوا", callback_data="content:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def content_detail_keyboard(entry_id: str, *, can_update: bool, status: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if can_update and status in {"pending", "in_progress"}:
        if status == "pending":
            buttons.append(
                [InlineKeyboardButton(text="🔄 شروع کار", callback_data=f"content:status:{entry_id}:in_progress")]
            )
        buttons.append(
            [InlineKeyboardButton(text="✅ انجام شد", callback_data=f"content:status:{entry_id}:done")]
        )
        buttons.append(
            [InlineKeyboardButton(text="❌ لغو شده", callback_data=f"content:status:{entry_id}:cancelled")]
        )
    buttons.append([InlineKeyboardButton(text="🔙 لیست", callback_data="content:list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_flow_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data=callback_data)],
        ]
    )


def cancel_idea_keyboard() -> InlineKeyboardMarkup:
    return cancel_flow_keyboard("idea:cancel")


def open_sheet_inline_keyboard(url: str, *, label: str = "📊 باز کردن Google Sheet") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, url=url)],
        ]
    )


def reports_inline_keyboard(kinds: tuple[str, ...]) -> InlineKeyboardMarkup:
    labels = dict(REPORT_KIND_LABELS)
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for kind in kinds:
        row.append(InlineKeyboardButton(text=labels.get(kind, kind), callback_data=f"report:{kind}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def personnel_inline_keyboard(employees: list[Personnel]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=employee.name[:64], callback_data=f"assign:{employee.telegram_id}"
            )
        ]
        for employee in employees
    ]
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _project_picker_label(name: str) -> str:
    """Visual hint: cross-project categories vs single-page projects."""
    prefix = "🌐 " if name in GENERAL_PROJECT_CATEGORIES else "📁 "
    return (prefix + name)[:64]


def _projects_keyboard(
    projects: list[str],
    *,
    page: int,
    item_prefix: str,
    page_prefix: str,
    cancel_data: str,
) -> InlineKeyboardMarkup:
    page_items, page, total_pages = paginate(projects, page, PROJECTS_PAGE_SIZE)
    start = page * PROJECTS_PAGE_SIZE
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for offset, project in enumerate(page_items):
        index = start + offset
        row.append(
            InlineKeyboardButton(
                text=_project_picker_label(project),
                callback_data=f"{item_prefix}:{index}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبل", callback_data=f"{page_prefix}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="بعد ➡️", callback_data=f"{page_prefix}:{page + 1}"))
    if nav:
        buttons.append(nav)
    if total_pages > 1:
        buttons.append(
            [InlineKeyboardButton(text=f"صفحه {page + 1}/{total_pages}", callback_data="noop")]
        )
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data=cancel_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def projects_inline_keyboard(projects: list[str], *, page: int = 0) -> InlineKeyboardMarkup:
    return _projects_keyboard(
        projects,
        page=page,
        item_prefix="projectidx",
        page_prefix="projectpage",
        cancel_data="cancel:create_task",
    )


def filming_projects_inline_keyboard(projects: list[str], *, page: int = 0) -> InlineKeyboardMarkup:
    return _projects_keyboard(
        projects,
        page=page,
        item_prefix="filmproject",
        page_prefix="filmpage",
        cancel_data="film:cancel",
    )


def filming_personnel_inline_keyboard(employees: list[Personnel]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=employee.name[:64],
                callback_data=f"filmassign:{employee.telegram_id}",
            )
        ]
        for employee in employees
    ]
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="film:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def content_projects_inline_keyboard(projects: list[str], *, page: int = 0) -> InlineKeyboardMarkup:
    return _projects_keyboard(
        projects,
        page=page,
        item_prefix="contentproject",
        page_prefix="contentpage",
        cancel_data="content:cancel",
    )


def content_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 پست", callback_data="contenttype:post")],
            [InlineKeyboardButton(text="📱 استوری", callback_data="contenttype:story")],
            [InlineKeyboardButton(text="📰📱 پست و استوری", callback_data="contenttype:both")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="content:cancel")],
        ]
    )


def content_person_keyboard(names: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name[:64], callback_data=f"contentperson:{index}")]
        for index, name in enumerate(names[:30])
    ]
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="content:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def priority_inline_keyboard() -> InlineKeyboardMarkup:
    labels = {"High": "🔴 High", "Medium": "🟡 Medium", "Low": "🟢 Low"}
    buttons = [
        [InlineKeyboardButton(text=labels[p], callback_data=f"priority:{p}")]
        for p in PRIORITIES
    ]
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def announce_confirm_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=CONFIRM_ANNOUNCE_BUTTON,
                    callback_data="announce:confirm",
                ),
            ],
            [
                InlineKeyboardButton(text=CANCEL_ANNOUNCE_BUTTON, callback_data="announce:cancel"),
            ],
        ]
    )


def announce_confirm_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard confirm — reliable when inline callbacks fail in some clients."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CONFIRM_ANNOUNCE_BUTTON)],
            [KeyboardButton(text=CANCEL_ANNOUNCE_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def due_date_inline_keyboard(
    *,
    before: int = DATE_PICKER_BEFORE,
    after: int = DATE_PICKER_AFTER,
) -> InlineKeyboardMarkup:
    """Pick deadline: this week (today through +6), skip, or type a date."""
    buttons = _week_date_grid(callback_prefix="duedate", before=before, after=after)
    buttons.append(
        [InlineKeyboardButton(text="✏️ ورود دستی تاریخ", callback_data="duedate:manual")]
    )
    buttons.append(
        [InlineKeyboardButton(text="⏭ بدون ددلاین (امروز)", callback_data="skip:due_date")]
    )
    buttons.append(
        [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def team_users_keyboard(members: list[Personnel]) -> InlineKeyboardMarkup:
    """Pick an employee to browse their tasks (senior admin)."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for member in members[:40]:
        row.append(
            InlineKeyboardButton(
                text=member.name[:32],
                callback_data=f"task:user:{member.telegram_id}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if not buttons:
        buttons.append([InlineKeyboardButton(text="کارمندی یافت نشد", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_tasks_keyboard(
    tasks: list[Task],
    *,
    member_tid: int,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Task list for one employee + back to the team user picker."""
    markup = task_list_keyboard(
        tasks,
        show_assignee=False,
        page=page,
        page_callback=f"task:up:{member_tid}",
    )
    buttons = list(markup.inline_keyboard)
    buttons.append(
        [InlineKeyboardButton(text="🔙 لیست کارمندان", callback_data="task:users")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_list_keyboard(
    tasks: list[Task],
    *,
    show_assignee: bool = False,
    page: int = 0,
    page_callback: str = "task:page",
    active_filter: str = "all",
) -> InlineKeyboardMarkup:
    page_items, page, total_pages = paginate(tasks, page, TASKS_PAGE_SIZE)
    buttons: list[list[InlineKeyboardButton]] = []

    if len(tasks) > 2 or active_filter != "all":
        f_all = "🔘 همه" if active_filter == "all" else "همه"
        f_overdue = "🔘 🔴 معوق" if active_filter == "overdue" else "🔴 معوق"
        f_today = "🔘 📅 امروز" if active_filter == "today" else "📅 امروز"
        buttons.append([
            InlineKeyboardButton(text=f_all, callback_data="taskfilter:all"),
            InlineKeyboardButton(text=f_overdue, callback_data="taskfilter:overdue"),
            InlineKeyboardButton(text=f_today, callback_data="taskfilter:today"),
        ])

    for task in page_items:
        prefix = STATUS_LABELS.get(task.status, task.status)
        if show_assignee and task.assignee_name:
            label = f"{prefix} | {task.assignee_name[:16]} | {task.title[:28]}"
        else:
            label = f"{prefix} | {task.title[:38]}"

        buttons.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"task:view:{task.id}")]
        )

    if not buttons:
        buttons.append([InlineKeyboardButton(text="تسکی یافت نشد", callback_data="noop")])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبل", callback_data=f"{page_callback}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="بعد ➡️", callback_data=f"{page_callback}:{page + 1}"))
    if nav:
        buttons.append(nav)
    if total_pages > 1:
        buttons.append(
            [InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_detail_keyboard(
    task: Task,
    *,
    can_update_status: bool = True,
    is_manager: bool = False,
    back_callback: str = "task:list",
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if can_update_status and task.status in {"pending", "in_progress"}:
        status_row: list[InlineKeyboardButton] = []
        if task.status == "pending":
            status_row.append(
                InlineKeyboardButton(text="🔄 شروع", callback_data=f"task:status:{task.id}:in_progress")
            )
        status_row.append(
            InlineKeyboardButton(text="✅ انجام شد", callback_data=f"task:status:{task.id}:done")
        )
        status_row.append(
            InlineKeyboardButton(text="❌ لغو", callback_data=f"task:status:{task.id}:cancelled")
        )
        buttons.append(status_row)

    buttons.append([
        InlineKeyboardButton(text="💬 ثبت / ویرایش یادداشت", callback_data=f"task:note:{task.id}")
    ])

    if is_manager:
        buttons.append([
            InlineKeyboardButton(text="📅 تغییر ددلاین", callback_data=f"task:editdue:{task.id}"),
            InlineKeyboardButton(text="⚡ تغییر اولویت", callback_data=f"task:editpri:{task.id}"),
        ])

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_confirm_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تأیید و ثبت تسک", callback_data="taskconfirm:yes")],
            [InlineKeyboardButton(text="✏️ ویرایش عنوان", callback_data="taskconfirm:edittitle")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")],
        ]
    )


def edit_priority_inline_keyboard(task_id: str) -> InlineKeyboardMarkup:
    labels = {"High": "🔴 High", "Medium": "🟡 Medium", "Low": "🟢 Low"}
    buttons = [
        [InlineKeyboardButton(text=labels[p], callback_data=f"task:setpri:{task_id}:{p}")]
        for p in PRIORITIES
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به تسک", callback_data=f"task:view:{task_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def edit_due_date_inline_keyboard(task_id: str) -> InlineKeyboardMarkup:
    buttons = _week_date_grid(callback_prefix=f"task:setdue:{task_id}")
    buttons.append(
        [InlineKeyboardButton(text="✏️ ورود دستی تاریخ", callback_data=f"task:setdue:{task_id}:manual")]
    )
    buttons.append(
        [InlineKeyboardButton(text="🔙 بازگشت به تسک", callback_data=f"task:view:{task_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
