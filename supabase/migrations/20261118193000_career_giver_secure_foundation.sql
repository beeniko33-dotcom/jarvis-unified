-- Career Giver foundation: profiles, verified organizations, jobs, applications and private messaging.
-- No identity documents, public contact details, payments or rewards are stored here.
create table public.career_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (length(trim(display_name)) between 1 and 100),
  headline text check (headline is null or length(headline) <= 160),
  bio text check (bio is null or length(bio) <= 4000),
  location text check (location is null or length(location) <= 120),
  visibility text not null default 'private' check (visibility in ('private','public')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.career_profiles enable row level security;
create policy career_profiles_read on public.career_profiles for select to authenticated
  using (user_id = auth.uid() or visibility = 'public');
create policy career_profiles_insert on public.career_profiles for insert to authenticated
  with check (user_id = auth.uid());
create policy career_profiles_update on public.career_profiles for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
revoke all on public.career_profiles from anon;
grant select, insert, update on public.career_profiles to authenticated;

create table public.career_organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) between 2 and 160),
  website text check (website is null or length(website) <= 500),
  description text check (description is null or length(description) <= 4000),
  country_code text check (country_code is null or country_code ~ '^[A-Z]{2}$'),
  verification_status text not null default 'pending'
    check (verification_status in ('pending','verified','rejected','suspended')),
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table public.career_organization_members (
  organization_id uuid not null references public.career_organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  member_role text not null check (member_role in ('owner','admin','recruiter')),
  membership_status text not null default 'active'
    check (membership_status in ('invited','active','suspended')),
  created_at timestamptz not null default now(),
  primary key (organization_id,user_id)
);
alter table public.career_organizations enable row level security;
alter table public.career_organization_members enable row level security;
create policy career_org_read on public.career_organizations for select to authenticated
  using (verification_status = 'verified' or created_by = auth.uid()
    or exists (select 1 from public.career_organization_members m
      where m.organization_id=id and m.user_id=auth.uid() and m.membership_status='active'));
create policy career_org_create on public.career_organizations for insert to authenticated
  with check (created_by = auth.uid() and verification_status='pending');
create policy career_org_update on public.career_organizations for update to authenticated
  using (exists (select 1 from public.career_organization_members m
    where m.organization_id=id and m.user_id=auth.uid()
      and m.member_role in ('owner','admin') and m.membership_status='active'))
  with check (verification_status in ('pending','verified','rejected','suspended'));
create policy career_org_members_read on public.career_organization_members for select to authenticated
  using (user_id=auth.uid() or exists (select 1 from public.career_organization_members m
    where m.organization_id=career_organization_members.organization_id
      and m.user_id=auth.uid() and m.membership_status='active'));
create policy career_org_members_owner_manage on public.career_organization_members for all to authenticated
  using (exists (select 1 from public.career_organization_members m
    where m.organization_id=career_organization_members.organization_id
      and m.user_id=auth.uid() and m.member_role in ('owner','admin') and m.membership_status='active'))
  with check (exists (select 1 from public.career_organization_members m
    where m.organization_id=career_organization_members.organization_id
      and m.user_id=auth.uid() and m.member_role in ('owner','admin') and m.membership_status='active'));
revoke all on public.career_organizations, public.career_organization_members from anon;
grant select,insert,update on public.career_organizations to authenticated;
grant select,insert,update,delete on public.career_organization_members to authenticated;

create or replace function public.career_add_organization_owner()
returns trigger language plpgsql security definer set search_path=''
as $$
begin
  insert into public.career_organization_members(organization_id,user_id,member_role,membership_status)
  values(new.id,new.created_by,'owner','active');
  return new;
end;
$$;
revoke all on function public.career_add_organization_owner() from public,anon,authenticated;
create trigger career_org_owner_after_insert after insert on public.career_organizations
  for each row execute function public.career_add_organization_owner();

