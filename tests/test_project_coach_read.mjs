// 僅隔離記憶體 PostgreSQL 與虛構資料，不連正式 Supabase。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const runtime=process.env.PGLITE_RUNTIME || path.join(root,'output/qa_atomic_runtime/node_modules/@electric-sql/pglite/dist/index.js');
const {PGlite}=await import(pathToFileURL(runtime).href);
const db=new PGlite();
const sql=fs.readFileSync(path.join(root,'migration_project_coach_read_v1_13_7.sql'),'utf8');
const id=n=>`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
let checks=0;
const check=async(name,fn)=>{await fn();checks++;console.log('PASS '+name);};
async function actor(n,role='authenticated'){
 await db.exec('reset role');
 await db.query("select set_config('request.jwt.claim.sub',$1,false)",[n===null?'':id(n)]);
 await db.exec('set role '+role);
}
async function visible(){return (await db.query('select id from public.project_entries order by id')).rows.map(x=>x.id);}
try {
 await db.exec(`create role authenticated nologin; create role anon nologin; create schema auth;
 create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 create table public.profiles(id uuid primary key,role text,active boolean);
 create table public.project_entries(id int primary key,coach_id uuid,created_by uuid,entry_date date,item_hours numeric,quantity numeric,line_amount numeric);
 alter table public.profiles enable row level security;
 create policy profiles_read on public.profiles for select to authenticated using(active);
 create function public.is_manager() returns boolean language sql stable security definer set search_path=public as $$
 select exists(select 1 from public.profiles where id=auth.uid() and role in ('shared_coach','manager','admin') and active)$$;
 alter table public.project_entries enable row level security;
 create policy project_entries_read on public.project_entries for select to authenticated using(created_by=auth.uid() or public.is_manager());
 create policy project_entries_insert on public.project_entries for insert to authenticated with check(created_by=auth.uid());
 grant usage on schema public,auth to authenticated,anon;
 grant select on public.profiles,public.project_entries to authenticated,anon;
 grant insert on public.project_entries to authenticated;
 `);
 for(const [n,role,active] of [[1,'admin',true],[2,'coach',true],[3,'coach',true],[4,'manager',true],[5,'shared_coach',true],[6,'coach',false]])
  await db.query('insert into public.profiles values($1,$2,$3)',[id(n),role,active]);
 for(const [n,coach,creator] of [[1,2,1],[2,2,2],[3,3,1],[4,3,2],[5,6,1],[6,null,1]])
  await db.query("insert into public.project_entries values($1,$2,$3,'2026-10-05',1,1,1700)",[n,coach===null?null:id(coach),id(creator)]);
 const before=(await db.query('select jsonb_agg(to_jsonb(e) order by id) as data from public.project_entries e')).rows[0].data;
 await actor(2);
 await check('old policy hides administrator-entered own-coach row',async()=>assert.deepEqual(await visible(),[2,4]));
 await db.exec('reset role');
 await check('migration installs and safely reruns',async()=>{await db.exec(sql);await db.exec(sql);});
 await actor(2);
 await check('coach sees own assigned rows and retains original creator access',async()=>assert.deepEqual(await visible(),[1,2,4]));
 await check('hours include administrator entry without duplicates',async()=>assert.equal((await db.query('select sum(item_hours*quantity) as hours from public.project_entries where coach_id=$1',[id(2)])).rows[0].hours,'2'));
 await actor(3);
 await check('other coach sees only own assigned rows, not coach two',async()=>assert.deepEqual(await visible(),[3,4]));
 for(const [n,name] of [[1,'admin'],[4,'manager'],[5,'shared coach']]){
  await actor(n);await check(name+' retains original full read access',async()=>assert.deepEqual(await visible(),[1,2,3,4,5,6]));
 }
 await actor(6);await check('inactive coach gains no assigned-row access',async()=>assert.deepEqual(await visible(),[]));
 await actor(null);await check('missing identity gains no access',async()=>assert.deepEqual(await visible(),[]));
 await actor(null,'anon');await check('anonymous role gains no access',async()=>assert.deepEqual(await visible(),[]));
 await actor(2);
 await check('insert cannot forge creator',async()=>assert.rejects(db.query("insert into public.project_entries values(7,$1,$2,'2026-10-05',1,1,1700)",[id(2),id(1)]),/row-level security/));
 await check('no update permission added',async()=>assert.rejects(db.exec('update public.project_entries set item_hours=99 where id=1'),/permission denied/));
 await check('no delete permission added',async()=>assert.rejects(db.exec('delete from public.project_entries where id=1'),/permission denied/));
 await db.exec('reset role');
 await check('all original transaction values unchanged',async()=>assert.deepEqual((await db.query('select jsonb_agg(to_jsonb(e) order by id) as data from public.project_entries e')).rows[0].data,before));
 await check('only select predicate changed; RLS stays enabled',async()=>{
  const policies=(await db.query("select cmd,with_check from pg_policies where schemaname='public' and tablename='project_entries' order by cmd")).rows;
  assert.equal(policies.length,2);assert.equal(policies[0].cmd,'INSERT');assert.equal(policies[0].with_check,'(created_by = auth.uid())');
  assert.equal((await db.query("select relrowsecurity from pg_class where oid='public.project_entries'::regclass")).rows[0].relrowsecurity,true);
 });
 console.log(`Completed ${checks} isolated PostgreSQL checks.`);
} finally {await db.close();}
