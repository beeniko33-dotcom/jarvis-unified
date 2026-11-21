-- JAEO is a supervised research/engineering operator, not a trading runtime.
-- Replace the legacy paper-mode label with an explicit supervised mode.
alter table jarvis_private.jaeo_tasks
  drop constraint if exists jaeo_tasks_mode_check;

update jarvis_private.jaeo_tasks
set mode = 'supervised'
where mode <> 'supervised';

alter table jarvis_private.jaeo_tasks
  alter column mode set default 'supervised';

alter table jarvis_private.jaeo_tasks
  add constraint jaeo_tasks_mode_check check (mode = 'supervised');

comment on column jarvis_private.jaeo_tasks.mode is
  'Supervised research/engineering mode only. No paper, demo, or live trade execution.';
comment on table jarvis_private.jaeo_tasks is
  'Private supervised JAEO task registry for research and engineering operations only; no trading execution.';
