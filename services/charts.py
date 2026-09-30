"""PNG task reports for Telegram (Vazirmatn)."""

from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path

import arabic_reshaper
import jdatetime
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from bidi.algorithm import get_display
from matplotlib import font_manager

from config import BASE_DIR
from services.sheets_models import (
    PERSIAN_MONTHS,
    Task,
    normalize_name,
    parse_due_as_jalali,
    shamsi_today,
    tehran_today,
    to_persian_display_name,
    validate_shamsi_date,
)

STATUS_FA = {
    "pending": "در انتظار",
    "in_progress": "در حال انجام",
    "done": "انجام شده",
    "cancelled": "لغو شده",
}
STATUS_ORDER = ("pending", "in_progress", "done", "cancelled")
STATUS_COLORS = {
    "pending": "#e6b325",
    "in_progress": "#3b82c4",
    "done": "#3f9b6e",
    "cancelled": "#c45c5c",
}
BG = "#f7f4ee"
FG = "#1f2933"
MUTED = "#64748b"
MAX_BARS = 12
MAX_PEOPLE_BARS = 16
PENDING_COLOR = "#e6b325"
PROGRESS_COLOR = "#3b82c4"
OVERDUE_COLOR = "#d15b5b"

_FONT_CANDIDATES = (
    BASE_DIR / "assets" / "fonts" / "Vazirmatn-UI-FD-Regular.ttf",
    Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Vazirmatn-UI-FD-Regular.ttf",
    Path.home() / "Library/Fonts/Vazirmatn-UI-FD-Regular.ttf",
    Path.home() / "Library/Fonts/Vazirmatn-Regular.ttf",
)


def _font() -> font_manager.FontProperties | None:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return font_manager.FontProperties(fname=str(path))
    return None


def fa(text: object) -> str:
    return get_display(arabic_reshaper.reshape(str(text)), base_dir="R")


def _open_tasks(tasks: list[Task]) -> list[Task]:
    return [task for task in tasks if task.status not in {"done", "cancelled"}]


def _created_month(task: Task) -> tuple[int, int] | None:
    normalized = validate_shamsi_date(task.created_at)
    if not normalized:
        return None
    year, month, _day = (int(part) for part in normalized.split("/"))
    return year, month


def _task_month(task: Task) -> tuple[int, int] | None:
    res = _created_month(task)
    if res is not None:
        return res
    due = parse_due_as_jalali(task.due_date)
    if due is not None:
        return (due.year, due.month)
    return None


def render_report(kind: str, tasks: list[Task], *, kinds: tuple[str, ...] | None = None) -> bytes:
    """Return a PNG for one report kind. ``summary`` tiles the given kinds."""
    font = _font()
    plt.rcParams["axes.unicode_minus"] = False
    today = tehran_today()
    today_str, _month = shamsi_today()
    if kind == "summary":
        panels = [item for item in (kinds or ("status", "people", "project", "deadline")) if item != "summary"]
        if not panels:
            panels = ["status"]
        return _render_grid(panels, tasks, today, today_str, font)
    height = 6.8
    if kind == "people":
        people = {to_persian_display_name(normalize_name(task.assignee_name)).strip() or "بدون مسئول" for task in _open_tasks(tasks)}
        height = max(7.2, 0.48 * min(MAX_PEOPLE_BARS, max(1, len(people))) + 3.2)
    elif kind == "project":
        projects = {task.project.strip() or "بدون پروژه" for task in _open_tasks(tasks)}
        height = max(6.8, 0.48 * min(MAX_BARS, max(1, len(projects))) + 3.0)
    fig, ax = plt.subplots(figsize=(11.6, height), facecolor=BG)
    ax.set_facecolor(BG)
    _draw_kind(ax, kind, tasks, today, font)
    fig.suptitle(fa(_title(kind, today_str)), fontproperties=font, fontsize=16, color=FG, y=0.98)
    fig.text(0.97, 0.03, fa(_footer(tasks, today)), ha="right", fontproperties=font, fontsize=9, color=MUTED)
    right = 0.78 if kind in {"people", "project"} else 0.96
    fig.tight_layout(rect=(0.04, 0.08, right, 0.92))
    return _to_png(fig)


