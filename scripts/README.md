# اسکریپت‌های مدیریت و عملیات Homa Task

این پوشه شامل ابزارها و اسکریپت‌های کمکی برای مدیریت ربات و عملیات سرور است:

## اسکریپت‌های اصلی (`scripts/`)

- **`broadcast_local.py`**: ارسال پیام اطلاعیه / بروزرسانی چنج‌لاگ به کاربران تلگرام و پیامک به صورت مستقیم با استفاده از توکن ربات و داده‌های Google Sheet.
  ```bash
  python scripts/broadcast_local.py --dry-run
  python scripts/broadcast_local.py --send
  ```
- **`send_group_announcement.py`**: ارسال پیام اطلاعیه به گروه تلگرام تعریف‌شده در `GROUP_CHAT_ID`.
- **`send_test_chart.py`**: ساخت و ارسال نمونه نمودارهای تحلیلی فونت وزیرمتن جهت تست خروجی بصری.

---

## اسکریپت‌های عملیاتی و زیرساخت (`scripts/ops/`)

اسکریپت‌های مرتبط با دیپلوی، ارتباطات سرور، عیب‌یابی و بازیابی در پوشه `scripts/ops/` نگهداری می‌شوند:

- **دیپلوی به Dokploy**:
  - `deploy_dokploy.py` / `deploy_release.py` / `clean_deploy.py`: بسته‌بندی و آپلود فایل‌های پروژه به سرور Dokploy.
  - `poll_deploy.py`: بررسی وضعیت آخرین بیلد و استقرار.
- **ارتباط و مدیریت سرور (SSH)**:
  - `ssh_check.py` / `ssh_diag.py`: بررسی اتصال به سرور و تست پروکسی/VPN.
  - `ssh_sync_drop.py` / `ssh_build.py`: همگام‌سازی و ساخت مستقیم روی سرور لینوکس.
- **لاگ‌ها و بازیابی**:
  - `tail_logs.py` / `search_logs.py` / `check_dep_log.py`: مشاهده زنده یا فیلترشده لاگ‌های کانتینر.
  - `recover_homa.py` / `force_stop_homa.py`: متوقف‌سازی و بازیابی کانتینر در مواقع قطعی یا کرش‌لوپ.
