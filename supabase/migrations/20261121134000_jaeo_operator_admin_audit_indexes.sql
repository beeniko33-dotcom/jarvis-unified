create index if not exists jaeo_operator_admin_audit_actor_idx on jarvis_private.jaeo_operator_admin_audit(actor_user_id, occurred_at desc);
create index if not exists jaeo_operator_admin_audit_target_idx on jarvis_private.jaeo_operator_admin_audit(target_user_id, occurred_at desc);
