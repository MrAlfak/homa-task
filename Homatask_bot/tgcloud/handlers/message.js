import { api, db } from 'sdk';
import { personnel, projects } from '../schema.js';
import {
  getOrRegisterUser,
  getUserState,
  setUserState,
  clearUserState,
  getAllProjects,
  getActivePersonnel,
  getMyTasks,
} from '../lib/db-helpers.js';
import {
  mainMenuKeyboard,
  taskActionKeyboard,
  projectSelectKeyboard,
  deadlineSelectKeyboard,
  prioritySelectKeyboard,
} from '../lib/keyboards.js';

export default async function (message, ctx) {
  const chatId = message.chat.id;
  const tgId = message.from?.id || chatId;
  const text = message.text?.trim() || '';

  // 1. Check commands
  if (text === '/start') {
    await clearUserState(tgId);
    const user = await getOrRegisterUser(tgId, message.from);

    if (!user) {
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `⚠️ <b>شما در لیست پرسنل ثبت نشده‌اید.</b>\n\nشناسه عددی تلگرام شما:\n<code>${tgId}</code>\n\nلطفاً این شناسه را به مدیر سیستم تحویل دهید تا به عنوان پرسنل فعال ثبت شوید.`,
      });
      return;
    }

    const roleTitle = user.role === 'admin'
      ? '👑 مدیر سیستم'
      : user.role === 'senior_admin'
      ? '⭐ مدیر ارشد'
      : '👤 همکار گرامی';

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: `سلام <b>${user.name}</b> عزیز! 👋\n${roleTitle}\n\nبه سامانه مدیریت تسک هما خوش آمدید. برای شروع یکی از گزینه‌های زیر را انتخاب نمایید:`,
      reply_markup: mainMenuKeyboard(user.role, user.canViewAll),
    });
    return;
  }

  if (text === '/myid') {
    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: `شناسه عددی تلگرام شما: <code>${tgId}</code>`,
    });
    return;
  }

  if (text.startsWith('/add_user') || text.startsWith('/add_personnel')) {
    const user = await getOrRegisterUser(tgId, message.from);
    if (!user || (user.role !== 'admin' && user.role !== 'senior_admin')) {
      await api.sendMessage({ chat_id: chatId, text: '⛔ فقط مدیر سیستم می‌تواند پرسنل جدید ثبت کند.' });
      return;
    }
    const parts = text.split(/\s+/).slice(1);
    if (parts.length < 2) {
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: 'راهنمای ثبت پرسنل جدید:\n<code>/add_user نام شناسه_تلگرام [admin/employee]</code>\nمثال:\n<code>/add_user علی_رضایی 987654321 employee</code>',
      });
      return;
    }
    const name = parts[0].replace(/_/g, ' ');
    const newTgId = parseInt(parts[1], 10);
    const newRole = parts[2] === 'admin' ? 'admin' : parts[2] === 'senior_admin' ? 'senior_admin' : 'employee';

    await db.insert(personnel).values({
      tgId: newTgId,
      name,
      role: newRole,
      active: true,
      canViewAll: newRole !== 'employee',
    }).run();

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: `✅ همکار جدید <b>${name}</b> با شناسه <code>${newTgId}</code> به عنوان <b>${newRole}</b> اضافه شد.`,
    });
    return;
  }

  // 2. Check FSM state for active task creation or project addition
  const state = await getUserState(tgId);
  if (state && state.step) {
    if (state.step === 'awaiting_title') {
      if (!text || text.startsWith('/')) {
        await api.sendMessage({
          chat_id: chatId,
          text: 'لطفاً یک عنوان متنی معتبر برای تسک ارسال کنید:',
        });
        return;
      }

      const updatedData = { ...state.data, title: text };
      await setUserState(tgId, 'awaiting_deadline', updatedData);

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `📝 عنوان تسک: <b>${text}</b>\n\nاکنون مهلت انجام (ددلاین) را انتخاب کنید:`,
        reply_markup: deadlineSelectKeyboard(),
      });
      return;
    }

    if (state.step === 'awaiting_custom_deadline') {
      const updatedData = { ...state.data, deadline: text };
      await setUserState(tgId, 'awaiting_priority', updatedData);

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `📅 ددلاین: <b>${text}</b> ثبت شد.\n\nاکنون اولویت تسک را مشخص کنید:`,
        reply_markup: prioritySelectKeyboard(),
      });
      return;
    }

    if (state.step === 'awaiting_new_project_name') {
      if (!text || text.startsWith('/')) {
        await api.sendMessage({
          chat_id: chatId,
          text: 'لطفاً نام پروژه را بنویسید:',
        });
        return;
      }
      await db.insert(projects).values({ name: text, category: 'project' }).run();
      await clearUserState(tgId);
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: `✅ پروژه جدید <b>${text}</b> با موفقیت ایجاد شد.`,
      });
      return;
    }
  }

  // 3. User Authorization for Menus
  const user = await getOrRegisterUser(tgId, message.from);
  if (!user) {
    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: `⚠️ شما دسترسی به منوهای سیستم ندارید. شناسه شما: <code>${tgId}</code>`,
    });
    return;
  }

  // 4. Handle Reply Keyboard Buttons
  if (text.includes('ثبت تسک جدید')) {
    if (user.role !== 'admin' && user.role !== 'senior_admin') {
      await api.sendMessage({
        chat_id: chatId,
        text: '⛔ شما دسترسی ثبت تسک جدید را ندارید.',
      });
      return;
    }

    const prjs = await getAllProjects();
    await setUserState(tgId, 'awaiting_project', {
      creatorId: user.id,
      creatorName: user.name,
    });

    await api.sendMessage({
      chat_id: chatId,
      text: '📁 لطفاً پروژه مربوط به این تسک را انتخاب نمایید:',
      reply_markup: projectSelectKeyboard(prjs),
    });
    return;
  }

  if (text.includes('تسک‌های من') || text.includes('تسک های من')) {
    const myTasks = await getMyTasks(user.id, false);
    if (!myTasks || myTasks.length === 0) {
      await api.sendMessage({
        chat_id: chatId,
        text: '🎉 شما در حال حاضر تسک بازی ندارید!',
      });
      return;
    }

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: `📌 <b>لیست تسک‌های باز شما (${myTasks.length} مورد):</b>`,
    });

    for (const t of myTasks.slice(0, 10)) {
      const pColor = t.priority === 'فوری' ? '🔴' : t.priority === 'کم' ? '🟢' : '🟡';
      const statusIcon = t.status === 'در حال انجام' ? '⏳' : '📌';
      const msg = `<b>#${t.id} - ${t.title}</b>\n` +
        `📁 پروژه: ${t.projectName}\n` +
        `⏰ ددلاین: ${t.deadline || 'تعیین نشده'} | ${pColor} ${t.priority}\n` +
        `وضعیت: ${statusIcon} <b>${t.status}</b>`;

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: msg,
        reply_markup: taskActionKeyboard(t.id, t.status),
      });
    }
    return;
  }

  if (text.includes('تسک‌های انجام‌شده') || text.includes('تسک های انجام شده')) {
    const doneTasks = await getMyTasks(user.id, true);
    if (!doneTasks || doneTasks.length === 0) {
      await api.sendMessage({
        chat_id: chatId,
        text: 'هنوز تسک انجام‌شده‌ای در سوابق شما ثبت نشده است.',
      });
      return;
    }

    let report = `✅ <b>آخرین تسک‌های انجام‌شده شما:</b>\n\n`;
    for (const t of doneTasks) {
      report += `• <b>#${t.id} ${t.title}</b> (پروژه: ${t.projectName})\n`;
    }

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: report,
    });
    return;
  }

  if (text.includes('تسک‌های افراد') || text.includes('تسک های افراد')) {
    if (user.role !== 'admin' && user.role !== 'senior_admin' && !user.canViewAll) {
      await api.sendMessage({
        chat_id: chatId,
        text: '⛔ شما اجازه مشاهده تسک‌های سایر افراد را ندارید.',
      });
      return;
    }

    const staff = await getActivePersonnel();
    const buttons = staff.map(s => ([{
      text: `👤 ${s.name} (${s.role === 'admin' ? 'مدیر' : 'کارمند'})`,
      callback_data: `view_staff:${s.id}`
    }]));

    await api.sendMessage({
      chat_id: chatId,
      text: '👥 انتخاب پرسنل جهت مشاهده تسک‌های باز:',
      reply_markup: { inline_keyboard: buttons },
    });
    return;
  }

  if (text.includes('پروژه‌ها')) {
    if (user.role !== 'admin') {
      await api.sendMessage({
        chat_id: chatId,
        text: '⛔ فقط مدیر به مدیریت پروژه‌ها دسترسی دارد.',
      });
      return;
    }

    const prjs = await getAllProjects();
    let textList = '📁 <b>لیست پروژه‌های موجود:</b>\n\n';
    for (const p of prjs) {
      textList += `• ${p.category === 'general' ? '🌐' : '📁'} <b>${p.name}</b>\n`;
    }

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: textList,
      reply_markup: {
        inline_keyboard: [
          [{ text: '➕ افزودن پروژه جدید', callback_data: 'prj:new' }]
        ]
      }
    });
    return;
  }

  // Default response for unhandled text
  await api.sendMessage({
    chat_id: chatId,
    text: 'دستور نامشخص است. لطفاً از گزینه‌های منوی زیر استفاده کنید یا /start را ارسال کنید.',
    reply_markup: mainMenuKeyboard(user.role, user.canViewAll),
  });
}