create table public.career_jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.career_organizations(id) on delete restrict,
  created_by uuid not null references auth.users(id) on delete restrict,
  title text not null check (length(trim(title)) between 3 and 180),
  description text not null check (length(trim(description)) between 30 and 20000),
  employment_type text not null check (employment_type in ('full_time','part_time','contract','temporary','internship')),
  workplace_type text not null check (workplace_type in ('onsite','hybrid','remote')),
  location text check (location is null or length(location) <= 160),
  salary_min numeric(14,2) check (salary_min is null or salary_min >= 0),
  salary_max numeric(14,2) check (salary_max is null or salary_max >= 0),
  salary_currency text check (salary_currency is null or salary_currency ~ '^[A-Z]{3}$'),
  status text not null default 'draft' check (status in ('draft','published','closed')),
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (salary_min is null or salary_max is null or salary_max >= salary_min),
  check (status <> 'published' or published_at is not null)
);
create index career_jobs_public_idx on public.career_jobs(status,created_at desc);
create index career_jobs_org_idx on public.career_jobs(organization_id,created_at desc);
alter table public.career_jobs enable row level security;
create policy career_jobs_read on public.career_jobs for select to authenticated
  using (status='published' or exists (select 1 from public.career_organization_members m
    where m.organization_id=career_jobs.organization_id and m.user_id=auth.uid()
      and m.membership_status='active'));
create policy career_jobs_insert on public.career_jobs for insert to authenticated
  with check (created_by=auth.uid() and status='draft' and exists (
    select 1 from public.career_organization_members m join public.career_organizations o
      on o.id=m.organization_id
    where m.organization_id=career_jobs.organization_id and m.user_id=auth.uid()
      and m.membership_status='active' and m.member_role in ('owner','admin','recruiter')
      and o.verification_status='verified'));
create policy career_jobs_update on public.career_jobs for update to authenticated
  using (exists (select 1 from public.career_organization_members m
    where m.organization_id=career_jobs.organization_id and m.user_id=auth.uid()
      and m.membership_status='active' and m.member_role in ('owner','admin','recruiter')))
  with check (exists (select 1 from public.career_organization_members m
    join public.career_organizations o on o.id=m.organization_id
    where m.organization_id=career_jobs.organization_id and m.user_id=auth.uid()
      and m.membership_status='active' and m.member_role in ('owner','admin','recruiter')
      and (status <> 'published' or o.verification_status='verified')));
revoke all on public.career_jobs from anon;
grant select,insert,update on public.career_jobs to authenticated;

create table public.career_applications (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.career_jobs(id) on delete restrict,
  candidate_id uuid not null references auth.users(id) on delete restrict,
  cover_letter text check (cover_letter is null or length(cover_letter) <= 10000),
  status text not null default 'submitted'
    check (status in ('submitted','reviewing','shortlisted','interview','offered','rejected','withdrawn')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(job_id,candidate_id)
);
create index career_applications_candidate_idx on public.career_applications(candidate_id,created_at desc);
create index career_applications_job_idx on public.career_applications(job_id,created_at desc);
alter table public.career_applications enable row level security;
create policy career_applications_read on public.career_applications for select to authenticated
  using (candidate_id=auth.uid() or exists (
    select 1 from public.career_jobs j join public.career_organization_members m
      on m.organization_id=j.organization_id
    where j.id=career_applications.job_id and m.user_id=auth.uid()
      and m.membership_status='active'));
create policy career_applications_insert on public.career_applications for insert to authenticated
  with check (candidate_id=auth.uid() and exists (
    select 1 from public.career_jobs j where j.id=job_id and j.status='published'));
create policy career_applications_candidate_update on public.career_applications for update to authenticated
  using (candidate_id=auth.uid() and status in ('submitted','reviewing','shortlisted','interview'))
  with check (candidate_id=auth.uid() and status='withdrawn');
create policy career_applications_employer_update on public.career_applications for update to authenticated
  using (exists (select 1 from public.career_jobs j join public.career_organization_members m
    on m.organization_id=j.organization_id where j.id=career_applications.job_id
      and m.user_id=auth.uid() and m.membership_status='active'
      and m.member_role in ('owner','admin','recruiter')))
  with check (exists (select 1 from public.career_jobs j join public.career_organization_members m
    on m.organization_id=j.organization_id where j.id=career_applications.job_id
      and m.user_id=auth.uid() and m.membership_status='active'
      and m.member_role in ('owner','admin','recruiter')));
revoke all on public.career_applications from anon;
grant select,insert,update on public.career_applications to authenticated;

create table public.career_conversations (
  id uuid primary key default gen_random_uuid(),
  application_id uuid not null unique references public.career_applications(id) on delete restrict,
  created_at timestamptz not null default now(),
  last_message_at timestamptz
);
create table public.career_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.career_conversations(id) on delete restrict,
  sender_id uuid not null references auth.users(id) on delete restrict,
  body text not null check (length(trim(body)) between 1 and 10000),
  created_at timestamptz not null default now()
);
create index career_messages_conversation_idx on public.career_messages(conversation_id,created_at);
alter table public.career_conversations enable row level security;
alter table public.career_messages enable row level security;
create policy career_conversations_participant_read on public.career_conversations for select to authenticated
  using (exists (select 1 from public.career_applications a
    where a.id=application_id and (a.candidate_id=auth.uid() or exists (
      select 1 from public.career_jobs j join public.career_organization_members m
        on m.organization_id=j.organization_id where j.id=a.job_id
          and m.user_id=auth.uid() and m.membership_status='active'))));
