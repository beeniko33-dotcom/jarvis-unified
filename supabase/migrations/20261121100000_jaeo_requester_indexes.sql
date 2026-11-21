-- Cover the requester/approver foreign keys introduced by JAEO approval binding.
create index if not exists jaeo_tasks_requested_by_idx
  on jarvis_private.jaeo_tasks(requested_by);
create index if not exists jaeo_approvals_requested_by_idx
  on jarvis_private.jaeo_approvals(requested_by);
create index if not exists jaeo_approvals_decided_by_user_id_idx
  on jarvis_private.jaeo_approvals(decided_by_user_id);
