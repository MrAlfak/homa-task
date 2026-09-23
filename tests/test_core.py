"""Unit tests that do not need Google Sheets or a live bot token."""

from __future__ import annotations

import datetime
import unittest

import jdatetime

from services.auth import (
    can_access_content,
    can_access_filming,
    can_access_report_kind,
    can_access_reports,
    can_create_tasks,
    can_update_content_entry,
    can_update_filming_entry,
    can_view_all_tasks,
    is_admin,
    is_senior_admin,
)
from services.sheets_models import (
    STATUS_SHEET_VALUES,
    TEHRAN_TZ,
    ContentEntry,
    ContentSummaryItem,
    FilmingEntry,
    Personnel,
    Task,
    coalesce_personnel,
    encode_task_id,
    get_jalali_period_dates,
    normalize_mobile,
    normalize_sheet_title,
    normalize_status,
    overlay_status_from_personal,
    paginate,
    parse_task_id,
    personnel_from_record,
    record_telegram_id,
    sms_settings_from_records,
    status_to_sheet,
    tehran_now,
    tehran_today,
    today_jalali_str,
    validate_shamsi_date,
)


def _person(**kwargs) -> Personnel:
    defaults = {
        "telegram_id": 1,
        "name": "علی",
        "role": "employee",
        "active": True,
    }
    defaults.update(kwargs)
    return Personnel(**defaults)


class AuthTests(unittest.TestCase):
    def test_admin_can_create_not_view_all(self) -> None:
        admin = _person(role="admin", name="مدیر")
        self.assertTrue(is_admin(admin))
        self.assertTrue(can_create_tasks(admin))
        self.assertFalse(can_view_all_tasks(admin))

    def test_senior_needs_view_flag(self) -> None:
        senior = _person(role="employee", senior_admin=True, view_all_tasks=True)
        self.assertTrue(is_senior_admin(senior))
        self.assertTrue(can_view_all_tasks(senior))
        self.assertTrue(can_create_tasks(senior))

    def test_filming_update_is_assignee_or_admin(self) -> None:
        assignee = _person(name="سارا", filming_access=True)
        other = _person(name="رضا", telegram_id=2, filming_access=True)
        admin = _person(role="admin", name="مدیر", filming_access=True)
        entry = FilmingEntry(
            row_index=2,
            project="پست",
            location="استودیو",
            day="شنبه",
            hour="10",
            date="1405/01/01",
            assignee_name="سارا",
            status="pending",
            created_by="مدیر",
        )
        self.assertTrue(can_update_filming_entry(assignee, entry))
        self.assertFalse(can_update_filming_entry(other, entry))
        self.assertTrue(can_update_filming_entry(admin, entry))
        self.assertFalse(can_access_filming(_person()))

    def test_report_flags(self) -> None:
        off = _person()
        self.assertFalse(can_access_reports(off))
        master = _person(reports_access=True)
        self.assertTrue(can_access_reports(master))
        self.assertTrue(can_access_report_kind(master, "summary"))
        self.assertTrue(can_access_report_kind(master, "people"))
        limited = _person(reports_access=True, report_people=True)
        self.assertTrue(can_access_report_kind(limited, "people"))
        self.assertFalse(can_access_report_kind(limited, "month"))
        self.assertFalse(can_access_report_kind(limited, "summary"))

    def test_content_update_matches_name(self) -> None:
        person = _person(name="علیپور", content_access=True)
        entry = ContentEntry(
            row_index=3,
            name="علیپور",
            project="عمومی",
            post="✓",
            story="",
            status="pending",
            created_by="مدیر",
        )
        self.assertTrue(can_access_content(person))
        self.assertTrue(can_update_content_entry(person, entry))


