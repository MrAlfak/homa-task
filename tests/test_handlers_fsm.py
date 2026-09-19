"""Unit tests for FSM handlers and create-task flow logic."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.create_task_flow import FLOW_EXPIRED_TEXT
from bot.handlers.admin_tasks import (
    _flow_owned_by,
    _same_creator,
    _submit_lock,
    cancel_create_task,
    create_task_stale_callback,
    due_date_selected,
    priority_selected,
    receive_due_date_manual,
    receive_title,
)
from bot.states import CreateTaskStates


def _make_user(user_id: int = 123, name: str = "Admin") -> User:
    return User(id=user_id, is_bot=False, first_name=name)


def _make_message(text: str = "Hello", user_id: int = 123) -> Message:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_user(user_id)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = 456
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str = "btn:1", user_id: int = 123) -> CallbackQuery:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_user(user_id)
    cb.message = _make_message("Inline message", user_id=user_id)
    cb.answer = AsyncMock()
    return cb


class CreateTaskFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.storage = MemoryStorage()
        self.key = StorageKey(bot_id=1, chat_id=456, user_id=123)
        self.state = FSMContext(storage=self.storage, key=self.key)

    async def test_same_creator_check(self) -> None:
        self.assertTrue(_same_creator({"creator_id": 123}, 123))
        self.assertTrue(_same_creator({"creator_id": "123"}, 123))
        self.assertFalse(_same_creator({"creator_id": 123}, 999))
        self.assertFalse(_same_creator({}, 123))
        self.assertFalse(_same_creator({"creator_id": "invalid"}, 123))

    async def test_flow_owned_by(self) -> None:
        await self.state.update_data(creator_id=123)

        cb_owner = _make_callback(user_id=123)
        self.assertTrue(await _flow_owned_by(cb_owner, self.state))

        cb_stranger = _make_callback(user_id=999)
        self.assertFalse(await _flow_owned_by(cb_stranger, self.state))
        cb_stranger.answer.assert_awaited_once_with("دسترسی ندارید.", show_alert=True)

    async def test_cancel_create_task(self) -> None:
        await self.state.set_state(CreateTaskStates.entering_title)
        await self.state.update_data(creator_id=123, title="Old Title")

        cb = _make_callback(data="cancel:create_task", user_id=123)
        with patch("bot.handlers.admin_tasks.safe_edit_text", new_callable=AsyncMock) as mock_edit:
            await cancel_create_task(cb, self.state)

            cb.answer.assert_awaited_once()
            self.assertIsNone(await self.state.get_state())
            self.assertEqual(await self.state.get_data(), {})
            mock_edit.assert_awaited_once_with(cb.message, "❌ ثبت تسک لغو شد.")

    async def test_stale_callback_recovery(self) -> None:
        cb = _make_callback(data="duedate:1", user_id=123)
        with patch("bot.handlers.admin_tasks.safe_answer", new_callable=AsyncMock) as mock_answer:
            await create_task_stale_callback(cb, self.state)

            cb.answer.assert_awaited_once()
            self.assertIsNone(await self.state.get_state())
            mock_answer.assert_awaited_once_with(cb.message, FLOW_EXPIRED_TEXT)

    async def test_receive_title_validation(self) -> None:
        await self.state.set_state(CreateTaskStates.entering_title)
        await self.state.update_data(creator_id=123)

        # Title too short (< 2 chars)
        short_msg = _make_message(text="a", user_id=123)
        await receive_title(short_msg, self.state)
        short_msg.answer.assert_awaited_once_with("عنوان باید حداقل ۲ کاراکتر باشد:")
        self.assertEqual(await self.state.get_state(), CreateTaskStates.entering_title.state)

        # Valid title
        valid_msg = _make_message(text="بررسی طراحی جدید", user_id=123)
        await receive_title(valid_msg, self.state)
        data = await self.state.get_data()
        self.assertEqual(data.get("title"), "بررسی طراحی جدید")
        self.assertEqual(await self.state.get_state(), CreateTaskStates.choosing_priority.state)

    async def test_priority_selected(self) -> None:
        await self.state.set_state(CreateTaskStates.choosing_priority)
        await self.state.update_data(creator_id=123)

        cb = _make_callback(data="priority:High", user_id=123)
        with patch("bot.handlers.admin_tasks.safe_edit_text", new_callable=AsyncMock) as mock_edit:
            await priority_selected(cb, self.state)

            cb.answer.assert_awaited_once()
            data = await self.state.get_data()
            self.assertEqual(data.get("priority"), "High")
            self.assertEqual(await self.state.get_state(), CreateTaskStates.choosing_due_date.state)
            mock_edit.assert_awaited_once()

    async def test_due_date_manual_transition(self) -> None:
        await self.state.set_state(CreateTaskStates.choosing_due_date)
        await self.state.update_data(creator_id=123)

        cb = _make_callback(data="duedate:manual", user_id=123)
        with patch("bot.handlers.admin_tasks.safe_edit_text", new_callable=AsyncMock) as mock_edit:
            await due_date_selected(cb, self.state)

            cb.answer.assert_awaited_once()
            self.assertEqual(await self.state.get_state(), CreateTaskStates.entering_due_date_manual.state)
            mock_edit.assert_awaited_once()

    async def test_receive_due_date_manual_validation(self) -> None:
        await self.state.set_state(CreateTaskStates.entering_due_date_manual)
        await self.state.update_data(creator_id=123)

        # Invalid Jalali format
        bad_msg = _make_message(text="invalid-date", user_id=123)
        await receive_due_date_manual(bad_msg, self.state)
        bad_msg.answer.assert_awaited_once()
        self.assertIn("فرمت تاریخ نامعتبر است", bad_msg.answer.await_args[0][0])
        self.assertEqual(await self.state.get_state(), CreateTaskStates.entering_due_date_manual.state)

        # Slash command cancels
        cmd_msg = _make_message(text="/cancel", user_id=123)
        await receive_due_date_manual(cmd_msg, self.state)
        cmd_msg.answer.assert_awaited_once_with("❌ ثبت تسک لغو شد.")
        self.assertIsNone(await self.state.get_state())

    async def test_submit_lock_per_user(self) -> None:
        lock1 = _submit_lock(100)
        lock2 = _submit_lock(100)
        lock3 = _submit_lock(200)

        # Same user gets same lock instance
        self.assertIs(lock1, lock2)
        # Different user gets different lock instance
        self.assertIsNot(lock1, lock3)


if __name__ == "__main__":
    unittest.main()
