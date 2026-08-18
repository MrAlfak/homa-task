# Homa Task — ربات تلگرام مدیریت تسک با Google Sheets

ربات تلگرام برای ثبت و پیگیری تسک پرسنل. تمام داده‌ها (پرسنل و تسک‌ها) در **Google Sheet** ذخیره می‌شوند.

## قابلیت‌ها

- **مدیر (admin):** ثبت تسک برای کارمندان، دریافت نوتیف پس از ثبت
- **کارمند (employee):** مشاهده تسک‌ها، تغییر وضعیت (شروع / انجام شد)
- **Google Sheet:** مدیریت پرسنل بدون کدنویسی

---

## ۱. ساخت Google Sheet

یک Google Sheet جدید بسازید با دو تب:

### تب `Personnel`

| telegram_id | name | role | active |
|-------------|------|------|--------|
| 123456789 | مدیر سیستم | admin | TRUE |
| 987654321 | علی کارمند | employee | TRUE |

- **telegram_id:** شناسه عددی تلگرام (با `/myid` در ربات بگیرید)
- **role:** `admin` یا `employee`
- **active:** `TRUE` یا `FALSE`

### تب `Projects`

| پروژه |
|-------|

نام هر پروژه یا پیج در ستون A (ردیف ۱: هدر `پروژه`). ربات هنگام راه‌اندازی این دسته‌های **عمومی** را در صورت نبودن اضافه می‌کند:

- **عمومی** — کارهایی که به یک پیج خاص وصل نیستند
- **آپلودها** — آپلود برای چند پیج در یک بازه
- **کارهای مشترک** — سایر کارهای چندپروژه‌ای

در منوی ثبت تسک، 🌐 = دسته عمومی، 📁 = پروژه مشخص.

### تب `Tasks` (ثبت اصلی — مطابق Sheet مشتری)

| تسک | پروژه | مسوول تسک | ایجاد کننده | تاریخ ایجاد | ددلاین | اولویت | ماه |
|-----|-------|-----------|-------------|-------------|--------|--------|-----|

ربات ردیف جدید را **با همان قالب** (تاریخ شمسی، ماه فارسی، dropdown اولویت) در انتهای جدول insert می‌کند و فرمت ردیف ۲ را کپی می‌کند.

همزمان در **تب شخصی کارمند** هم ثبت می‌شود **فقط اگر** آن تب فرمول `FILTER` از Tasks نداشته باشد.
تب‌هایی مثل Bakhshande که با `FILTER(..., Tasks!C:C="نام")` پر می‌شوند فقط از تب **Tasks** تغذیه می‌شوند — ربات دیگر در آن‌ها ردیف نمی‌نویسد.

---

## ۲. Google Cloud Service Account

1. به [Google Cloud Console](https://console.cloud.google.com/) بروید
2. پروژه جدید بسازید → **APIs & Services** → **Enable APIs**:
   - Google Sheets API
   - Google Drive API
3. **Credentials** → **Create Credentials** → **Service Account**
4. کلید JSON دانلود کنید → در پوشه `credentials/` با نام:
   ```
   credentials/google-service-account.json
   ```
5. Google Sheet را با **ایمیل Service Account** (مثل `xxx@xxx.iam.gserviceaccount.com`) Share کنید (Editor)

---

## ۳. ربات تلگرام

1. در تلگرام به [@BotFather](https://t.me/BotFather) پیام دهید
2. `/newbot` → نام و username بگیرید
3. **Token** را کپی کنید

---

## ۴. نصب و اجرا

```bash
cd homa-task
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
```

فایل `.env` را پر کنید:

```env
BOT_TOKEN=123456:ABC...
GOOGLE_SHEET_ID=از_آدرس_شیت
GOOGLE_CREDENTIALS_PATH=credentials/google-service-account.json
BOT_MODE=polling
```

**Sheet ID** از URL:
```
https://docs.google.com/spreadsheets/d/SHEET_ID/edit
```

### اجرا

```bash
python -m bot.main
```

---

## ۵. ثبت اولین کاربر

1. ربات را `/start` بزنید → پیام «در لیست پرسنل نیستید» + شناسه شما
2. یا `/myid` بزنید
3. `telegram_id` را در تب `Personnel` با `role=admin` ثبت کنید
4. دوباره `/start` بزنید

---

## فلو استفاده

### مدیر
1. **➕ ثبت تسک جدید**
2. کارمند را از لیست انتخاب کنید
3. عنوان → توضیح → مهلت (اختیاری)
4. تسک در Sheet ثبت و به کارمند نوتیف می‌شود

### کارمند
1. **📌 تسک‌های من** — همه تسک‌ها
2. **✅ تسک‌های انجام‌شده** — فیلتر done
3. روی هر تسک → **شروع کار** / **انجام شد**

---

## Webhook (production)

```env
BOT_MODE=webhook
WEBHOOK_HOST=https://your-domain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8080
```

سرور باید HTTPS داشته باشد. پشت nginx/caddy پروکسی کنید.

---

## ساختار پروژه

```text
homa-task/
├── bot/
│   ├── main.py
│   ├── keyboards.py
│   ├── states.py
│   └── handlers/
├── services/
│   ├── sheets.py
│   └── auth.py
├── credentials/
├── config.py
├── requirements.txt
└── .env
```

---

## عیب‌یابی

| مشکل | راه‌حل |
|------|--------|
| `BOT_TOKEN is required` | `.env` را از `.env.example` کپی و پر کنید |
| `credentials not found` | JSON Service Account در `credentials/` |
| `Spreadsheet not found` | Sheet ID اشتباه یا Share نشده |
| نوتیف به کارمند نمی‌رسد | کارمند باید حداقل یک بار `/start` زده باشد |
| لیست کارمند خالی | تب Personnel — role=employee و active=TRUE |