create policy career_messages_participant_read on public.career_messages for select to authenticated
  using (exists (select 1 from public.career_conversations c
    join public.career_applications a on a.id=c.application_id
    join public.career_jobs j on j.id=a.job_id
    where c.id=conversation_id and (a.candidate_id=auth.uid() or exists (
      select 1 from public.career_organization_members m where m.organization_id=j.organization_id
        and m.user_id=auth.uid() and m.membership_status='active'))));
create policy career_messages_participant_insert on public.career_messages for insert to authenticated
  with check (sender_id=auth.uid() and exists (
    select 1 from public.career_conversations c
    join public.career_applications a on a.id=c.application_id
    join public.career_jobs j on j.id=a.job_id
    where c.id=conversation_id and (a.candidate_id=auth.uid() or exists (
      select 1 from public.career_organization_members m where m.organization_id=j.organization_id
        and m.user_id=auth.uid() and m.membership_status='active'))));
revoke all on public.career_conversations, public.career_messages from anon;
grant select on public.career_conversations to authenticated;
grant select,insert on public.career_messages to authenticated;

create or replace function public.career_create_application_conversation()
returns trigger language plpgsql security definer set search_path=''
as $$
begin
  insert into public.career_conversations(application_id) values(new.id)
    on conflict (application_id) do nothing;
  return new;
end;
$$;
revoke all on function public.career_create_application_conversation() from public,anon,authenticated;
create trigger career_application_conversation_after_insert after insert on public.career_applications
  for each row execute function public.career_create_application_conversation();

create or replace function public.career_touch_conversation()
returns trigger language plpgsql security definer set search_path=''
as $$
begin
  update public.career_conversations set last_message_at=new.created_at where id=new.conversation_id;
  return new;
end;
$$;
revoke all on function public.career_touch_conversation() from public,anon,authenticated;
create trigger career_message_touch_after_insert after insert on public.career_messages
  for each row execute function public.career_touch_conversation();

comment on table public.career_profiles is 'Career Giver profile; public visibility exposes only explicitly authored profile fields.';
comment on table public.career_organizations is 'Employer organization; verification status is controlled by trusted administration.';
comment on table public.career_applications is 'Candidate applications; access restricted to the candidate and active employer members.';
comment on table public.career_messages is 'Private application messages; readable only by application participants.';


-- Harden membership lookups without recursive RLS evaluation.
create or replace function public.career_is_org_member(p_org uuid, p_roles text[] default null)
returns boolean language sql stable security definer set search_path=''
as $$
  select exists (
    select 1 from public.career_organization_members m
    where m.organization_id=p_org and m.user_id=auth.uid()
      and m.membership_status='active'
      and (p_roles is null or m.member_role = any(p_roles))
  );
$$;
create or replace function public.career_can_access_application(p_application uuid)
returns boolean language sql stable security definer set search_path=''
as $$
  select exists (
    select 1 from public.career_applications a
    join public.career_jobs j on j.id=a.job_id
    where a.id=p_application and (
      a.candidate_id=auth.uid() or public.career_is_org_member(j.organization_id,null)
    )
  );
$$;
revoke all on function public.career_is_org_member(uuid,text[]) from public,anon;
revoke all on function public.career_can_access_application(uuid) from public,anon;
grant execute on function public.career_is_org_member(uuid,text[]) to authenticated;
grant execute on function public.career_can_access_application(uuid) to authenticated;

