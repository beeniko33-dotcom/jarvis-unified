-- Career Giver foundation: profiles, organizations, jobs, applications and participant-only messaging.
-- Verification evidence files are deliberately not stored in these tables; use private Storage with short-lived signed access in a later reviewed change.
create table if not exists public.career_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (length(trim(display_name)) between 1 and 120),
  headline text check (headline is null or length(headline) <= 180),
  bio text check (bio is null or length(bio) <= 4000),
  location text check (location is null or length(location) <= 160),
  skills text[] not null default '{}',
  visibility text not null default 'private' check (visibility in ('private','public')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.career_organizations (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id) on delete restrict,
  name text not null check (length(trim(name)) between 2 and 180),
  website text check (website is null or length(website) <= 500),
  business_email_domain text check (business_email_domain is null or length(business_email_domain) <= 255),
  verification_status text not null default 'pending' check (verification_status in ('pending','verified','rejected','suspended')),
  is_public boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.career_org_memberships (
  organization_id uuid not null references public.career_organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner','admin','recruiter','viewer')),
  created_at timestamptz not null default now(),
  primary key (organization_id,user_id)
);

create table if not exists public.career_employer_verifications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.career_organizations(id) on delete cascade,
  submitted_by uuid not null references auth.users(id) on delete restrict,
  status text not null default 'pending' check (status in ('pending','approved','rejected','needs_information')),
  evidence_storage_path text,
  reviewer_note text check (reviewer_note is null or length(reviewer_note) <= 2000),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  check (evidence_storage_path is null or length(evidence_storage_path) <= 500)
);

create table if not exists public.career_jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.career_organizations(id) on delete restrict,
  created_by uuid not null references auth.users(id) on delete restrict,
  title text not null check (length(trim(title)) between 3 and 180),
  description text not null check (length(trim(description)) between 20 and 20000),
  employment_type text not null check (employment_type in ('full_time','part_time','contract','internship','temporary')),
  workplace_type text not null default 'onsite' check (workplace_type in ('onsite','hybrid','remote')),
  location text check (location is null or length(location) <= 180),
  salary_currency text check (salary_currency is null or salary_currency ~ '^[A-Z]{3}$'),
  salary_min numeric(14,2) check (salary_min is null or salary_min >= 0),
  salary_max numeric(14,2) check (salary_max is null or salary_max >= 0),
  status text not null default 'draft' check (status in ('draft','published','paused','closed')),
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (salary_min is null or salary_max is null or salary_max >= salary_min)
);

create table if not exists public.career_applications (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.career_jobs(id) on delete restrict,
  applicant_user_id uuid not null references auth.users(id) on delete restrict,
  cover_note text check (cover_note is null or length(cover_note) <= 8000),
  status text not null default 'submitted' check (status in ('submitted','reviewing','shortlisted','interview','offered','rejected','withdrawn','hired')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (job_id,applicant_user_id)
);

create table if not exists public.career_conversations (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id) on delete restrict,
  application_id uuid references public.career_applications(id) on delete set null,
  subject text check (subject is null or length(subject) <= 180),
  created_at timestamptz not null default now()
);

create table if not exists public.career_conversation_participants (
  conversation_id uuid not null references public.career_conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  joined_at timestamptz not null default now(),
  primary key (conversation_id,user_id)
);

create table if not exists public.career_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.career_conversations(id) on delete cascade,
  sender_user_id uuid not null references auth.users(id) on delete restrict,
  body text not null check (length(trim(body)) between 1 and 10000),
  created_at timestamptz not null default now(),
  read_at timestamptz
);

create index if not exists career_jobs_public_search_idx on public.career_jobs(status, published_at desc);
create index if not exists career_jobs_org_idx on public.career_jobs(organization_id, created_at desc);
create index if not exists career_applications_applicant_idx on public.career_applications(applicant_user_id, created_at desc);
create index if not exists career_applications_job_idx on public.career_applications(job_id, created_at desc);
create index if not exists career_messages_conversation_idx on public.career_messages(conversation_id, created_at);

alter table public.career_profiles enable row level security;
alter table public.career_organizations enable row level security;
alter table public.career_org_memberships enable row level security;
alter table public.career_employer_verifications enable row level security;
alter table public.career_jobs enable row level security;
alter table public.career_applications enable row level security;
alter table public.career_conversations enable row level security;
alter table public.career_conversation_participants enable row level security;
alter table public.career_messages enable row level security;

revoke all on public.career_profiles, public.career_organizations, public.career_org_memberships,
  public.career_employer_verifications, public.career_jobs, public.career_applications,
  public.career_conversations, public.career_conversation_participants, public.career_messages
  from anon, authenticated;
