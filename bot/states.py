"""FSM states for multi-step conversations."""

from aiogram.fsm.state import State, StatesGroup


class CreateTaskStates(StatesGroup):
    """Admin flow aligned with the Google Sheet columns."""

    choosing_employee = State()
    choosing_project = State()
    entering_title = State()
    choosing_priority = State()
    choosing_due_date = State()
    entering_due_date_manual = State()


class IdeaStates(StatesGroup):
    """Submit a new idea."""

    entering_idea = State()


class AnnounceStates(StatesGroup):
    """Senior admin group broadcast confirmation."""

    waiting_confirm = State()


class FilmingStates(StatesGroup):
    """Create a تصویر برداری schedule row."""

    choosing_project = State()
    entering_location = State()
    choosing_day = State()
    entering_hour = State()
    choosing_date = State()
    entering_date_manual = State()
    choosing_assignee = State()


class ContentStates(StatesGroup):
    """Create a Design (تولید محتوا) row: نام → پروژه → پست/استوری."""

    choosing_person = State()
    choosing_project = State()
    choosing_type = State()