class ModelTests(unittest.TestCase):
    def test_tehran_timezone_pinning(self) -> None:
        now = tehran_now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.tzinfo.utcoffset(None), datetime.timedelta(hours=3, minutes=30))
        today_str = today_jalali_str()
        self.assertEqual(len(today_str), 10)
        self.assertTrue(today_str.startswith("14"))

    def test_jalali_period_calculation(self) -> None:
        d1 = jdatetime.date(1405, 6, 20)
        from_d, to_d, label = get_jalali_period_dates("1_to_1", d1)
        self.assertEqual(from_d, "1405/06/01")
        self.assertEqual(to_d, "1405/06/20")
        self.assertIn("دوره یکم", label)

        from_d, to_d, label = get_jalali_period_dates("15_to_15", d1)
        self.assertEqual(from_d, "1405/06/15")
        self.assertEqual(to_d, "1405/06/20")
        self.assertIn("۱۵", label)

        d2 = jdatetime.date(1405, 6, 5)
        from_d2, to_d2, label2 = get_jalali_period_dates("15_to_15", d2)
        self.assertEqual(from_d2, "1405/05/15")
        self.assertEqual(to_d2, "1405/06/05")

        d3 = jdatetime.date(1405, 1, 10)
        from_d3, to_d3, label3 = get_jalali_period_dates("15_to_15", d3)
        self.assertEqual(from_d3, "1404/12/15")
        self.assertEqual(to_d3, "1405/01/10")

    def test_content_entry_date_and_counts(self) -> None:
        entry = ContentEntry(
            row_index=5,
            name="بخشی",
            project="عمومی",
            post="✓",
            story="",
            status="pending",
            created_by="مدیر",
        )
        self.assertEqual(entry.effective_post_count, 1)
        self.assertEqual(entry.effective_story_count, 0)
        self.assertEqual(entry.content_type, "پست")

        entry2 = ContentEntry(
            row_index=6,
            name="علیپور",
            project="پیج اصلی",
            post="✓",
            story="✓",
            status="pending",
            created_by="مدیر",
            date="1405/06/28",
            post_count=2,
            story_count=5,
        )
        self.assertEqual(entry2.effective_post_count, 2)
        self.assertEqual(entry2.effective_story_count, 5)
        self.assertEqual(entry2.date, "1405/06/28")
        self.assertEqual(entry2.content_type, "پست و استوری")

    def test_format_task_overview_categorization(self) -> None:
        from bot.handlers.employee_tasks import _format_task_overview

        today = tehran_today()
        today_str = f"{today.year:04d}/{today.month:02d}/{today.day:02d}"
        yesterday = today - jdatetime.timedelta(days=1)
        yesterday_str = f"{yesterday.year:04d}/{yesterday.month:02d}/{yesterday.day:02d}"
        tomorrow = today + jdatetime.timedelta(days=1)
        tomorrow_str = f"{tomorrow.year:04d}/{tomorrow.month:02d}/{tomorrow.day:02d}"

        t_overdue = Task(
            sheet_name="علی",
            row_index=2,
            title="تسک دیروز",
            project="هما",
            assignee_name="علی",
            created_by="مدیر",
            created_at=yesterday_str,
            due_date=yesterday_str,
            priority="High",
            status="pending",
            description="",
        )
        t_today = Task(
            sheet_name="علی",
            row_index=3,
            title="تسک امروز",
            project="عمومی",
            assignee_name="علی",
            created_by="مدیر",
            created_at=today_str,
            due_date=today_str,
            priority="High",
            status="pending",
            description="",
        )
        t_future = Task(
            sheet_name="علی",
            row_index=4,
            title="تسک فردا",
            project="عمومی",
            assignee_name="علی",
            created_by="مدیر",
            created_at=today_str,
            due_date=tomorrow_str,
            priority="Normal",
            status="pending",
            description="",
        )

        text, sorted_tasks = _format_task_overview("📌 تسک‌های من", [t_future, t_overdue, t_today])

        # Verify categorization text contains sections
        self.assertIn("تسک‌های امروز", text)
        self.assertIn("تسک‌های معوقه", text)
        self.assertIn("تسک فردا", text)

        # Verify sorted_tasks priority: overdue first, then today, then future
        self.assertEqual(sorted_tasks[0].title, "تسک دیروز")
        self.assertEqual(sorted_tasks[1].title, "تسک امروز")
        self.assertEqual(sorted_tasks[2].title, "تسک فردا")

    def test_task_id_is_ascii_and_short(self) -> None:
        task = Task(
            sheet_name="سید علی‌رضا محمدی",
            row_index=12,
            title="عنوان",
            project="عمومی",
            assignee_name="سید علی‌رضا محمدی",
            created_by="مدیر",
            created_at="1405/01/01",
            due_date="1405/01/02",
            priority="High",
            status="pending",
            description="",
            sheet_gid=987654321,
        )
        self.assertEqual(task.id, "t:987654321:12")
        self.assertLessEqual(len(f"task:status:{task.id}:in_progress".encode()), 64)
        parsed = parse_task_id(task.id)
        self.assertEqual(parsed, (987654321, None, 12))

    def test_legacy_task_id_still_parses(self) -> None:
        self.assertEqual(parse_task_id("Tasks:4"), (None, "Tasks", 4))
        self.assertEqual(encode_task_id(0, 4, "Tasks"), "Tasks:4")

    def test_persian_personnel_headers(self) -> None:
        record = {
            "شناسه تلگرام": "12345",
            "نام": "مینا",
            "نقش": "admin",
            "فعال": "TRUE",
            "مدیر ارشد": "FALSE",
        }
        self.assertEqual(record_telegram_id(record), 12345)
        person = personnel_from_record(record, 12345)
        self.assertEqual(person.name, "مینا")
        self.assertEqual(person.role, "admin")
        self.assertTrue(person.active)

    def test_mobile_and_sms_flags(self) -> None:
        record = {
            "telegram_id": "9",
            "name": "علی",
            "role": "employee",
            "active": "TRUE",
            "موبایل": "0912-000-0000",
            "ارسال پیامک": "TRUE",
            "ارسال تلگرام": "TRUE",
        }
        person = personnel_from_record(record, 9)
        self.assertEqual(person.mobile, "9120000000")
        self.assertTrue(person.sms_enabled)
        self.assertTrue(person.telegram_notify)
        off_record = {
            "telegram_id": "9",
            "name": "علی",
            "role": "employee",
            "active": "TRUE",
        }
        self.assertFalse(personnel_from_record(off_record, 9).telegram_notify)
        self.assertEqual(normalize_mobile("+989121111111"), "9121111111")
        self.assertEqual(normalize_mobile("۰۹۱۲۱۱۱۱۱۱۱"), "9121111111")
        self.assertEqual(normalize_mobile("٠٩١٢١١١١١١١"), "9121111111")
        self.assertEqual(normalize_mobile("0989121111111"), "9121111111")
        self.assertEqual(normalize_mobile("989121111111"), "9121111111")
        self.assertEqual(normalize_mobile("9121111111.0"), "9121111111")
        self.assertEqual(normalize_mobile("0912 111 1111"), "9121111111")
        self.assertEqual(normalize_mobile("+98 912 111 1111"), "9121111111")
        self.assertEqual(normalize_mobile("0912-111-1111"), "9121111111")
        self.assertEqual(normalize_mobile("09121111111 (واتساپ)"), "9121111111")
        self.assertEqual(normalize_mobile("09121111111 / 09352222222"), "9121111111")
        self.assertEqual(normalize_mobile("02188888888"), "")
        self.assertEqual(normalize_mobile("123"), "")

    def test_parse_bool_and_name_normalization(self) -> None:
        from services.sheets_models import normalize_name, parse_bool

        self.assertTrue(parse_bool(True))
        self.assertFalse(parse_bool(False))
        self.assertTrue(parse_bool("TRUE"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("بله"))
        self.assertTrue(parse_bool("فعال"))
        self.assertTrue(parse_bool("دارد"))
        self.assertTrue(parse_bool("صحیح"))
        self.assertFalse(parse_bool("FALSE"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool(""))

        self.assertEqual(normalize_name("  علي  "), "علی")
        self.assertEqual(normalize_name("بانك"), "بانک")

    def test_personnel_sms_aliases(self) -> None:
        rec1 = {"نام": "محمد", "شماره تماس": "09123334444", "پیامک": "بله"}
        p1 = personnel_from_record(rec1, 10)
        self.assertEqual(p1.mobile, "9123334444")
        self.assertTrue(p1.sms_enabled)

        rec2 = {"Name": "رضا", "تلفن همراه": "09125556666", "ارسال sms": "TRUE"}
        p2 = personnel_from_record(rec2, 20)
        self.assertEqual(p2.mobile, "9125556666")
        self.assertTrue(p2.sms_enabled)

    def test_coalesce_keeps_mobile_from_duplicate_row(self) -> None:
        left = Personnel(telegram_id=1, name="Ali", role="admin", active=True)
        right = Personnel(
            telegram_id=1,
            name="Ali",
            role="employee",
            active=True,
            mobile="9120000000",
            sms_enabled=True,
            telegram_notify=True,
        )
        merged = coalesce_personnel(left, right)
        self.assertEqual(merged.role, "admin")
        self.assertEqual(merged.mobile, "9120000000")
        self.assertTrue(merged.sms_enabled)
        self.assertTrue(merged.telegram_notify)

    def test_sms_skip_reason(self) -> None:
        from services.sms import skip_reason_for_person

        off = Personnel(
            telegram_id=1, name="A", role="employee", active=True, mobile="9120000000"
        )
        self.assertEqual(skip_reason_for_person(off), "ارسال پیامک=FALSE")
        bad = Personnel(
            telegram_id=1,
            name="A",
            role="employee",
            active=True,
            mobile="12",
            sms_enabled=True,
        )
        self.assertEqual(skip_reason_for_person(bad), "شماره موبایل خالی یا نامعتبر")
        ok = Personnel(
            telegram_id=1,
            name="A",
            role="employee",
            active=True,
            mobile="9120000000",
            sms_enabled=True,
        )
        self.assertEqual(skip_reason_for_person(ok), "")
        self.assertEqual(
            skip_reason_for_person(ok, seen_mobiles={"9120000000"}),
            "شماره تکراری",
        )

    def test_sms_settings_from_sheet_rows(self) -> None:
        settings = sms_settings_from_records(
            [
                {"کلید": "فعال", "مقدار": "TRUE"},
                {"کلید": "شماره فرستنده", "مقدار": "auto"},
                {"کلید": "تلاش مجدد", "مقدار": "۴"},
                {"کلید": "پیامک اطلاعیه همگانی", "مقدار": "FALSE"},
            ]
        )
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.sender, "auto")
        self.assertEqual(settings.try_send, 4)
        self.assertTrue(settings.on_new_task)
        self.assertFalse(settings.on_announce)

    def test_status_and_date(self) -> None:
        self.assertEqual(normalize_status("انجام شد"), "done")
        self.assertEqual(normalize_status("تمام شده"), "done")
        self.assertEqual(normalize_status("درحال انجام"), "in_progress")
        self.assertEqual(normalize_status("در حال انجامه"), "in_progress")
        self.assertEqual(status_to_sheet("done"), "انجام شده")
        self.assertEqual(
            STATUS_SHEET_VALUES,
            ("در انتظار", "در حال انجام", "انجام شده", "لغو شده"),
        )
        self.assertEqual(normalize_status("❌ لغو شده"), "cancelled")
        self.assertEqual(validate_shamsi_date("1405-4-9"), "1405/04/09")
        self.assertIsNone(validate_shamsi_date("not-a-date"))
        self.assertEqual(normalize_sheet_title("تـــدوین "), "تدوین")

    def test_overlay_status_from_personal_tabs(self) -> None:
        def _task(*, title: str, status: str, sheet: str, row: int, due: str = "1405/01/02") -> Task:
            return Task(
                sheet_name=sheet,
                row_index=row,
                title=title,
                project="عمومی",
                assignee_name="Alfak",
                created_by="مدیر",
                created_at="1405/01/01",
                due_date=due,
                priority="High",
                status=status,
                description="",
                sheet_gid=1 if sheet == "Tasks" else 2,
            )

        main = [
            _task(title="الف", status="pending", sheet="Tasks", row=2),
            _task(title="ب", status="pending", sheet="Tasks", row=3),
        ]
        personal = [
            _task(title="الف", status="done", sheet="Alfak", row=5),
            _task(title="ب", status="in_progress", sheet="Alfak", row=6),
        ]
        merged = overlay_status_from_personal(main, personal)
        self.assertEqual([task.status for task in merged], ["done", "in_progress"])
        self.assertEqual([task.row_index for task in merged], [2, 3])

    def test_paginate(self) -> None:
        items = list(range(10))
        page, index, total = paginate(items, 1, 4)
        self.assertEqual(page, [4, 5, 6, 7])
        self.assertEqual(index, 1)
        self.assertEqual(total, 3)

    def test_template_assignees_and_schedule(self) -> None:
        import jdatetime

        from services.sheets_models import (
            next_run_on_or_after,
            split_assignee_names,
            template_from_record,
            template_is_due,
        )

        self.assertEqual(
            split_assignee_names("Alfak، Dehghanian, Alfak"),
            ["Alfak", "Dehghanian"],
        )
        monthly = next_run_on_or_after(
            recurrence="ماهانه",
            day_base="1",
            start=jdatetime.date(1405, 6, 21),
            on_or_after=jdatetime.date(1405, 6, 21),
        )
        self.assertEqual((monthly.year, monthly.month, monthly.day), (1405, 7, 1))
        weekly = next_run_on_or_after(
            recurrence="هفتگی",
            day_base="شنبه",
            start=None,
            on_or_after=jdatetime.date(1405, 6, 21),
        )
        self.assertEqual(weekly.weekday(), 0)
        quarterly = next_run_on_or_after(
            recurrence="سه ماهه",
            day_base="1",
            start=jdatetime.date(1405, 7, 1),
            on_or_after=jdatetime.date(1405, 8, 1),
        )
        self.assertEqual((quarterly.year, quarterly.month, quarterly.day), (1405, 10, 1))
        off = template_from_record(
            {
                "فعال": "FALSE",
                "تسک": "تست قالب ماهانه",
                "پروژه": "عمومی",
                "مسوول تسک": "Alfak, Dehghanian",
                "اولویت": "Low",
                "تکرارشوندگی": "ماهانه",
                "روز مبنا": "1",
                "مهلت (روز)": "5",
                "تاریخ شروع": "1405/07/01",
            },
            2,
        )
        self.assertIsNotNone(off)
        self.assertFalse(off.enabled)
        self.assertEqual(off.assignee_names, ["Alfak", "Dehghanian"])
        self.assertFalse(template_is_due(off, jdatetime.date(1405, 7, 1)))
        on = template_from_record(
            {
                "فعال": "TRUE",
                "تسک": "گزارش",
                "پروژه": "عمومی",
                "مسوول تسک": "Alfak",
                "اولویت": "High",
                "تکرارشوندگی": "ماهانه",
                "روز مبنا": "1",
                "مهلت (روز)": "5",
                "تاریخ شروع": "1405/07/01",
            },
            3,
        )
        self.assertTrue(template_is_due(on, jdatetime.date(1405, 7, 1)))
        self.assertFalse(template_is_due(on, jdatetime.date(1405, 6, 21)))


class KeyboardOverlapTests(unittest.TestCase):
    def test_admin_my_tasks_does_not_steal_employee_label(self) -> None:
        from bot.keyboards import ADMIN_MY_TASKS_TEXTS, MY_TASKS_TEXTS

        overlap = ADMIN_MY_TASKS_TEXTS & MY_TASKS_TEXTS
        self.assertFalse(
            overlap,
            f"shared menu texts would swallow employee taps: {overlap}",
        )

    def test_reply_menu_covers_main_buttons_not_announce(self) -> None:
        from bot.keyboards import (
            CANCEL_ANNOUNCE_BUTTON,
            CONFIRM_ANNOUNCE_BUTTON,
            CONTENT_BUTTON,
            CREATE_TASK_BUTTON,
            FILMING_BUTTON,
            IDEAS_BUTTON,
            MY_TASKS_BUTTON,
            OPEN_SHEET_BUTTON,
            REPORTS_BUTTON,
            REPLY_MENU_TEXTS,
            TEAM_TASKS_BUTTON,
        )

        for label in (
            CREATE_TASK_BUTTON,
            MY_TASKS_BUTTON,
            TEAM_TASKS_BUTTON,
            IDEAS_BUTTON,
            FILMING_BUTTON,
            CONTENT_BUTTON,
            OPEN_SHEET_BUTTON,
            REPORTS_BUTTON,
        ):
            self.assertIn(label, REPLY_MENU_TEXTS)
        self.assertNotIn(CONFIRM_ANNOUNCE_BUTTON, REPLY_MENU_TEXTS)
        self.assertNotIn(CANCEL_ANNOUNCE_BUTTON, REPLY_MENU_TEXTS)

    def test_due_date_callbacks_parse_and_fit_telegram_limit(self) -> None:
        from bot.keyboards import due_date_inline_keyboard

        kb = due_date_inline_keyboard()
        seen_manual = False
        seen_skip = False
        offsets: list[int] = []
        for row in kb.inline_keyboard:
            for btn in row:
                data = btn.callback_data
                if not data:
                    continue
                self.assertLessEqual(len(data.encode()), 64, data)
                if data == "duedate:manual":
                    seen_manual = True
                    continue
                if data == "skip:due_date":
                    seen_skip = True
                    continue
                if data.startswith("duedate:"):
                    offsets.append(int(data.split(":", 1)[1]))
        self.assertTrue(seen_manual)
        self.assertTrue(seen_skip)
        self.assertEqual(offsets, list(range(7)))

    def test_task_users_does_not_match_user_prefix(self) -> None:
        self.assertFalse("task:users".startswith("task:user:"))
        self.assertTrue("task:user:123".startswith("task:user:"))

    def test_status_callback_ids_split(self) -> None:
        film_id, film_status = "filming:12:in_progress".rsplit(":", 1)
        self.assertEqual(film_id, "filming:12")
        self.assertEqual(film_status, "in_progress")
        content_id, content_status = "design:3:done".rsplit(":", 1)
        self.assertEqual(content_id, "design:3")
        self.assertEqual(content_status, "done")
        task_id, task_status = "t:987654321:12:in_progress".rsplit(":", 1)
        self.assertEqual(task_id, "t:987654321:12")
        self.assertEqual(task_status, "in_progress")

    def test_filming_weekday_callbacks_fit(self) -> None:
        from bot.keyboards import filming_weekday_keyboard

        for row in filming_weekday_keyboard().inline_keyboard:
            for btn in row:
                if btn.callback_data:
                    self.assertLessEqual(len(btn.callback_data.encode()), 64, btn.callback_data)

    def test_cancel_flow_keyboard(self) -> None:
        from bot.keyboards import cancel_flow_keyboard

        kb = cancel_flow_keyboard("cancel:create_task")
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "cancel:create_task")


