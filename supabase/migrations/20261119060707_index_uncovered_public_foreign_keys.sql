-- Cover the ten public foreign keys reported by Supabase's performance advisor.
-- These indexes improve FK joins and parent-row delete/update checks without
-- changing row-level security, authorization, or application behavior.
create index if not exists career_jobs_created_by_idx
  on public.career_jobs (created_by);
create index if not exists career_messages_sender_id_idx
  on public.career_messages (sender_id);
create index if not exists career_organization_members_user_id_idx
  on public.career_organization_members (user_id);
create index if not exists career_organizations_created_by_idx
  on public.career_organizations (created_by);
create index if not exists jarvis_autopilot_tasks_approved_by_idx
  on public.jarvis_autopilot_tasks (approved_by);
create index if not exists jarvis_autopilot_tasks_requested_by_idx
  on public.jarvis_autopilot_tasks (requested_by);
create index if not exists marketplace_affiliate_links_affiliate_user_id_idx
  on public.marketplace_affiliate_links (affiliate_user_id);
create index if not exists marketplace_listings_created_by_idx
  on public.marketplace_listings (created_by);
create index if not exists marketplace_orders_affiliate_link_id_idx
  on public.marketplace_orders (affiliate_link_id);
create index if not exists marketplace_orders_listing_id_idx
  on public.marketplace_orders (listing_id);