-- Verification is an administrative decision: authenticated organization members
-- may edit descriptive fields but cannot change verification_status or created_by.
revoke update on public.career_organizations from authenticated;
grant update(name,website,description,country_code) on public.career_organizations to authenticated;

-- Membership writes are reserved for trusted administrative onboarding for now.
drop policy career_org_members_owner_manage on public.career_organization_members;
revoke insert,update,delete on public.career_organization_members from authenticated;
grant select on public.career_organization_members to authenticated;

drop policy career_org_read on public.career_organizations;
create policy career_org_read on public.career_organizations for select to authenticated
  using (verification_status='verified' or created_by=auth.uid()
    or public.career_is_org_member(id,null));
drop policy career_org_members_read on public.career_organization_members;
create policy career_org_members_read on public.career_organization_members for select to authenticated
  using (user_id=auth.uid() or public.career_is_org_member(organization_id,null));
drop policy career_org_update on public.career_organizations;
create policy career_org_update on public.career_organizations for update to authenticated
  using (public.career_is_org_member(id,array['owner','admin']))
  with check (public.career_is_org_member(id,array['owner','admin']));

drop policy career_jobs_read on public.career_jobs;
create policy career_jobs_read on public.career_jobs for select to authenticated
  using (status='published' or public.career_is_org_member(organization_id,null));
drop policy career_jobs_insert on public.career_jobs;
create policy career_jobs_insert on public.career_jobs for insert to authenticated
  with check (created_by=auth.uid() and status='draft'
    and public.career_is_org_member(organization_id,array['owner','admin','recruiter'])
    and exists (select 1 from public.career_organizations o
      where o.id=organization_id and o.verification_status='verified'));
drop policy career_jobs_update on public.career_jobs;
create policy career_jobs_update on public.career_jobs for update to authenticated
  using (public.career_is_org_member(organization_id,array['owner','admin','recruiter']))
  with check (public.career_is_org_member(organization_id,array['owner','admin','recruiter'])
    and (status<>'published' or exists (select 1 from public.career_organizations o
      where o.id=organization_id and o.verification_status='verified')));

drop policy career_applications_read on public.career_applications;
create policy career_applications_read on public.career_applications for select to authenticated
  using (candidate_id=auth.uid() or exists (select 1 from public.career_jobs j
    where j.id=job_id and public.career_is_org_member(j.organization_id,null)));
drop policy career_applications_employer_update on public.career_applications;
create policy career_applications_employer_update on public.career_applications for update to authenticated
  using (exists (select 1 from public.career_jobs j where j.id=job_id
    and public.career_is_org_member(j.organization_id,array['owner','admin','recruiter'])))
  with check (exists (select 1 from public.career_jobs j where j.id=job_id
    and public.career_is_org_member(j.organization_id,array['owner','admin','recruiter'])));

drop policy career_conversations_participant_read on public.career_conversations;
create policy career_conversations_participant_read on public.career_conversations for select to authenticated
  using (public.career_can_access_application(application_id));
drop policy career_messages_participant_read on public.career_messages;
create policy career_messages_participant_read on public.career_messages for select to authenticated
  using (exists (select 1 from public.career_conversations c
    where c.id=conversation_id and public.career_can_access_application(c.application_id)));
drop policy career_messages_participant_insert on public.career_messages;
create policy career_messages_participant_insert on public.career_messages for insert to authenticated
  with check (sender_id=auth.uid() and exists (select 1 from public.career_conversations c
    where c.id=conversation_id and public.career_can_access_application(c.application_id)));


-- Prevent clients from rewriting application/job ownership keys through broad UPDATE grants.
revoke update on public.career_jobs from authenticated;
grant update(title,description,employment_type,workplace_type,location,
  salary_min,salary_max,salary_currency,status,published_at)
  on public.career_jobs to authenticated;
revoke update on public.career_applications from authenticated;
grant update(status,cover_letter) on public.career_applications to authenticated;

drop policy career_applications_insert on public.career_applications;
create policy career_applications_insert on public.career_applications for insert to authenticated
  with check (candidate_id=auth.uid() and status='submitted' and exists (
    select 1 from public.career_jobs j where j.id=job_id and j.status='published'));
