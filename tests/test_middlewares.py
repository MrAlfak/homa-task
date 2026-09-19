"""Unit tests for bot middlewares."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.keyboards import CREATE_TASK_BUTTON, MY_TASKS_BUTTON
from bot.middlewares.dedupe import DuplicateTapMiddleware
from bot.middlewares.errors import UserErrorMiddleware
from bot.middlewares.feedback import InstantFeedbackMiddleware
from bot.middlewares.menu_reset import MenuResetMiddleware


def _make_user(user_id: int = 123, name: str = "Test User") -> User:
    return User(id=user_id, is_bot=False, first_name=name)


def _make_message(text: str = "Hello", user_id: int = 123, chat_id: int = 456) -> Message:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_user(user_id)
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    return msg


def _make_callback(data: str = "btn:1", user_id: int = 123) -> CallbackQuery:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_user(user_id)
    cb.answer = AsyncMock()
    return cb


class MenuResetMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_clears_fsm_on_menu_text(self) -> None:
        middleware = MenuResetMiddleware()
        mock_state = AsyncMock()
        mock_state.get_state.return_value = "CreateTaskStates:entering_title"

        handler = AsyncMock(return_value="handled")
        message = _make_message(text=MY_TASKS_BUTTON)

        result = await middleware(handler, message, {"state": mock_state})
        self.assertEqual(result, "handled")
        mock_state.clear.assert_awaited_once()

    async def test_clears_fsm_on_create_task_button(self) -> None:
        middleware = MenuResetMiddleware()
        mock_state = AsyncMock()
        mock_state.get_state.return_value = "SomeState:step"

        handler = AsyncMock(return_value="handled")
        message = _make_message(text=CREATE_TASK_BUTTON)

        result = await middleware(handler, message, {"state": mock_state})
        self.assertEqual(result, "handled")
        mock_state.clear.assert_awaited_once()

    async def test_preserves_fsm_on_arbitrary_text(self) -> None:
        middleware = MenuResetMiddleware()
        mock_state = AsyncMock()
        mock_state.get_state.return_value = "CreateTaskStates:entering_title"

        handler = AsyncMock(return_value="handled")
        message = _make_message(text="طراحی لوگوی جدید برای پروژه")

        result = await middleware(handler, message, {"state": mock_state})
        self.assertEqual(result, "handled")
        mock_state.clear.assert_not_awaited()


class DuplicateTapMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_drops_fast_duplicate_message(self) -> None:
        middleware = DuplicateTapMiddleware(window_seconds=1.0)
        handler = AsyncMock(return_value="ok")
        msg = _make_message(text="hello", user_id=100)

        # First execution passes
        res1 = await middleware(handler, msg, {})
        self.assertEqual(res1, "ok")
        self.assertEqual(handler.await_count, 1)

        # Second identical message within window is dropped
        res2 = await middleware(handler, msg, {})
        self.assertIsNone(res2)
        self.assertEqual(handler.await_count, 1)

    async def test_drops_fast_duplicate_callback(self) -> None:
        middleware = DuplicateTapMiddleware(window_seconds=1.0)
        handler = AsyncMock(return_value="ok")
        cb = _make_callback(data="task:12", user_id=200)

        res1 = await middleware(handler, cb, {})
        self.assertEqual(res1, "ok")

        res2 = await middleware(handler, cb, {})
        self.assertIsNone(res2)
        cb.answer.assert_awaited()

    async def test_user_busy_lock_prevents_concurrent_runs(self) -> None:
        middleware = DuplicateTapMiddleware(window_seconds=0.1)

        started = asyncio.Event()
        finish = asyncio.Event()

        async def slow_handler(event, data):
            started.set()
            await finish.wait()
            return "slow_done"

        msg1 = _make_message(text="tap 1", user_id=300)
        msg2 = _make_message(text="tap 2", user_id=300)

        task1 = asyncio.create_task(middleware(slow_handler, msg1, {}))
        await started.wait()

        # While task 1 is running, second message from same user is dropped
        res2 = await middleware(slow_handler, msg2, {})
        self.assertIsNone(res2)
        msg2.answer.assert_awaited()

        finish.set()
        res1 = await task1
        self.assertEqual(res1, "slow_done")

        # After task 1 finishes, user is no longer busy
        quick_handler = AsyncMock(return_value="quick_done")
        msg3 = _make_message(text="tap 3", user_id=300)
        res3 = await middleware(quick_handler, msg3, {})
        self.assertEqual(res3, "quick_done")


class UserErrorMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_exception_sends_polite_response(self) -> None:
        middleware = UserErrorMiddleware()

        async def broken_handler(event, data):
            raise RuntimeError("Database connection failed")

        msg = _make_message()
        result = await middleware(broken_handler, msg, {})
        self.assertIsNone(result)
        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args[0][0]
        self.assertIn("خطایی رخ داد", sent_text)

    async def test_callback_exception_alerts_user(self) -> None:
        middleware = UserErrorMiddleware()

        async def broken_handler(event, data):
            raise ValueError("Invalid state")

        cb = _make_callback()
        result = await middleware(broken_handler, cb, {})
        self.assertIsNone(result)
        cb.answer.assert_awaited_once_with("خطا رخ داد. دوباره تلاش کنید.", show_alert=True)


class InstantFeedbackMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_triggers_typing_action(self) -> None:
        middleware = InstantFeedbackMiddleware()
        bot = AsyncMock()
        msg = _make_message(chat_id=999)

        handler = AsyncMock(return_value="handled")
        await middleware(handler, msg, {"bot": bot})

        # Allow background task to run
        await asyncio.sleep(0.01)
        bot.send_chat_action.assert_awaited_once_with(999, ChatAction.TYPING)


if __name__ == "__main__":
    unittest.main()
