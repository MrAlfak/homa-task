import { db } from 'sdk';
import { eq, and, sql, desc } from 'sdk/db';
import { personnel, projects, tasks, userState } from '../schema.js';

const DEFAULT_STAFF = [
  { tgId: 114848224, name: 'Alfak', role: 'admin', active: true, canViewAll: true },
  { tgId: 109636816, name: 'Alipour', role: 'employee', active: true, canViewAll: false },
  { tgId: 5170242889, name: 'Amiri', role: 'employee', active: true, canViewAll: false },
  { tgId: 1093900281, name: 'Bakhshande', role: 'employee', active: true, canViewAll: false },
  { tgId: 5845798705, name: 'Dehghanian', role: 'employee', active: true, canViewAll: true },
  { tgId: 13541485, name: 'Eidani', role: 'employee', active: true, canViewAll: false },
  { tgId: 99441746, name: 'Hosseini', role: 'employee', active: true, canViewAll: false },
  { tgId: 1338041605, name: 'MR.SHEIKH', role: 'employee', active: true, canViewAll: true },
  { tgId: 293719168, name: 'Moradi', role: 'employee', active: true, canViewAll: false },
  { tgId: 110217849, name: 'Roozmand', role: 'employee', active: true, canViewAll: false },
];

const DEFAULT_PROJECTS = [
  { name: 'عمومی', category: 'general' },
  { name: 'آپلودها', category: 'general' },
  { name: 'کارهای مشترک', category: 'general' },
  { name: 'استخر عفیف آباد', category: 'project' },
  { name: 'تیزر', category: 'project' },
  { name: 'جمالی', category: 'project' },
  { name: 'دل افکار', category: 'project' },
  { name: 'دهقان زاده', category: 'project' },
  { name: 'دکتر اکرمی', category: 'project' },
  { name: 'دکتر رضایی', category: 'project' },
  { name: 'رییسی', category: 'project' },
  { name: 'زمین تنیس عفیف آباد (سگال)', category: 'project' },
  { name: 'سایکو', category: 'project' },
  { name: 'قاسم پور', category: 'project' },
  { name: 'متفرقه', category: 'project' },
  { name: 'هما', category: 'project' },
  { name: 'ویسادار', category: 'project' },
  { name: 'کوه کاران', category: 'project' },
  { name: 'گروه وستا', category: 'project' },
];

export async function ensureSeedData() {
  // Clean up any dummy test user
  await db.delete(personnel).where(eq(personnel.tgId, 1)).run();

  // Ensure all Google Sheet personnel are in SQLite
  for (const s of DEFAULT_STAFF) {
    const existing = await db.select().from(personnel).where(eq(personnel.tgId, s.tgId)).get();
    if (!existing) {
      await db.insert(personnel).values(s).run();
    } else if (existing.name !== s.name || existing.role !== s.role || existing.canViewAll !== s.canViewAll) {
      await db.update(personnel)
        .set({ name: s.name, role: s.role, canViewAll: s.canViewAll, active: s.active })
        .where(eq(personnel.tgId, s.tgId))
        .run();
    }
  }

  // Ensure all Google Sheet projects are in SQLite
  for (const p of DEFAULT_PROJECTS) {
    const existingPrj = await db.select().from(projects).where(eq(projects.name, p.name)).get();
    if (!existingPrj) {
      await db.insert(projects).values(p).run();
    }
  }
}

export async function getOrRegisterUser(tgId, fromUser = {}) {
  await ensureSeedData();
  let user = await db.select().from(personnel).where(eq(personnel.tgId, tgId)).get();

  if (!user && (tgId === 114848224 || (await db.$count(personnel)) === 0)) {
    const name = [fromUser.first_name, fromUser.last_name].filter(Boolean).join(' ') || 'Alfak';
    const [newAdmin] = await db.insert(personnel).values({
      tgId,
      name,
      role: 'admin',
      active: true,
      canViewAll: true,
    }).returning().run();
    return newAdmin;
  }

  return user;
}

export async function getActivePersonnel() {
  return await db.select().from(personnel).where(eq(personnel.active, true)).all();
}

export async function getAllProjects() {
  return await db.select().from(projects).all();
}

export async function getProjectById(id) {
  return await db.select().from(projects).where(eq(projects.id, id)).get();
}

export async function getPersonById(id) {
  return await db.select().from(personnel).where(eq(personnel.id, id)).get();
}

export async function getMyTasks(assigneeId, isDone = false) {
  if (isDone) {
    return await db.select()
      .from(tasks)
      .where(and(eq(tasks.assigneeId, assigneeId), eq(tasks.status, 'انجام شد')))
      .orderBy(desc(tasks.updatedAt))
      .limit(10)
      .all();
  }

  return await db.select()
    .from(tasks)
    .where(and(
      eq(tasks.assigneeId, assigneeId),
      sql`${tasks.status} != 'انجام شد' AND ${tasks.status} != 'لغو'`
    ))
    .orderBy(desc(tasks.id))
    .all();
}

export async function getOpenTasksForPerson(assigneeId) {
  return await db.select()
    .from(tasks)
    .where(and(
      eq(tasks.assigneeId, assigneeId),
      sql`${tasks.status} != 'انجام شد' AND ${tasks.status} != 'لغو'`
    ))
    .orderBy(desc(tasks.id))
    .all();
}

export async function getTaskById(taskId) {
  return await db.select().from(tasks).where(eq(tasks.id, taskId)).get();
}

export async function setTaskStatus(taskId, status) {
  return await db.update(tasks)
    .set({
      status,
      updatedAt: sql`(unixepoch())`
    })
    .where(eq(tasks.id, taskId))
    .run();
}

export async function insertNewTask(taskData) {
  const [created] = await db.insert(tasks).values({
    title: taskData.title,
    projectName: taskData.projectName,
    assigneeId: taskData.assigneeId,
    assigneeName: taskData.assigneeName,
    creatorId: taskData.creatorId,
    creatorName: taskData.creatorName,
    deadline: taskData.deadline,
    priority: taskData.priority || 'متوسط',
    status: 'باز',
  }).returning().run();
  return created;
}

export async function getUserState(tgId) {
  const row = await db.select().from(userState).where(eq(userState.tgId, tgId)).get();
  if (!row) return null;
  let parsedData = {};
  try {
    parsedData = typeof row.data === 'string' ? JSON.parse(row.data) : (row.data || {});
  } catch (e) {
    parsedData = {};
  }
  return { ...row, data: parsedData };
}

export async function setUserState(tgId, step, data = {}) {
  const now = Math.floor(Date.now() / 1000);
  const serialized = JSON.stringify(data);
  await db.insert(userState)
    .values({ tgId, step, data: serialized, updatedAt: now })
    .onConflictDoUpdate({
      target: userState.tgId,
      set: { step, data: serialized, updatedAt: now }
    })
    .run();
}

export async function clearUserState(tgId) {
  await db.delete(userState).where(eq(userState.tgId, tgId)).run();
}
