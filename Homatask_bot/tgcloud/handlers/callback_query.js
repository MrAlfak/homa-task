import { api } from 'sdk';
import {
  getUserState,
  setUserState,
  clearUserState,
  getProjectById,
  getPersonById,
  getActivePersonnel,
  setTaskStatus,
  getTaskById,
  insertNewTask,
  getOpenTasksForPerson,
} from '../lib/db-helpers.js';
import {
  assigneeSelectKeyboard,
  prioritySelectKeyboard,
  confirmCreateTaskKeyboard,
} from '../lib/keyboards.js';

export default async function (query, ctx) {
  const queryId = query.id;
  const data = query.data || '';
  const message = query.message;
  const chatId = message?.chat?.id;
  const messageId = message?.message_id;
  const tgId = query.from?.id;

  async function answer(text, alert = false) {
    try {
      await api.answerCallbackQuery({
        callback_query_id: queryId,
        text,
        show_alert: alert,
      });
    } catch (e) {
      // ignore expired query errors
    }
  }

  // 1. Task Status Actions
  if (data.startsWith('ts:')) {
    const [, action, idStr] = data.split(':');
    const taskId = parseInt(idStr, 10);
    const task = await getTaskById(taskId);

    if (!task) {
      await answer('تسک مورد نظر یافت نشد.', true);
      return;
    }

    if (action === 'start') {
      await setTaskStatus(taskId, 'در حال انجام');
      await answer('وضعیت تسک به «در حال انجام» تغییر یافت ⏳');
      if (chatId && messageId) {
        await api.editMessageText({
          chat_id: chatId,
          message_id: messageId,
          parse_mode: 'HTML',
          text: `${message.text}\n\n⏳ <i>وضعیت در ساعت جاری به «در حال انجام» تغییر کرد.</i>`,
        });
      }
      return;
    }

    if (action === 'done') {
      await setTaskStatus(taskId, 'انجام شد');
      await answer('آفرین! تسک با موفقیت انجام شد ✅', true);
      if (chatId && messageId) {
        await api.editMessageText({
          chat_id: chatId,
          message_id: messageId,
          parse_mode: 'HTML',
          text: `<s>${message.text}</s>\n\n✅ <b>انجام شد.</b>`,
        });
      }
      return;
    }

    if (action === 'cancel') {
      await setTaskStatus(taskId, 'لغو');
      await answer('تسک لغو گردید ❌');
      if (chatId && messageId) {
        await api.editMessageText({
          chat_id: chatId,
          message_id: messageId,
          parse_mode: 'HTML',
          text: `<s>${message.text}</s>\n\n❌ <b>لغو شد.</b>`,
        });
      }
      return;
    }

    if (action === 'reopen') {
      await setTaskStatus(taskId, 'باز');
      await answer('تسک مجدداً باز شد 🔄');
      return;
    }
  }

  // 2. FSM Workflow for Creating Tasks
  if (data === 'fsm:cancel') {
    await clearUserState(tgId);
    await answer('عملیات لغو شد.');
    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '❌ عملیات ثبت تسک لغو گردید.',
      });
    }
    return;
  }

  if (data.startsWith('fsm:prj:')) {
    const prjId = parseInt(data.replace('fsm:prj:', ''), 10);
    const prj = await getProjectById(prjId);
    if (!prj) {
      await answer('پروژه معتبر نیست.', true);
      return;
    }

    const state = (await getUserState(tgId)) || { data: {} };
    const updatedData = { ...state.data, projectName: prj.name, projectId: prj.id };
    await setUserState(tgId, 'awaiting_assignee', updatedData);

    const staff = await getActivePersonnel();
    await answer(`پروژه ${prj.name} انتخاب شد.`);

    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: `📁 پروژه انتخابی: <b>${prj.name}</b>\n\n👤 لطفاً مسئول انجام تسک را انتخاب کنید:`,
        reply_markup: assigneeSelectKeyboard(staff),
      });
    }
    return;
  }

  if (data.startsWith('fsm:asg:')) {
    const personId = parseInt(data.replace('fsm:asg:', ''), 10);
    const person = await getPersonById(personId);
    if (!person) {
      await answer('شخص معتبر نیست.', true);
      return;
    }

    const state = (await getUserState(tgId)) || { data: {} };
    const updatedData = {
      ...state.data,
      assigneeId: person.id,
      assigneeName: person.name,
      assigneeTgId: person.tgId,
    };
    await setUserState(tgId, 'awaiting_title', updatedData);

    await answer(`مسئول تسک: ${person.name}`);
    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: `📁 پروژه: <b>${updatedData.projectName}</b>\n` +
          `👤 مسئول: <b>${person.name}</b>\n\n` +
          `✍️ لطفاً اکنون <b>عنوان تسک</b> را به عنوان یک پیام متنی ارسال کنید:`,
      });
    }
    return;
  }

  if (data.startsWith('fsm:ddl:')) {
    const deadline = data.replace('fsm:ddl:', '');
    const state = (await getUserState(tgId)) || { data: {} };
    const updatedData = { ...state.data, deadline };
    await setUserState(tgId, 'awaiting_priority', updatedData);

    await answer(`ددلاین: ${deadline}`);
    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: `📝 عنوان: <b>${updatedData.title}</b>\n` +
          `📅 ددلاین: <b>${deadline}</b>\n\n` +
          `🎯 اولویت تسک را مشخص کنید:`,
        reply_markup: prioritySelectKeyboard(),
      });
    }
    return;
  }

  if (data.startsWith('fsm:prio:')) {
    const priority = data.replace('fsm:prio:', '');
    const state = (await getUserState(tgId)) || { data: {} };
    const updatedData = { ...state.data, priority };
    await setUserState(tgId, 'confirm', updatedData);

    await answer(`اولویت: ${priority}`);
    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: `📋 <b>پیش‌نمایش تسک جدید:</b>\n\n` +
          `▫️ عنوان: <b>${updatedData.title}</b>\n` +
          `▫️ پروژه: <b>${updatedData.projectName}</b>\n` +
          `▫️ مسئول: <b>${updatedData.assigneeName}</b>\n` +
          `▫️ ددلاین: <b>${updatedData.deadline}</b>\n` +
          `▫️ اولویت: <b>${priority}</b>\n\n` +
          `آیا مشخصات بالا مورد تأیید است؟`,
        reply_markup: confirmCreateTaskKeyboard(),
      });
    }
    return;
  }

  if (data === 'fsm:confirm') {
    const state = await getUserState(tgId);
    if (!state || !state.data || !state.data.title) {
      await answer('اطلاعات تسک منقضی شده است. لطفاً مجدداً اقدام نمایید.', true);
      return;
    }

    const created = await insertNewTask(state.data);
    await clearUserState(tgId);
    await answer('تسک با موفقیت ثبت گردید! 🎉', true);

    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: `✅ <b>تسک #${created.id} با موفقیت ثبت شد!</b>\n\n` +
          `▫️ عنوان: <b>${created.title}</b>\n` +
          `▫️ پروژه: <b>${created.projectName}</b>\n` +
          `▫️ مسئول: <b>${created.assigneeName}</b>\n` +
          `▫️ ددلاین: <b>${created.deadline}</b>`,
      });
    }

    // Notify assignee if registered with telegram id
    if (state.data.assigneeTgId && state.data.assigneeTgId !== tgId) {
      try {
        await api.sendMessage({
          chat_id: state.data.assigneeTgId,
          parse_mode: 'HTML',
          text: `🔔 <b>یک تسک جدید برای شما ثبت شد!</b>\n\n` +
            `▫️ عنوان: <b>${created.title}</b>\n` +
            `▫️ پروژه: <b>${created.projectName}</b>\n` +
            `▫️ ایجاد کننده: <b>${created.creatorName || 'مدیر'}</b>\n` +
            `▫️ ددلاین: <b>${created.deadline}</b>`,
        });
      } catch (e) {
        // user might not have started bot yet
      }
    }
    return;
  }

  // 3. View Staff Tasks (Admin)
  if (data.startsWith('view_staff:')) {
    const personId = parseInt(data.replace('view_staff:', ''), 10);
    const person = await getPersonById(personId);
    if (!person) {
      await answer('شخص یافت نشد.', true);
      return;
    }

    const personTasks = await getOpenTasksForPerson(person.id);
    await answer(`تسک‌های ${person.name}`);

    if (personTasks.length === 0) {
      if (chatId && messageId) {
        await api.editMessageText({
          chat_id: chatId,
          message_id: messageId,
          parse_mode: 'HTML',
          text: `👤 <b>${person.name}:</b>\nهیچ تسک بازی ندارد! 🎉`,
        });
      }
      return;
    }

    let report = `👤 <b>تسک‌های باز ${person.name} (${personTasks.length} مورد):</b>\n\n`;
    for (const t of personTasks) {
      report += `• <b>#${t.id} ${t.title}</b>\n  📁 پروژه: ${t.projectName} | ددلاین: ${t.deadline || '-'}\n`;
    }

    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: report,
      });
    }
    return;
  }

  // 4. Add Project Prompt
  if (data === 'prj:new') {
    await setUserState(tgId, 'awaiting_new_project_name', {});
    await answer('نام پروژه جدید را ارسال کنید.');
    if (chatId && messageId) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '✍️ لطفاً نام پروژه جدید را در قالب یک پیام ارسال فرمایید:',
      });
    }
    return;
  }

  await answer('دستور دریافت شد.');
}
