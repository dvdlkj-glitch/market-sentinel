create table if not exists public.taiwan_official_snapshots (
  id bigint generated always as identity primary key,
  snapshot_kind text not null,
  ticker text not null,
  as_of_date date not null,
  fetched_at timestamptz not null default timezone('utc', now()),
  status text not null default 'ready',
  snapshot_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint taiwan_official_snapshots_kind_ticker_day_key
    unique (snapshot_kind, ticker, as_of_date)
);

create index if not exists taiwan_official_snapshots_lookup_idx
  on public.taiwan_official_snapshots (snapshot_kind, ticker, as_of_date desc, fetched_at desc);

create or replace function public.set_taiwan_official_snapshots_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_taiwan_official_snapshots_updated_at on public.taiwan_official_snapshots;

create trigger set_taiwan_official_snapshots_updated_at
before update on public.taiwan_official_snapshots
for each row
execute function public.set_taiwan_official_snapshots_updated_at();

alter table public.taiwan_official_snapshots enable row level security;

comment on table public.taiwan_official_snapshots is
'Snapshot-first cache for the Taiwan official data layer, including shared macro backdrop and per-ticker official payloads.';

comment on column public.taiwan_official_snapshots.snapshot_payload is
'Serialized Taiwan official dashboard snapshot payload written by the official prefetch job.';

-- Keep the table private by default. The Streamlit app reads it using the
-- service-role fallback and the GitHub Action writes with the same secret.