def _render_grid(
    panels: list[str],
    tasks: list[Task],
    today: jdatetime.date,
    today_str: str,
    font: font_manager.FontProperties | None,
) -> bytes:
    count = len(panels)
    cols = 2 if count > 1 else 1
    rows = (count + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(13.2, 4.8 * rows + 1.2), facecolor=BG)
    flat = [axes] if count == 1 else list(axes.ravel()) if hasattr(axes, "ravel") else [axes]
    fig.suptitle(fa(f"خلاصه گزارش  ·  {today_str}"), fontproperties=font, fontsize=16, color=FG, y=0.99)
    for index, kind in enumerate(panels):
        ax = flat[index]
        ax.set_facecolor(BG)
        _draw_kind(ax, kind, tasks, today, font)
        ax.set_title(fa(_short_title(kind)), fontproperties=font, fontsize=12, color="#334155", pad=28, loc="right")
    for extra in flat[len(panels) :]:
        extra.axis("off")
        extra.set_facecolor(BG)
    fig.text(0.97, 0.02, fa(_footer(tasks, today)), ha="right", fontproperties=font, fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0.04, 0.06, 0.88, 0.93))
    return _to_png(fig)


def _title(kind: str, today_str: str) -> str:
    mapping = {
        "status": "وضعیت کل تسک‌ها",
        "people": "تسک باز هر نفر (در انتظار / در حال انجام / عقب‌افتاده)",
        "project": "تسک باز به تفکیک پروژه",
        "deadline": "ددلاین و عقب‌افتاده",
        "month": "مقایسه این ماه و ماه قبل",
        "summary": "خلاصه هفتگی",
    }
    return f"{mapping.get(kind, kind)}  ·  {today_str}"


def _short_title(kind: str) -> str:
    return {
        "status": "وضعیت کل",
        "people": "نفرات · تسک باز",
        "project": "پروژه",
        "deadline": "ددلاین",
        "month": "ماه",
    }.get(kind, kind)


def _footer(tasks: list[Task], today: jdatetime.date) -> str:
    opened = _open_tasks(tasks)
    overdue = 0
    for task in opened:
        due = parse_due_as_jalali(task.due_date)
        if due is not None and due < today:
            overdue += 1
    done = sum(1 for task in tasks if task.status == "done")
    return f"جمع {len(tasks)}  ·  باز {len(opened)}  ·  انجام‌شده {done}  ·  عقب‌افتاده {overdue}"


def _draw_kind(
    ax,
    kind: str,
    tasks: list[Task],
    today: jdatetime.date,
    font: font_manager.FontProperties | None,
) -> None:
    if kind == "status":
        _draw_status(ax, tasks, font)
    elif kind == "people":
        _draw_people(ax, tasks, today, font)
    elif kind == "project":
        _draw_named_bars(ax, _count_open_and_overdue(tasks, today, "project"), font)
    elif kind == "deadline":
        _draw_deadline(ax, tasks, today, font)
    elif kind == "month":
        _draw_month(ax, tasks, today, font)
    else:
        ax.axis("off")


def _rtl_barh(ax) -> None:
    ax.yaxis.tick_right()
    ax.yaxis.set_ticks_position("right")
    if not ax.xaxis_inverted():
        ax.invert_xaxis()
    ax.tick_params(axis="y", length=0, pad=6)
    ax.tick_params(axis="x", colors=MUTED)
    for spine in ("top", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["right"].set_color("#d6d3cd")
    ax.spines["bottom"].set_color("#d6d3cd")


def _draw_status(ax, tasks: list[Task], font: font_manager.FontProperties | None) -> None:
    counts = Counter(task.status for task in tasks)
    sizes = [counts.get(key, 0) for key in STATUS_ORDER]
    colors = [STATUS_COLORS[key] for key in STATUS_ORDER]
    total = sum(sizes)
    if total == 0:
        sizes = [1]
        colors = ["#d6d3cd"]
        wedges, *_rest = ax.pie(
            sizes,
            colors=colors,
            startangle=90,
            counterclock=False,
            center=(-0.2, 0.0),
            wedgeprops={"linewidth": 2, "edgecolor": BG},
        )
        labels = [fa(f"{STATUS_FA[key]}: 0") for key in STATUS_ORDER]
    else:
        wedges, *_rest = ax.pie(
            sizes,
            colors=colors,
            startangle=90,
            counterclock=False,
            center=(-0.2, 0.0),
            wedgeprops={"linewidth": 2, "edgecolor": BG},
        )
        labels = [
            fa(f"{STATUS_FA[key]}: {counts.get(key, 0)} ({round(counts.get(key, 0) / total * 100)}٪)")
            for key in STATUS_ORDER
        ]
    ax.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(0.90, 0.5),
        prop=font,
        frameon=False,
        labelspacing=0.9,
    )


