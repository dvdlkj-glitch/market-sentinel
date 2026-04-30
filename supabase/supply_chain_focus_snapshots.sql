create table if not exists public.supply_chain_focus_snapshots (
  id bigint generated always as identity primary key,
  config_key text not null,
  as_of_date date not null,
  fetched_at timestamptz not null default timezone('utc', now()),
  period text not null,
  interval text not null,
  lens_title text not null,
  status text not null default 'ready',
  snapshot_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint supply_chain_focus_snapshots_group_day_lens_key
    unique (config_key, as_of_date, period, interval, lens_title)
);

create index if not exists supply_chain_focus_snapshots_lookup_idx
  on public.supply_chain_focus_snapshots (config_key, as_of_date desc, fetched_at desc);

create or replace function public.set_supply_chain_focus_snapshots_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists set_supply_chain_focus_snapshots_updated_at on public.supply_chain_focus_snapshots;

create trigger set_supply_chain_focus_snapshots_updated_at
before update on public.supply_chain_focus_snapshots
for each row
execute function public.set_supply_chain_focus_snapshots_updated_at();

alter table public.supply_chain_focus_snapshots enable row level security;

comment on table public.supply_chain_focus_snapshots is
'Snapshot-first cache for each supply-chain focus group used by the Supply Chain Lab overview and chain compare views.';

comment on column public.supply_chain_focus_snapshots.snapshot_payload is
'Serialized supply-chain focus snapshot payload written by the supply-chain prefetch job.';

-- Keep the table private by default. The Streamlit app reads it using the
-- service-role fallback and the GitHub Action writes with the same secret.
