create table if not exists public.active_etf_snapshots (
  id bigint generated always as identity primary key,
  ticker text not null,
  as_of_date date not null,
  fetched_at timestamptz not null default timezone('utc', now()),
  period text not null,
  interval text not null,
  lens_title text not null,
  status text not null default 'ready',
  snapshot_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint active_etf_snapshots_ticker_day_lens_key
    unique (ticker, as_of_date, period, interval, lens_title)
);

create index if not exists active_etf_snapshots_lookup_idx
  on public.active_etf_snapshots (ticker, as_of_date desc, fetched_at desc);

create or replace function public.set_active_etf_snapshots_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_active_etf_snapshots_updated_at on public.active_etf_snapshots;

create trigger set_active_etf_snapshots_updated_at
before update on public.active_etf_snapshots
for each row
execute function public.set_active_etf_snapshots_updated_at();

alter table public.active_etf_snapshots enable row level security;

comment on table public.active_etf_snapshots is
'Daily Active ETF dashboard snapshots used by Workspace and Compare for fast DB-first loading.';

comment on column public.active_etf_snapshots.snapshot_payload is
'Serialized dashboard snapshot payload written by the Active ETF prefetch job.';

-- Keep the table private by default. The Streamlit app can read it with
-- SUPABASE_SERVICE_ROLE_KEY fallback, and the GitHub Action writes with the
-- same secret. If you prefer publishable-key reads, add a select policy such as:
--
-- create policy "active_etf_snapshots_public_read"
-- on public.active_etf_snapshots
-- for select
-- to anon, authenticated
-- using (true);
