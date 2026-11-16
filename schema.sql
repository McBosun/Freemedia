create table if not exists videos (
  id uuid primary key default gen_random_uuid(),
  owner uuid references auth.users(id) on delete cascade default auth.uid(),
  title text not null,
  raw_path text,                 -- path in raw-uploads bucket
  hls_path text,                 -- e.g. <id>/master.m3u8 in hls bucket
  status text not null default 'uploaded'
    check (status in ('uploaded','processing','ready','failed')),
  error text,
  views bigint not null default 0,
  created_at timestamptz not null default now()
);
create index on videos (status, created_at);

create table if not exists live_streams (
  id uuid primary key default gen_random_uuid(),
  owner uuid references auth.users(id) on delete cascade default auth.uid(),
  title text not null,
  stream_key text not null default encode(gen_random_bytes(12),'hex'),
  is_live boolean not null default false,
  created_at timestamptz not null default now()
);

alter table videos enable row level security;
alter table live_streams enable row level security;

create policy "public reads ready videos" on videos for select using (status = 'ready' or owner = auth.uid());
create policy "owner inserts videos" on videos for insert with check (owner = auth.uid());
create policy "owner updates videos" on videos for update using (owner = auth.uid());
create policy "owner deletes videos" on videos for delete using (owner = auth.uid());

create policy "public reads streams" on live_streams for select using (true);
create policy "owner manages streams" on live_streams for all using (owner = auth.uid()) with check (owner = auth.uid());