class SmsClientTests(unittest.TestCase):
    def test_html_to_plain_and_task_text(self) -> None:
        from services.sms import format_new_task_sms, html_to_plain

        self.assertEqual(html_to_plain("<b>سلام</b><br>جهان"), "سلام\nجهان")
        task = Task(
            sheet_name="Tasks",
            row_index=2,
            title="عنوان",
            project="عمومی",
            assignee_name="علی",
            created_by="مدیر",
            created_at="1405/01/01",
            due_date="1405/01/02",
            priority="High",
            status="pending",
            description="",
        )
        text = format_new_task_sms(task, creator_name="مدیر")
        self.assertIn("تسک جدید", text)
        self.assertIn("عنوان", text)
        self.assertNotIn("<b>", text)

    def test_post_sms_success(self) -> None:
        from unittest.mock import Mock, patch

        from services.sms import post_sms

        response = Mock()
        response.json.return_value = {"result": "1", "data": {"sendID": "77"}}
        response.text = ""
        with patch("services.sms.requests.post", return_value=response) as mocked:
            result = post_sms(
                api_key="secret",
                sender="auto",
                receivers="9120000000",
                text="hello",
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.send_id, "77")
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "secret")
        self.assertEqual(kwargs["data"]["action"], "send")
        self.assertEqual(kwargs["data"]["receivers"], "9120000000")

    def test_post_sms_skips_without_key(self) -> None:
        from services.sms import post_sms

        result = post_sms(api_key="", sender="auto", receivers="9120000000", text="x")
        self.assertTrue(result.skipped)
        self.assertFalse(result.ok)


class QuickTaskParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.employees = [
            Personnel(telegram_id=101, name="علی پور", role="employee", active=True),
            Personnel(telegram_id=102, name="شیخ", role="employee", active=True),
            Personnel(telegram_id=103, name="عیدانی", role="employee", active=True),
        ]
        self.projects = ["هما", "تبلیغات", "اینستاگرام"]

    def test_slash_quicktask_full(self) -> None:
        from bot.handlers.admin_tasks import parse_quick_task

        text = "/quicktask شیخ | هما | ساخت تیزر تبلیغاتی | فوری | فردا"
        res = parse_quick_task(text, self.employees, self.projects)
        self.assertIsNotNone(res)
        self.assertNotIn("error", res)
        self.assertEqual(res["employee"].name, "شیخ")
        self.assertEqual(res["project"], "هما")
        self.assertEqual(res["title"], "ساخت تیزر تبلیغاتی")
        self.assertEqual(res["priority"], "High")
        self.assertTrue(len(res["due_date"]) >= 8)

    def test_persian_prefix_quicktask(self) -> None:
        from bot.handlers.admin_tasks import parse_quick_task

        text = "ثبت تسک: علی پور | اینستاگرام | ادیت استوری هفتگی"
        res = parse_quick_task(text, self.employees, self.projects)
        self.assertIsNotNone(res)
        self.assertNotIn("error", res)
        self.assertEqual(res["employee"].name, "علی پور")
        self.assertEqual(res["project"], "اینستاگرام")
        self.assertEqual(res["title"], "ادیت استوری هفتگی")
        self.assertEqual(res["priority"], "Medium")

    def test_empty_quicktask(self) -> None:
        from bot.handlers.admin_tasks import parse_quick_task

        text = "/quicktask"
        res = parse_quick_task(text, self.employees, self.projects)
        self.assertIsNone(res)

    def test_incomplete_parts(self) -> None:
        from bot.handlers.admin_tasks import parse_quick_task

        text = "/quicktask علی پور | هما"
        res = parse_quick_task(text, self.employees, self.projects)
        self.assertIsNotNone(res)
        self.assertIn("error", res)

    def test_unknown_employee(self) -> None:
        from bot.handlers.admin_tasks import parse_quick_task

        text = "/quicktask ناشناس | هما | عنوان تسک"
        res = parse_quick_task(text, self.employees, self.projects)
        self.assertIsNotNone(res)
        self.assertIn("error", res)
        self.assertIn("ناشناس", res["error"])


