"""Telegram inline and reply keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import config

from services.sheets import GENERAL_PROJECT_CATEGORIES, PRIORITIES, Personnel, Task

OPEN_SHEET_BUTTON = "📊 باز کردن شیت"
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

MY_TASKS_TEXTS = frozenset({MY_TASKS_BUTTON, "تسک‌های من", "تسک های من"})
ADMIN_MY_TASKS_TEXTS = frozenset({ADMIN_MY_TASKS_BUTTON, "تسک‌های من", "تسک های من"})
DONE_TASKS_TEXTS = frozenset({DONE_TASKS_BUTTON, "تسک‌های انجام‌شده", "تسک های انجام شده"})
TEAM_TASKS_TEXTS = frozenset({
    TEAM_TASKS_BUTTON,
    "👥 تسک کارمندان",
    "👥 همه تسک‌ها",
    "تسک‌های گروه",
    "تسک های گروه",
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
CONFIRM_ANNOUNCE_BUTTON = "✅ تأیید و ارسال برای همه"
CANCEL_ANNOUNCE_BUTTON = "❌ انصراف اعلان"

STATUS_LABELS = {
    "pending": "⏳ در انتظار",
    "in_progress": "🔄 در حال انجام",
    "done": "✅ انجام شده",
    "cancelled": "❌ لغو شده",
}


def main_menu_keyboard(personnel: Personnel) -> ReplyKeyboardMarkup:
    """Build reply menu from permissions (not role alone)."""
    from services.auth import (
        can_access_content,
        can_access_filming,
        can_create_tasks,
        can_view_all_tasks,
        is_admin,
    )

    rows: list[list[KeyboardButton]] = []

    if can_create_tasks(personnel):
        rows.append([KeyboardButton(text=CREATE_TASK_BUTTON)])

    access_row: list[KeyboardButton] = []
    if can_access_filming(personnel):
        access_row.append(KeyboardButton(text=FILMING_BUTTON))
    if can_access_content(personnel):
        access_row.append(KeyboardButton(text=CONTENT_BUTTON))
    if access_row:
        rows.append(access_row)

    if can_view_all_tasks(personnel):
        my_label = ADMIN_MY_TASKS_BUTTON if is_admin(personnel) else MY_TASKS_BUTTON
        rows.append([
            KeyboardButton(text=TEAM_TASKS_BUTTON),
            KeyboardButton(text=my_label),
        ])
    elif is_admin(personnel):
        rows.append([
            KeyboardButton(text=ADMIN_MY_TASKS_BUTTON),
            KeyboardButton(text=IDEAS_BUTTON),
        ])
    else:
        rows.append([
            KeyboardButton(text=MY_TASKS_BUTTON),
            KeyboardButton(text=DONE_TASKS_BUTTON),
        ])

    if can_view_all_tasks(personnel) or not is_admin(personnel):
        rows.append([KeyboardButton(text=IDEAS_BUTTON), KeyboardButton(text=OPEN_SHEET_BUTTON)])
    else:
        rows.append([KeyboardButton(text=OPEN_SHEET_BUTTON)])

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


def content_menu_keyboard(sheet_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=CREATE_CONTENT_BUTTON, callback_data="content:new")],
            [InlineKeyboardButton(text=LIST_CONTENT_BUTTON, callback_data="content:list")],
            [InlineKeyboardButton(text=OPEN_CONTENT_SHEET_BUTTON, url=sheet_url)],
        ]
    )


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


def filming_date_inline_keyboard(*, before: int = 15, after: int = 15) -> InlineKeyboardMarkup:
    """Same ±15 day picker as task due dates, with filming callback prefix."""
    from services.sheets import SheetsService

    buttons: list[list[InlineKeyboardButton]] = []
    dates = SheetsService.shamsi_date_range(before=before, after=after)
    past = [(o, d) for o, d in dates if o < 0]
    today_rows = [(o, d) for o, d in dates if o == 0]
    future = [(o, d) for o, d in dates if o > 0]

    def _append_date_grid(items: list[tuple[int, str]]) -> None:
        row: list[InlineKeyboardButton] = []
        for offset, date_str in items:
            label = SheetsService.shamsi_date_button_label(offset, date_str)
            row.append(
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"filmdate:{offset}",
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    if past:
        buttons.append(
            [InlineKeyboardButton(text=f"⏪ {before} روز قبل", callback_data="noop")]
        )
        _append_date_grid(past)
    if today_rows:
        _append_date_grid(today_rows)
    if future:
        buttons.append(
            [InlineKeyboardButton(text=f"⏩ {after} روز بعد", callback_data="noop")]
        )
        _append_date_grid(future)
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


def cancel_idea_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="idea:cancel")],
        ]
    )


def open_sheet_inline_keyboard(url: str, *, label: str = "📊 باز کردن Google Sheet") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, url=url)],
        ]
    )


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


def projects_inline_keyboard(projects: list[str]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, project in enumerate(projects[:30]):
        row.append(
            InlineKeyboardButton(
                text=_project_picker_label(project),
                callback_data=f"projectidx:{index}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filming_projects_inline_keyboard(projects: list[str]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, project in enumerate(projects[:30]):
        row.append(
            InlineKeyboardButton(
                text=_project_picker_label(project),
                callback_data=f"filmproject:{index}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="film:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


def content_projects_inline_keyboard(projects: list[str]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, project in enumerate(projects[:30]):
        row.append(
            InlineKeyboardButton(
                text=_project_picker_label(project),
                callback_data=f"contentproject:{index}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="content:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


def skip_due_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ بدون ددلاین", callback_data="skip:due_date")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel:create_task")],
        ]
    )


def due_date_inline_keyboard(*, before: int = 15, after: int = 15) -> InlineKeyboardMarkup:
    """Pick deadline: past ``before`` days + today + future ``after`` days, or manual."""
    from services.sheets import SheetsService

    buttons: list[list[InlineKeyboardButton]] = []
    dates = SheetsService.shamsi_date_range(before=before, after=after)
    past = [(o, d) for o, d in dates if o < 0]
    today_rows = [(o, d) for o, d in dates if o == 0]
    future = [(o, d) for o, d in dates if o > 0]

    def _append_date_grid(items: list[tuple[int, str]]) -> None:
        row: list[InlineKeyboardButton] = []
        for offset, date_str in items:
            label = SheetsService.shamsi_date_button_label(offset, date_str)
            row.append(
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"duedate:{offset}",
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

    if past:
        buttons.append(
            [InlineKeyboardButton(text=f"⏪ {before} روز قبل", callback_data="noop")]
        )
        _append_date_grid(past)

    if today_rows:
        _append_date_grid(today_rows)

    if future:
        buttons.append(
            [InlineKeyboardButton(text=f"⏩ {after} روز بعد", callback_data="noop")]
        )
        _append_date_grid(future)

    buttons.append(
        [InlineKeyboardButton(text="✏️ ورود دستی تاریخ", callback_data="duedate:manual")]
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


def user_tasks_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    """Task list for one employee + back to the team user picker."""
    markup = task_list_keyboard(tasks, show_assignee=False)
    buttons = list(markup.inline_keyboard)
    buttons.append(
        [InlineKeyboardButton(text="🔙 لیست کارمندان", callback_data="task:users")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_list_keyboard(tasks: list[Task], *, show_assignee: bool = False) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for task in tasks[:20]:
        prefix = STATUS_LABELS.get(task.status, task.status)
        if show_assignee and task.assignee_name:
            label = f"{prefix} | {task.assignee_name[:20]} | {task.title[:28]}"
        else:
            label = f"{prefix} | {task.title[:35]}"
        # Telegram inline-button text is capped at 64 characters.
        buttons.append(
            [InlineKeyboardButton(text=label[:64], callback_data=f"task:view:{task.id}")]
        )
    if not buttons:
        buttons.append([InlineKeyboardButton(text="تسکی یافت نشد", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_detail_keyboard(
    task: Task,
    *,
    can_update_status: bool = True,
    back_callback: str = "task:list",
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    if can_update_status and task.status in {"pending", "in_progress"}:
        if task.status == "pending":
            buttons.append(
                [InlineKeyboardButton(text="🔄 شروع کار", callback_data=f"task:status:{task.id}:in_progress")]
            )
        buttons.append(
            [InlineKeyboardButton(text="✅ انجام شد", callback_data=f"task:status:{task.id}:done")]
        )
        buttons.append(
            [InlineKeyboardButton(text="❌ تسک لغو شده", callback_data=f"task:status:{task.id}:cancelled")]
        )
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
