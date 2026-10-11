import { getShamsiChoices } from './jalali.js';

export function mainMenuKeyboard(role = 'employee', canViewAll = false) {
  const keyboard = [];
  const isAdmin = role === 'admin' || role === 'senior_admin';

  if (isAdmin) {
    keyboard.push([{ text: '➕ ثبت تسک جدید' }]);
    keyboard.push([{ text: '📌 تسک‌های من' }, { text: '✅ تسک‌های انجام‌شده' }]);
    keyboard.push([{ text: '👥 تسک‌های افراد' }, { text: '📁 پروژه‌ها' }]);
  } else if (canViewAll) {
    keyboard.push([{ text: '📌 تسک‌های من' }, { text: '✅ تسک‌های انجام‌شده' }]);
    keyboard.push([{ text: '👥 تسک‌های افراد' }]);
  } else {
    keyboard.push([{ text: '📌 تسک‌های من' }, { text: '✅ تسک‌های انجام‌شده' }]);
  }

  return {
    keyboard,
    resize_keyboard: true,
  };
}

export function taskActionKeyboard(taskId, status = 'باز') {
  const buttons = [];
  if (status === 'باز') {
    buttons.push({ text: '▶️ شروع کار', callback_data: `ts:start:${taskId}` });
    buttons.push({ text: '✅ انجام شد', callback_data: `ts:done:${taskId}` });
  } else if (status === 'در حال انجام') {
    buttons.push({ text: '✅ انجام شد', callback_data: `ts:done:${taskId}` });
    buttons.push({ text: '❌ لغو', callback_data: `ts:cancel:${taskId}` });
  } else {
    buttons.push({ text: '🔄 بازگشایی مجدد', callback_data: `ts:reopen:${taskId}` });
  }

  return {
    inline_keyboard: [buttons],
  };
}

export function projectSelectKeyboard(projectsList = []) {
  const inline_keyboard = [];
  for (const prj of projectsList) {
    const icon = prj.category === 'general' ? '🌐' : '📁';
    inline_keyboard.push([{ text: `${icon} ${prj.name}`, callback_data: `fsm:prj:${prj.id}` }]);
  }
  inline_keyboard.push([{ text: '❌ انصراف', callback_data: 'fsm:cancel' }]);
  return { inline_keyboard };
}

export function assigneeSelectKeyboard(personnelList = []) {
  const inline_keyboard = [];
  for (const p of personnelList) {
    inline_keyboard.push([{ text: `👤 ${p.name}`, callback_data: `fsm:asg:${p.id}` }]);
  }
  inline_keyboard.push([{ text: '❌ انصراف', callback_data: 'fsm:cancel' }]);
  return { inline_keyboard };
}

export function deadlineSelectKeyboard() {
  const choices = getShamsiChoices();
  const inline_keyboard = choices.map(c => [
    { text: c.label, callback_data: `fsm:ddl:${c.value}` }
  ]);
  inline_keyboard.push([{ text: '❌ انصراف', callback_data: 'fsm:cancel' }]);
  return { inline_keyboard };
}

export function prioritySelectKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: '🟢 کم', callback_data: 'fsm:prio:کم' },
        { text: '🟡 متوسط', callback_data: 'fsm:prio:متوسط' },
        { text: '🔴 فوری', callback_data: 'fsm:prio:فوری' }
      ],
      [{ text: '❌ انصراف', callback_data: 'fsm:cancel' }]
    ]
  };
}

export function confirmCreateTaskKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: '✅ تأیید و ثبت تسک', callback_data: 'fsm:confirm' },
        { text: '❌ انصراف', callback_data: 'fsm:cancel' }
      ]
    ]
  };
}

export function cancelInlineKeyboard() {
  return {
    inline_keyboard: [[{ text: '❌ انصراف', callback_data: 'fsm:cancel' }]]
  };
}