class KeyboardsAndUXFeaturesTests(unittest.TestCase):
    def test_is_my_tasks_text(self) -> None:
        from bot.keyboards import is_my_tasks_text

        self.assertTrue(is_my_tasks_text("📌 تسک‌های من"))
        self.assertTrue(is_my_tasks_text("📌 تسک‌های من (۳)"))
        self.assertTrue(is_my_tasks_text("📌 تسک‌های من (12)"))
        self.assertFalse(is_my_tasks_text("تسک‌های دیگر"))

    def test_is_menu_text(self) -> None:
        from bot.keyboards import (
            BACK_TO_MAIN_MENU_BUTTON,
            SPECIAL_SECTIONS_BUTTON,
            is_menu_text,
        )

        self.assertTrue(is_menu_text("📌 تسک‌های من (۵)"))
        self.assertTrue(is_menu_text(SPECIAL_SECTIONS_BUTTON))
        self.assertTrue(is_menu_text(BACK_TO_MAIN_MENU_BUTTON))

    def test_main_menu_keyboard_with_badge(self) -> None:
        from bot.keyboards import SPECIAL_SECTIONS_BUTTON, main_menu_keyboard

        person = Personnel(telegram_id=1, name="علی", role="employee", active=True)
        kb = main_menu_keyboard(person, open_tasks_count=4)
        all_buttons = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn("📌 تسک‌های من (4)", all_buttons)
        self.assertIn(SPECIAL_SECTIONS_BUTTON, all_buttons)

    def test_special_sections_keyboard(self) -> None:
        from bot.keyboards import (
            BACK_TO_MAIN_MENU_BUTTON,
            special_sections_keyboard,
        )

        person = Personnel(telegram_id=1, name="علی", role="employee", active=True)
        kb = special_sections_keyboard(person)
        all_buttons = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn(BACK_TO_MAIN_MENU_BUTTON, all_buttons)

    def test_task_list_keyboard_quickdone_and_filter(self) -> None:
        from bot.keyboards import task_list_keyboard

        tasks = [
            Task(
                sheet_name="Tasks",
                row_index=2,
                title="تسک آزمایشی",
                project="پروژه ۱",
                assignee_name="علی",
                created_by="مدیر",
                created_at="1405/01/01",
                due_date="1405/01/02",
                priority="High",
                status="pending",
                description="توضیح کوتاه",
            ),
            Task(
                sheet_name="Tasks",
                row_index=3,
                title="تسک دوم",
                project="پروژه ۲",
                assignee_name="علی",
                created_by="مدیر",
                created_at="1405/01/01",
                due_date="1405/01/03",
                priority="Low",
                status="pending",
                description="",
            ),
            Task(
                sheet_name="Tasks",
                row_index=4,
                title="تسک سوم",
                project="پروژه ۳",
                assignee_name="علی",
                created_by="مدیر",
                created_at="1405/01/01",
                due_date="1405/01/04",
                priority="Medium",
                status="pending",
                description="",
            ),
        ]
        kb = task_list_keyboard(tasks, active_filter="all")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn("taskfilter:all", callbacks)
        self.assertIn("taskfilter:overdue", callbacks)
        self.assertIn("taskfilter:today", callbacks)
        # Verify task rows (after filter row) are single-column (one button per row)
        task_rows = kb.inline_keyboard[1:]
        self.assertEqual(len(task_rows), 3)
        for row in task_rows:
            self.assertEqual(len(row), 1)
            self.assertTrue(row[0].callback_data.startswith("task:view:"))

    def test_task_detail_keyboard_manager_and_notes(self) -> None:
        from bot.keyboards import task_detail_keyboard

        task = Task(
            sheet_name="Tasks",
            row_index=2,
            title="تسک آزمایشی",
            project="پروژه ۱",
            assignee_name="علی",
            created_by="مدیر",
            created_at="1405/01/01",
            due_date="1405/01/02",
            priority="High",
            status="pending",
            description="",
        )
        kb_employee = task_detail_keyboard(task, is_manager=False)
        cb_emp = [btn.callback_data for row in kb_employee.inline_keyboard for btn in row]
        self.assertTrue(any(cb and cb.startswith("task:note:") for cb in cb_emp))
        self.assertFalse(any(cb and cb.startswith("task:editdue:") for cb in cb_emp))

        kb_manager = task_detail_keyboard(task, is_manager=True)
        cb_mgr = [btn.callback_data for row in kb_manager.inline_keyboard for btn in row]
        self.assertTrue(any(cb and cb.startswith("task:editdue:") for cb in cb_mgr))
        self.assertTrue(any(cb and cb.startswith("task:editpri:") for cb in cb_mgr))

    def test_task_confirm_keyboard(self) -> None:
        from bot.keyboards import task_confirm_inline_keyboard

        kb = task_confirm_inline_keyboard()
        cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn("taskconfirm:yes", cbs)
        self.assertIn("taskconfirm:edittitle", cbs)
        self.assertIn("cancel:create_task", cbs)

    def test_format_task_detail_includes_description(self) -> None:
        from bot.handlers.employee_tasks import format_task_detail

        task = Task(
            sheet_name="Tasks",
            row_index=2,
            title="طراحی پوستر",
            project="هما",
            assignee_name="علی",
            created_by="مدیر",
            created_at="1405/01/01",
            due_date="1405/01/02",
            priority="High",
            status="pending",
            description="لینک فایل در درایو قرار دارد",
        )
        text = format_task_detail(task)
        self.assertIn("طراحی پوستر", text)
        self.assertIn("📝 توضیحات: لینک فایل در درایو قرار دارد", text)

    def test_is_my_tasks_text_matches_badges_and_variations(self) -> None:
        from bot.keyboards import is_my_tasks_text, is_done_tasks_text, is_team_tasks_text

        # Badges with count
        self.assertTrue(is_my_tasks_text("📌 تسک‌های من (3)"))
        self.assertTrue(is_my_tasks_text("📌 تسک‌های من (1)"))
        self.assertTrue(is_my_tasks_text("📌 تسک های من (12)"))
        self.assertTrue(is_my_tasks_text("📋 تسک‌های من (5)"))

        # Standard forms without count
        self.assertTrue(is_my_tasks_text("📌 تسک‌های من"))
        self.assertTrue(is_my_tasks_text("📋 تسک‌های من"))
        self.assertTrue(is_my_tasks_text("تسک‌های من"))
        self.assertTrue(is_my_tasks_text("تسک های من"))
        self.assertTrue(is_my_tasks_text("تسك هاي من"))  # Arabic kaf and yeh

        # Negative checks
        self.assertFalse(is_my_tasks_text("➕ ثبت تسک جدید"))
        self.assertFalse(is_my_tasks_text("👥 تسک‌های گروه"))
        self.assertFalse(is_my_tasks_text(None))
        self.assertFalse(is_my_tasks_text(""))

        # Done tasks matcher
        self.assertTrue(is_done_tasks_text("✅ تسک‌های انجام‌شده"))
        self.assertTrue(is_done_tasks_text("تسک‌های انجام شده"))
        self.assertTrue(is_done_tasks_text("تسک های انجام شده"))
        self.assertFalse(is_done_tasks_text("📌 تسک‌های من"))

        # Team tasks matcher
        self.assertTrue(is_team_tasks_text("👥 تسک‌های گروه"))
        self.assertTrue(is_team_tasks_text("تسک‌های تیم"))
        self.assertTrue(is_team_tasks_text("👥 همه تسک‌ها"))
        self.assertFalse(is_team_tasks_text("📌 تسک‌های من"))

    def test_defensive_date_parsing_handles_none_and_corrupt(self) -> None:
        from services.sheets_models import parse_due_as_jalali, validate_shamsi_date

        self.assertIsNone(validate_shamsi_date(None))
        self.assertIsNone(validate_shamsi_date(""))
        self.assertIsNone(validate_shamsi_date("bad-format"))
        self.assertIsNone(parse_due_as_jalali(None))
        self.assertIsNone(parse_due_as_jalali(""))
        self.assertIsNone(parse_due_as_jalali("not-a-date"))


if __name__ == "__main__":
    unittest.main()
