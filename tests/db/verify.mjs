// Runs the production migration against a fresh, isolated PostgreSQL WASM instance.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';
import { vector } from '@electric-sql/pglite-pgvector';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';

const db = await PGlite.create({extensions: {vector}});
const migration = await readFile(new URL('../../database/001_initial.sql', import.meta.url), 'utf8');
await db.exec(`
  create role anon;
  create role authenticated;
  create schema auth;
  create table auth.users (id uuid primary key);
`);
await db.exec(migration);
await db.exec('set search_path to devmind, extensions, public');
const version = await db.query("select extversion from pg_extension where extname = 'vector'");
console.log('Migrated an empty database with pgvector', version.rows[0].extversion);

const owner = randomUUID();
await db.query('insert into auth.users values ($1)', [owner]);
await db.query('insert into workspaces (id) values ($1)', [owner]);
const repo = await db.query(
  'insert into repositories (owner_id, url, name) values ($1,$2,$3) returning id',
  [owner, 'https://github.com/test/fixture', 'fixture']
);
const repoId = repo.rows[0].id;
await db.query("insert into jobs (repo_id,status,stage) values ($1,'queued','Validating repository')", [repoId]);
await assert.rejects(
  db.query("insert into jobs (repo_id,status,stage) values ($1,'queued','Validating repository')", [repoId]),
  {code: '23505'}
);
await db.query("insert into files values ($1,'fixture.py','Python','pass',1,true)", [repoId]);
// Deterministic basis vectors test the SQL storage and distance operator in isolation.
const basis = (axis) => JSON.stringify(Array.from({length: 768}, (_, i) => Number(i === axis)));
for (const axis of [0, 1]) {
  await db.query(`
    insert into chunks(id,repo_id,path,sha,language,start_line,end_line,text,content_hash,embedding)
    values($1,$2,'fixture.py','fixture','Python',1,1,'pass','fixture',$3::vector)
  `, [String(axis), repoId, basis(axis)]);
}
const ranked = await db.query('select id, vector_dims(embedding) as dims from chunks where repo_id=$1 order by embedding <=> $2::vector', [repoId, basis(1)]);
assert.deepEqual(ranked.rows, [{id:'1',dims:768},{id:'0',dims:768}]);
await assert.rejects(db.query("update chunks set embedding='[1]'::vector"), {code: '22000'});

for (const role of ['anon', 'authenticated']) {
  await db.exec(`set role ${role}`);
  await assert.rejects(db.query('select * from devmind.chunks'), {code: '42501'});
  await db.exec('reset role');
}
await db.query('delete from auth.users where id=$1', [owner]);
for (const table of ['workspaces','repositories','jobs','files','chunks']) {
  const count = await db.query(`select count(*)::integer as count from ${table}`);
  assert.equal(count.rows[0].count, 0);
}
console.log('Passed active-job uniqueness, vector ranking and dimensions, browser-role denial, and account cascade.');

if (process.argv.includes('--serve')) {
  const port = Number(process.env.TEST_DB_PORT ?? '55439');
  const server = new PGLiteSocketServer({db, port, host:'127.0.0.1', maxConnections:8});
  await server.start();
  console.log(`Ephemeral test database listening at 127.0.0.1:${port}`);
  process.once('SIGINT', async () => { await server.stop(); await db.close(); });
} else {
  await db.close();
}
