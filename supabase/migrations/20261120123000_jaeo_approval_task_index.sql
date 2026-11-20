-- Cover approval lookup and cascading task references efficiently.
create index if not exists jaeo_approvals_task_id_idx
    on jarvis_private.jaeo_approvals (task_id);