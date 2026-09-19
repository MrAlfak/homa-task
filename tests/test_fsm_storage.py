"""Unit tests for JSON-file FSM storage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey

from bot.fsm_storage import JsonFileStorage


class SampleStates(StatesGroup):
    step1 = State()
    step2 = State()


class JsonFileStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = Path(self.temp_dir.name) / "fsm_data.json"
        self.storage = JsonFileStorage(self.file_path)
        self.key = StorageKey(
            bot_id=123456,
            chat_id=111,
            user_id=222,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_set_and_get_state(self) -> None:
        # Initially None
        state = await self.storage.get_state(self.key)
        self.assertIsNone(state)

        # Set string state
        await self.storage.set_state(self.key, "SampleStates:step1")
        state = await self.storage.get_state(self.key)
        self.assertEqual(state, "SampleStates:step1")

        # Set aiogram State object
        await self.storage.set_state(self.key, SampleStates.step2)
        state = await self.storage.get_state(self.key)
        self.assertEqual(state, "SampleStates:step2")

        # Clear state (set to None)
        await self.storage.set_state(self.key, None)
        state = await self.storage.get_state(self.key)
        self.assertIsNone(state)

    async def test_set_and_get_data(self) -> None:
        data = await self.storage.get_data(self.key)
        self.assertEqual(data, {})

        await self.storage.set_data(self.key, {"title": "Task 1", "count": 5})
        data = await self.storage.get_data(self.key)
        self.assertEqual(data, {"title": "Task 1", "count": 5})

        # update_data merges dictionary
        updated = await self.storage.update_data(self.key, {"count": 6, "priority": "High"})
        self.assertEqual(updated, {"title": "Task 1", "count": 6, "priority": "High"})

        data = await self.storage.get_data(self.key)
        self.assertEqual(data, {"title": "Task 1", "count": 6, "priority": "High"})

    async def test_persistence_across_instances(self) -> None:
        await self.storage.set_state(self.key, SampleStates.step1)
        await self.storage.set_data(self.key, {"key1": "val1"})

        # Create brand new instance with same file path
        new_storage = JsonFileStorage(self.file_path)
        self.assertEqual(await new_storage.get_state(self.key), "SampleStates:step1")
        self.assertEqual(await new_storage.get_data(self.key), {"key1": "val1"})

    async def test_corrupt_json_file_handled_gracefully(self) -> None:
        # Write corrupted JSON to file
        self.file_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        corrupt_storage = JsonFileStorage(self.file_path)
        state = await corrupt_storage.get_state(self.key)
        self.assertIsNone(state)
        data = await corrupt_storage.get_data(self.key)
        self.assertEqual(data, {})

        # Can recover and write valid JSON again
        await corrupt_storage.set_state(self.key, SampleStates.step2)
        self.assertEqual(await corrupt_storage.get_state(self.key), "SampleStates:step2")
        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        self.assertIsInstance(raw, dict)


if __name__ == "__main__":
    unittest.main()
