-- Tighten the isolated four-pillar foundation after the first advisor pass.
-- Combine candidate and employer update rules without changing their effective access.
drop policy if exists career_applications_candidate_update on public.career_applications;
drop policy if exists career_applications_employer_update on public.career_applications;
drop policy if exists career_applications_update on public.career_applications;
create policy career_applications_update on public.career_applications
for update to authenticated
using (
  (candidate_id = (select auth.uid())
    and status in ('submitted','reviewing','shortlisted','interview'))
  or exists (
    select 1 from public.career_jobs j
    where j.id = career_applications.job_id
      and jarvis_private.career_is_org_member(
        j.organization_id, array['owner','admin','recruiter'])
  )
)
with check (
  (candidate_id = (select auth.uid()) and status = 'withdrawn')
  or exists (
    select 1 from public.career_jobs j
    where j.id = career_applications.job_id
      and jarvis_private.career_is_org_member(
        j.organization_id, array['owner','admin','recruiter'])
  )
);

-- Cover all foreign keys reported by the initial isolated performance audit.
create index if not exists career_jobs_created_by_idx on public.career_jobs(created_by);
create index if not exists career_messages_sender_id_idx on public.career_messages(sender_id);
create index if not exists career_organization_members_user_id_idx on public.career_organization_members(user_id);
create index if not exists career_organizations_created_by_idx on public.career_organizations(created_by);
create index if not exists marketplace_affiliate_links_affiliate_user_id_idx on public.marketplace_affiliate_links(affiliate_user_id);
create index if not exists marketplace_listings_created_by_idx on public.marketplace_listings(created_by);
create index if not exists marketplace_orders_affiliate_link_id_idx on public.marketplace_orders(affiliate_link_id);
create index if not exists marketplace_orders_listing_id_idx on public.marketplace_orders(listing_id);

-- Trigger-only helper; it must not be an RPC callable by API roles.
revoke all on function jarvis_private.jaeo_reject_feedback_mutation() from public, anon, authenticated, service_role;