grant select, insert, update on public.career_profiles to authenticated;
grant select, insert on public.career_organizations to authenticated;
grant select on public.career_org_memberships to authenticated;
grant select, insert on public.career_jobs to authenticated;
grant select, insert, update on public.career_applications to authenticated;
grant select on public.career_conversations, public.career_conversation_participants to authenticated;
grant select, insert on public.career_messages to authenticated;
grant all on public.career_profiles, public.career_organizations, public.career_org_memberships,
  public.career_employer_verifications, public.career_jobs, public.career_applications,
  public.career_conversations, public.career_conversation_participants, public.career_messages
  to service_role;

drop policy if exists career_profiles_read on public.career_profiles;
create policy career_profiles_read on public.career_profiles for select to authenticated
  using (user_id = (select auth.uid()) or visibility = 'public');
drop policy if exists career_profiles_insert on public.career_profiles;
create policy career_profiles_insert on public.career_profiles for insert to authenticated
  with check (user_id = (select auth.uid()));
drop policy if exists career_profiles_update on public.career_profiles;
create policy career_profiles_update on public.career_profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists career_orgs_read on public.career_organizations;
create policy career_orgs_read on public.career_organizations for select to authenticated
  using (created_by = (select auth.uid()) or (is_public = true and verification_status = 'verified'));
drop policy if exists career_orgs_insert on public.career_organizations;
create policy career_orgs_insert on public.career_organizations for insert to authenticated
  with check (created_by = (select auth.uid()) and verification_status = 'pending' and is_public = false);

drop policy if exists career_memberships_read_self on public.career_org_memberships;
create policy career_memberships_read_self on public.career_org_memberships for select to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists career_verifications_read_submitter on public.career_employer_verifications;
create policy career_verifications_read_submitter on public.career_employer_verifications for select to authenticated
  using (submitted_by = (select auth.uid()));

drop policy if exists career_jobs_public_read on public.career_jobs;
create policy career_jobs_public_read on public.career_jobs for select to authenticated
  using (status = 'published');
drop policy if exists career_jobs_insert_recruiter on public.career_jobs;
create policy career_jobs_insert_recruiter on public.career_jobs for insert to authenticated
  with check (
    created_by = (select auth.uid()) and status = 'draft'
    and exists (
      select 1 from public.career_org_memberships m
      where m.organization_id = career_jobs.organization_id
        and m.user_id = (select auth.uid())
        and m.role in ('owner','admin','recruiter')
    )
  );

drop policy if exists career_applications_read_parties on public.career_applications;
create policy career_applications_read_parties on public.career_applications for select to authenticated
  using (
    applicant_user_id = (select auth.uid())
    or exists (
      select 1 from public.career_jobs j
      join public.career_org_memberships m on m.organization_id = j.organization_id
      where j.id = career_applications.job_id
        and m.user_id = (select auth.uid())
        and m.role in ('owner','admin','recruiter','viewer')
    )
  );
drop policy if exists career_applications_insert_self on public.career_applications;
create policy career_applications_insert_self on public.career_applications for insert to authenticated
  with check (
    applicant_user_id = (select auth.uid())
    and status = 'submitted'
    and exists (select 1 from public.career_jobs j where j.id = career_applications.job_id and j.status = 'published')
  );
drop policy if exists career_applications_withdraw_self on public.career_applications;
create policy career_applications_withdraw_self on public.career_applications for update to authenticated
  using (applicant_user_id = (select auth.uid()) and status = 'submitted')
  with check (applicant_user_id = (select auth.uid()) and status = 'withdrawn');

drop policy if exists career_conversations_read_participant on public.career_conversations;
create policy career_conversations_read_participant on public.career_conversations for select to authenticated
  using (exists (select 1 from public.career_conversation_participants p where p.conversation_id = career_conversations.id and p.user_id = (select auth.uid())));
drop policy if exists career_conversation_participants_read_self on public.career_conversation_participants;
create policy career_conversation_participants_read_self on public.career_conversation_participants for select to authenticated
  using (user_id = (select auth.uid()));
drop policy if exists career_messages_read_participant on public.career_messages;
create policy career_messages_read_participant on public.career_messages for select to authenticated
  using (exists (select 1 from public.career_conversation_participants p where p.conversation_id = career_messages.conversation_id and p.user_id = (select auth.uid())));
drop policy if exists career_messages_insert_participant on public.career_messages;
create policy career_messages_insert_participant on public.career_messages for insert to authenticated
  with check (
    sender_user_id = (select auth.uid())
    and exists (select 1 from public.career_conversation_participants p where p.conversation_id = career_messages.conversation_id and p.user_id = (select auth.uid()))
  );

comment on table public.career_employer_verifications is 'Verification workflow metadata only. Store evidence in a private, access-controlled storage bucket; never expose identity documents publicly.';
comment on table public.career_messages is 'Private participant-only Career Giver messages. Access is enforced through conversation participant membership.';
