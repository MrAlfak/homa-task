"""One-off: render a task chart from Sheets and send it to Alfak's Telegram PV."""

from __future__ import annotations

import os
from collections import Counter
from io import BytesIO
from pathlib import Path

import arabic_reshaper
import jdatetime
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bidi.algorithm import get_display
from dotenv import load_dotenv
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
import sys

sys.path.insert(0, str(ROOT))

CHAT_ID = 114848224
FONT_PATH = Path.home() / "Library/Fonts/Vazirmatn-UI-FD-Regular.ttf"
STATUS_FA = {
    "pending": "در انتظار",
    "in_progress": "در حال انجام",
    "done": "انجام شده",
    "cancelled": "لغو شده",
}


def fa(text: str) -> str:
    return get_display(arabic_reshaper.reshape(str(text)))


def main() -> None:
    os.chdir(ROOT)
    from services.sheets import get_sheets_service
    from services.sheets_models import normalize_status, parse_due_as_jalali, shamsi_today
    import requests

    svc = get_sheets_service()
    values = svc._tasks_ws.get_all_values()
    headers = [str(h).strip() for h in values[0]]
    today = jdatetime.date.today()
    today_str, _month = shamsi_today()

    statuses: Counter[str] = Counter()
    open_by_person: Counter[str] = Counter()
    overdue_by_person: Counter[str] = Counter()
    total = 0
    for row in values[1:]:
        record = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        title = str(record.get("تسک", "")).strip()
        if not title:
            continue
        total += 1
        status = normalize_status(str(record.get("وضعیت", "")).strip())
        statuses[status] += 1
        assignee = str(record.get("مسوول تسک", record.get("i", ""))).strip() or "—"
        if status not in {"done", "cancelled"}:
            open_by_person[assignee] += 1
            due = parse_due_as_jalali(str(record.get("ددلاین", "")))
            if due is not None and due < today:
                overdue_by_person[assignee] += 1

    font = font_manager.FontProperties(fname=str(FONT_PATH)) if FONT_PATH.is_file() else None
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 6.4), facecolor="#f7f4ee")
    fig.suptitle(
        fa(f"گزارش تسک‌ها  ·  {today_str}"),
        fontproperties=font,
        fontsize=16,
        color="#1f2933",
        y=0.98,
    )

    order = ["pending", "in_progress", "done", "cancelled"]
    colors = ["#e6b325", "#3b82c4", "#3f9b6e", "#c45c5c"]
    labels = [fa(STATUS_FA[key]) for key in order]
    sizes = [statuses.get(key, 0) for key in order]
    ax0 = axes[0]
    ax0.set_facecolor("#f7f4ee")
    wedges, *_rest = ax0.pie(
        sizes if sum(sizes) else [1],
        colors=colors,
        startangle=90,
        wedgeprops={"linewidth": 2, "edgecolor": "#f7f4ee"},
    )
    ax0.set_title(fa("وضعیت کل"), fontproperties=font, fontsize=12, color="#334155", pad=12)
    legend_labels = [fa(f"{STATUS_FA[key]}  {statuses.get(key, 0)}") for key in order]
    ax0.legend(
        wedges,
        legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.18),
        prop=font,
        frameon=False,
    )

    ax1 = axes[1]
    ax1.set_facecolor("#f7f4ee")
    people = [name for name, _count in open_by_person.most_common(8)]
    open_counts = [open_by_person[name] for name in people]
    overdue_counts = [overdue_by_person.get(name, 0) for name in people]
    y = list(range(len(people)))[::-1]
    ax1.barh(y, open_counts, color="#5b8def", height=0.62, label=fa("باز"))
    ax1.barh(y, overdue_counts, color="#d15b5b", height=0.32, label=fa("عقب‌افتاده"))
    ax1.set_yticks(y)
    ax1.set_yticklabels([fa(name) for name in people], fontproperties=font)
    ax1.set_title(fa("تسک باز به تفکیک نفر"), fontproperties=font, fontsize=12, color="#334155", pad=12)
    ax1.tick_params(axis="x", colors="#64748b")
    ax1.legend(prop=font, frameon=False, loc="lower right")
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)
    ax1.spines["left"].set_color("#d6d3cd")
    ax1.spines["bottom"].set_color("#d6d3cd")

    fig.text(
        0.5,
        0.04,
        fa(f"جمع کل {total} تسک در تب Tasks  ·  تست نمودار ربات هما"),
        ha="center",
        fontproperties=font,
        fontsize=9,
        color="#64748b",
    )
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.92))

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)
    png = buffer.getvalue()
    out = Path("/tmp/homa-task-chart.png")
    out.write_bytes(png)

    caption = (
        f"📊 تست نمودار تسک‌ها\n"
        f"تاریخ: {today_str}\n"
        f"کل: {total}  |  باز: {sum(open_counts)}  |  عقب‌افتاده: {sum(overdue_by_person.values())}"
    )
    token = os.environ["BOT_TOKEN"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data={"chat_id": CHAT_ID, "caption": caption},
        files={"photo": ("tasks.png", png, "image/png")},
        timeout=30,
    )
    body = response.json()
    print("file", out, "bytes", len(png))
    print("telegram_ok", body.get("ok"), "desc", body.get("description"), "msg_id", (body.get("result") or {}).get("message_id"))
    if not body.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
