begin;
create schema if not exists extensions;
create extension if not exists vector with schema extensions;
create schema if not exists devmind;
revoke all on schema devmind from public, anon, authenticated;
set local search_path = devmind,extensions,public;

-- One personal workspace per verified Supabase user.
create table workspaces (
 id uuid primary key references auth.users(id) on delete cascade,
 email text, created_at timestamptz not null default now()
);
create table repositories (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references workspaces on delete cascade,
 url text not null, name text not null, sha text, metadata jsonb not null default '{}',
 embedding_model text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(owner_id,url)
);
create table jobs (
 id uuid primary key default gen_random_uuid(), repo_id uuid not null references repositories on delete cascade,
 status text not null, stage text not null, done integer not null default 0,total integer not null default 0,
 error text, created_at timestamptz not null default now()
);
create unique index one_job on jobs(repo_id) where status in ('queued','running');
create index jobs_latest on jobs(repo_id,created_at desc);
create table files (
 repo_id uuid references repositories on delete cascade,path text,language text not null,text text not null,
 lines integer not null,parsed boolean not null,primary key(repo_id,path)
);
create table symbols (
 repo_id uuid,path text,name text not null,kind text not null,start_line integer,end_line integer,
 foreign key(repo_id,path) references files on delete cascade
);
create index symbols_repo on symbols(repo_id,path);
create table edges (
 repo_id uuid,path text,target text not null,kind text not null,line integer not null,
 foreign key(repo_id,path) references files on delete cascade, unique(repo_id,path,target,kind,line)
);
create table chunks (
 id text primary key,repo_id uuid,path text,sha text not null,language text,symbol text,
 start_line integer not null,end_line integer not null,text text not null,content_hash text not null,
 embedding vector(768) not null,created_at timestamptz not null default now(),
 foreign key(repo_id,path) references files on delete cascade
);
create index chunks_repo on chunks(repo_id,path);
create index chunks_fts on chunks using gin(to_tsvector('simple',text));
-- Each repository has one persistent conversation. Citations retain commit-specific excerpts.
create table entries (
 id bigint generated always as identity primary key,repo_id uuid not null references repositories on delete cascade,
 kind text not null check(kind in ('ask','documents')),question text not null,answer text not null,
 citations jsonb not null,created_at timestamptz not null default now()
);
create index entries_repo on entries(repo_id,id);
create table usage (
 owner_id uuid references workspaces on delete cascade,day date not null,kind text,used int not null,
 primary key(owner_id,day,kind)
);
do $$ declare t text; begin
 foreach t in array array['workspaces','repositories','jobs','files','symbols','edges','chunks','entries','usage']
 loop execute format('alter table devmind.%I enable row level security',t); end loop;
end $$;
commit;
