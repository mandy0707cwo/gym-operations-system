// 隔離 PostgreSQL，全部虛構資料；不連正式 Supabase。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const runtime=process.env.PGLITE_RUNTIME||path.join(root,'output/qa_atomic_runtime/node_modules/@electric-sql/pglite/dist/index.js');
const {PGlite}=await import(pathToFileURL(runtime).href);
const db=new PGlite();
const migration=fs.readFileSync(path.join(root,'migration_course_purchase_defaults_v1_13_10.sql'),'utf8');
let checks=0;
const check=(label,fn)=>{fn();checks++;console.log('PASS '+label);};
await db.exec(`
create role authenticated;
create table public.course_catalog(id integer primary key, course_name text unique not null,
  course_type text not null default '訓練', report_category text not null default '測試',
  session_hours numeric(4,2) not null default 1, active boolean not null default true,
  created_at timestamptz not null default '2026-01-01');
insert into public.course_catalog(id,course_name) select i,'虛構課程'||i from generate_series(1,6) i;
create table public.purchases(id integer primary key,total_sessions integer,total_amount numeric,note text);
insert into public.purchases values(1,10,10500,'原成交備註');
alter table public.course_catalog enable row level security;
create function public.is_admin() returns boolean language sql stable as
$$ select current_setting('app.test_admin',true)='true' $$;
create policy course_catalog_read on public.course_catalog for select to authenticated using(true);
create policy course_catalog_admin_insert on public.course_catalog for insert to authenticated with check(public.is_admin());
create policy course_catalog_admin_update on public.course_catalog for update to authenticated using(public.is_admin()) with check(public.is_admin());
create policy course_catalog_admin_delete on public.course_catalog for delete to authenticated using(public.is_admin());
grant usage on schema public to authenticated;
grant select,insert,update,delete on public.course_catalog to authenticated;
`);
const oldFields='id,course_name,course_type,report_category,session_hours,active,created_at';
const before=JSON.stringify((await db.query('select '+oldFields+' from public.course_catalog order by id')).rows);
const purchases=JSON.stringify((await db.query('select * from public.purchases')).rows);
const policies=JSON.stringify((await db.query("select policyname,roles,cmd,qual,with_check from pg_policies where tablename='course_catalog' order by policyname")).rows);
await db.exec(migration);
const after=JSON.stringify((await db.query('select '+oldFields+' from public.course_catalog order by id')).rows);
check('original six course records and fields unchanged',()=>assert.equal(after,before));
const blanks=(await db.query('select default_sessions,default_total_amount,note from public.course_catalog')).rows;
assert.equal(blanks.length,6);
check('all new defaults remain NULL without backfill',()=>assert.ok(blanks.every(x=>x.default_sessions===null&&x.default_total_amount===null&&x.note===null)));
const columns=(await db.query("select column_name,is_nullable,column_default from information_schema.columns where table_schema='public' and table_name='course_catalog' and column_name in ('default_sessions','default_total_amount','note')")).rows;
check('three nullable columns with no assigned defaults',()=>{assert.equal(columns.length,3);assert.ok(columns.every(x=>x.is_nullable==='YES'&&x.column_default===null));});
await db.exec("update public.course_catalog set default_sessions=6,default_total_amount=8888,note='虛構備註' where id=1");
const setValue=JSON.stringify((await db.query('select * from public.course_catalog order by id')).rows);
await db.exec(migration);
const rerun=JSON.stringify((await db.query('select * from public.course_catalog order by id')).rows);
check('safe rerun preserves saved defaults',()=>assert.equal(rerun,setValue));
for(const [field,value] of [['default_sessions','0'],['default_sessions','-1'],['default_sessions','1000'],
 ['default_total_amount','0'],['default_total_amount','-1'],['default_total_amount','10000001'],['default_total_amount',"'NaN'"]]){
 let rejected=false;
 try{await db.exec('update public.course_catalog set '+field+'='+value+' where id=1');}catch(e){rejected=e.code==='23514';}
 check('constraint rejects '+field+'='+value,()=>assert.ok(rejected));
}
await db.exec('update public.course_catalog set default_sessions=null,default_total_amount=null,note=null where id=1');
const clear=(await db.query('select default_sessions,default_total_amount,note from public.course_catalog where id=1')).rows[0];
check('clearing defaults stores NULL',()=>assert.deepEqual(clear,{default_sessions:null,default_total_amount:null,note:null}));
const newPolicies=JSON.stringify((await db.query("select policyname,roles,cmd,qual,with_check from pg_policies where tablename='course_catalog' order by policyname")).rows);
check('existing RLS policies unchanged',()=>assert.equal(newPolicies,policies));
const rls=(await db.query("select relrowsecurity from pg_class where oid='public.course_catalog'::regclass")).rows[0].relrowsecurity;
check('RLS remains enabled',()=>assert.equal(rls,true));
await db.exec("set role authenticated; set app.test_admin='false'");
const readable=(await db.query('select id,default_sessions,default_total_amount,note from public.course_catalog')).rows;
check('existing authenticated catalog read remains available',()=>assert.equal(readable.length,6));
const denied=await db.query("update public.course_catalog set default_sessions=4 where id=1 returning id");
check('nonadmin update gains no privilege',()=>assert.equal(denied.rows.length,0));
await db.exec("set app.test_admin='true'");
const allowed=await db.query("update public.course_catalog set default_sessions=4 where id=1 returning default_sessions");
check('existing admin policy can set defaults',()=>assert.equal(allowed.rows[0].default_sessions,4));
await db.exec('reset role');
const finalPurchases=JSON.stringify((await db.query('select * from public.purchases')).rows);
check('historical purchase amounts, sessions and notes unchanged',()=>assert.equal(finalPurchases,purchases));
console.log(JSON.stringify({checks,formalWrites:0,records:6}));
await db.close();