def _count_open_and_overdue(tasks: list[Task], today: jdatetime.date, field: str) -> list[tuple[str, int, int]]:
    opened: Counter[str] = Counter()
    overdue: Counter[str] = Counter()
    for task in _open_tasks(tasks):
        if field == "assignee":
            raw_name = to_persian_display_name(normalize_name(task.assignee_name)).strip()
            name = raw_name or "بدون مسئول"
        else:
            name = task.project.strip() or "بدون پروژه"
        opened[name] += 1
        due = parse_due_as_jalali(task.due_date)
        if due is not None and due < today:
            overdue[name] += 1
    ranked = opened.most_common(MAX_BARS)
    rest_open = sum(count for name, count in opened.items() if name not in {item[0] for item in ranked})
    rest_overdue = sum(count for name, count in overdue.items() if name not in {item[0] for item in ranked})
    rows = [(name, opened[name], overdue.get(name, 0)) for name, _count in ranked]
    if rest_open:
        rows.append(("سایر", rest_open, rest_overdue))
    return rows


def _count_people_open(tasks: list[Task], today: jdatetime.date) -> list[tuple[str, int, int, int]]:
    pending: Counter[str] = Counter()
    progress: Counter[str] = Counter()
    overdue: Counter[str] = Counter()
    for task in _open_tasks(tasks):
        name = to_persian_display_name(normalize_name(task.assignee_name)).strip() or "بدون مسئول"
        due = parse_due_as_jalali(task.due_date)
        if due is not None and due < today:
            overdue[name] += 1
        elif task.status == "in_progress":
            progress[name] += 1
        else:
            pending[name] += 1
    totals = Counter()
    for bag in (pending, progress, overdue):
        totals.update(bag)
    ranked = totals.most_common(MAX_PEOPLE_BARS)
    used = {name for name, _count in ranked}
    rest = (
        sum(pending[name] for name in pending if name not in used),
        sum(progress[name] for name in progress if name not in used),
        sum(overdue[name] for name in overdue if name not in used),
    )
    rows = [
        (name, pending.get(name, 0), progress.get(name, 0), overdue.get(name, 0))
        for name, _count in ranked
    ]
    if sum(rest):
        rows.append(("سایر", rest[0], rest[1], rest[2]))
    return rows


def _draw_people(ax, tasks: list[Task], today: jdatetime.date, font: font_manager.FontProperties | None) -> None:
    rows = _count_people_open(tasks, today)
    if not rows:
        ax.text(0.5, 0.5, fa("تسک بازی نیست"), ha="center", va="center", fontproperties=font, color=MUTED)
        ax.axis("off")
        return
    labels = []
    pending_vals: list[int] = []
    progress_vals: list[int] = []
    overdue_vals: list[int] = []
    for name, pending, progress, overdue in rows:
        total = pending + progress + overdue
        if overdue:
            labels.append(f"{name}: {total} باز ({overdue} عقب‌افتاده)")
        else:
            labels.append(f"{name}: {total} باز")
        pending_vals.append(pending)
        progress_vals.append(progress)
        overdue_vals.append(overdue)
    y = list(range(len(labels)))[::-1]
    ax.barh(y, pending_vals, color=PENDING_COLOR, height=0.62, label=fa("در انتظار"))
    ax.barh(
        y,
        progress_vals,
        left=pending_vals,
        color=PROGRESS_COLOR,
        height=0.62,
        label=fa("در حال انجام"),
    )
    left_overdue = [p + g for p, g in zip(pending_vals, progress_vals)]
    ax.barh(
        y,
        overdue_vals,
        left=left_overdue,
        color=OVERDUE_COLOR,
        height=0.62,
        label=fa("عقب‌افتاده"),
    )
    totals = [p + g + o for p, g, o in zip(pending_vals, progress_vals, overdue_vals)]
    ax.set_yticks(y)
    ax.set_yticklabels([fa(label) for label in labels], fontproperties=font, fontsize=9)
    max_total = max(totals) if totals else 1
    ax.set_xlim(max_total * 1.15 + 0.5, 0)
    for index, total in enumerate(totals):
        ax.text(
            total + max_total * 0.02 + 0.15,
            y[index],
            str(total),
            va="center",
            ha="right",
            fontsize=8,
            color=MUTED,
        )
    ax.legend(prop=font, frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=3)
    ax.set_xlabel(fa("تعداد تسک باز"), fontproperties=font, color=MUTED, loc="right")
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    _rtl_barh(ax)


