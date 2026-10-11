import { table, integer, text, boolean, json, sql } from 'sdk/db';

export const personnel = table('personnel', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tgId: integer('tg_id').unique(),
  name: text('name').notNull(),
  role: text('role').notNull().default('employee'), // 'admin', 'senior_admin', 'employee'
  active: boolean('active').default(true),
  canViewAll: boolean('can_view_all').default(false),
  mobile: text('mobile'),
  createdAt: integer('created_at').default(sql`(unixepoch())`),
});

export const projects = table('projects', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name').notNull().unique(),
  category: text('category').default('project'), // 'general', 'project'
  createdAt: integer('created_at').default(sql`(unixepoch())`),
});

export const tasks = table('tasks', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  title: text('title').notNull(),
  projectName: text('project_name').notNull(),
  assigneeId: integer('assignee_id'), // logical link to personnel.id
  assigneeName: text('assignee_name').notNull(),
  creatorId: integer('creator_id'),
  creatorName: text('creator_name'),
  deadline: text('deadline'), // Shamsi string e.g. 1405/07/20
  priority: text('priority').default('متوسط'), // 'کم', 'متوسط', 'فوری'
  status: text('status').default('باز'), // 'باز', 'در حال انجام', 'انجام شد', 'لغو'
  createdAt: integer('created_at').default(sql`(unixepoch())`),
  updatedAt: integer('updated_at').default(sql`(unixepoch())`),
});

export const userState = table('user_state', {
  tgId: integer('tg_id').primaryKey(),
  step: text('step'),
  data: json('data'),
  updatedAt: integer('updated_at').default(sql`(unixepoch())`),
});
