// Pure JavaScript Jalali (Shamsi) calendar functions — no external dependencies

const PERSIAN_MONTHS = [
  'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
];

const PERSIAN_WEEKDAYS = [
  'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه'
];

export function gregorianToJalali(gy, gm, gd) {
  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy = (gy <= 1600) ? 0 : 979;
  gy -= (gy <= 1600) ? 621 : 1600;
  let gy2 = (gm > 2) ? (gy + 1) : gy;
  let days = (365 * gy) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100)
    + Math.floor((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1];
  jy += 33 * Math.floor(days / 12053);
  days %= 12053;
  jy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    jy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  let jm = (days < 186) ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  let jd = 1 + ((days < 186) ? (days % 31) : ((days - 186) % 30));
  return [jy, jm, jd];
}

export function formatJalali(date = new Date()) {
  const [jy, jm, jd] = gregorianToJalali(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
  const mm = String(jm).padStart(2, '0');
  const dd = String(jd).padStart(2, '0');
  return `${jy}/${mm}/${dd}`;
}

export function getJalaliDateOffset(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return formatJalali(d);
}

export function getMonthName(monthNumber) {
  return PERSIAN_MONTHS[monthNumber - 1] || '';
}

export function getShamsiChoices() {
  const today = getJalaliDateOffset(0);
  const tomorrow = getJalaliDateOffset(1);
  const day2 = getJalaliDateOffset(2);
  const day3 = getJalaliDateOffset(3);
  const nextWeek = getJalaliDateOffset(7);
  return [
    { label: `امروز (${today})`, value: today },
    { label: `فردا (${tomorrow})`, value: tomorrow },
    { label: `۲ روز بعد (${day2})`, value: day2 },
    { label: `۳ روز بعد (${day3})`, value: day3 },
    { label: `یک هفته بعد (${nextWeek})`, value: nextWeek },
  ];
}