def _draw_named_bars(ax, rows: list[tuple[str, int, int]], font: font_manager.FontProperties | None) -> None:
    if not rows:
        ax.text(0.5, 0.5, fa("داده‌ای نیست"), ha="center", va="center", fontproperties=font, color=MUTED)
        ax.axis("off")
        return
    names = [row[0] for row in rows]
    open_counts = [row[1] for row in rows]
    overdue_counts = [row[2] for row in rows]
    y = list(range(len(names)))[::-1]
    still_open = [max(0, total - late) for total, late in zip(open_counts, overdue_counts)]
    ax.barh(y, still_open, color="#5b8def", height=0.62, label=fa("باز و به‌موقع"))
    ax.barh(y, overdue_counts, left=still_open, color=OVERDUE_COLOR, height=0.62, label=fa("عقب‌افتاده"))
    ax.set_yticks(y)
    labels = []
    for name, count, late in zip(names, open_counts, overdue_counts):
        display_name = name[:20] + "…" if len(name) > 20 else name
        if late:
            labels.append(f"{display_name}: {count} باز ({late} عقب‌افتاده)")
        else:
            labels.append(f"{display_name}: {count} باز")
    ax.set_yticklabels([fa(label) for label in labels], fontproperties=font, fontsize=9)
    max_open = max(open_counts) if open_counts else 1
    ax.set_xlim(max_open * 1.15 + 0.5, 0)
    for index, count in enumerate(open_counts):
        ax.text(
            count + max_open * 0.02 + 0.15,
            y[index],
            str(count),
            va="center",
            ha="right",
            fontsize=8,
            color=MUTED,
        )
    ax.legend(prop=font, frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    _rtl_barh(ax)


def _draw_deadline(ax, tasks: list[Task], today: jdatetime.date, font: font_manager.FontProperties | None) -> None:
    buckets = Counter()
    week_end = today + jdatetime.timedelta(days=7)
    for task in _open_tasks(tasks):
        due = parse_due_as_jalali(task.due_date)
        if due is None:
            buckets["بدون‌ددلاین"] += 1
        elif due < today:
            buckets["عقب‌افتاده"] += 1
        elif due == today:
            buckets["امروز"] += 1
        elif due <= week_end:
            buckets["تا ۷ روز"] += 1
        else:
            buckets["بعداً"] += 1
    labels = ["عقب‌افتاده", "امروز", "تا ۷ روز", "بعداً", "بدون‌ددلاین"]
    colors = [OVERDUE_COLOR, "#e6b325", "#5b8def", "#3f9b6e", "#94a3b8"]
    values = [buckets.get(label, 0) for label in labels]
    x = list(range(len(labels)))
    ax.bar(x, values, color=colors, width=0.72)
    ax.set_xticks(x)
    ax.set_xticklabels([fa(label) for label in labels], fontproperties=font, fontsize=9)
    peak = max(values) if values else 1
    ax.set_ylim(0, max(peak * 1.25, 4))
    for index, value in enumerate(values):
        if value > 0:
            ax.text(index, value + max(peak * 0.03, 0.1), str(value), ha="center", fontsize=8, color=MUTED)
    if not ax.xaxis_inverted():
        ax.invert_xaxis()
    for spine in ("top", "left"):
        ax.spines[spine].set_visible(False)
    ax.yaxis.tick_right()
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.tick_params(axis="y", colors=MUTED)


def _draw_month(ax, tasks: list[Task], today: jdatetime.date, font: font_manager.FontProperties | None) -> None:
    this_key = (today.year, today.month)
    prev = today.month - 1
    prev_key = (today.year if prev else today.year - 1, prev if prev else 12)
    this_open = this_done = prev_open = prev_done = 0
    for task in tasks:
        month_key = _task_month(task)
        if month_key == this_key:
            if task.status == "done":
                this_done += 1
            elif task.status != "cancelled":
                this_open += 1
        elif month_key == prev_key:
            if task.status == "done":
                prev_done += 1
            elif task.status != "cancelled":
                prev_open += 1
    labels = [
        fa(PERSIAN_MONTHS[prev_key[1] - 1]),
        fa(PERSIAN_MONTHS[this_key[1] - 1]),
    ]
    x = [0, 1]
    ax.bar([i - 0.18 for i in x], [prev_open, this_open], width=0.36, color="#5b8def", label=fa("باز / در جریان"))
    ax.bar([i + 0.18 for i in x], [prev_done, this_done], width=0.36, color="#3f9b6e", label=fa("انجام‌شده"))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontproperties=font)
    ax.legend(prop=font, frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2)
    if not ax.xaxis_inverted():
        ax.invert_xaxis()
    ax.yaxis.tick_right()
    for spine in ("top", "left"):
        ax.spines[spine].set_visible(False)
    peak = max(prev_open, this_open, prev_done, this_done)
    ax.set_ylim(0, max(peak * 1.25, 4))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.tick_params(axis="y", colors=MUTED)
    vals = [prev_open, this_open, prev_done, this_done]
    x_positions = [-0.18, 1 - 0.18, 0.18, 1 + 0.18]
    for x_pos, val in zip(x_positions, vals):
        if val > 0:
            ax.text(x_pos, val + max(peak * 0.03, 0.1), str(val), ha="center", fontsize=8, color=MUTED)


def _to_png(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buffer.getvalue()
