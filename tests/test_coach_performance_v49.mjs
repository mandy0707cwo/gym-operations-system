// 真正的PostgreSQL引擎，全部合成資料，無網路／正式憑證。
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const {PGlite}=await import(pathToFileURL(process.env.PGLITE_RUNTIME).href);
const db=new PGlite();
const source=n=>readFileSync(resolve(root,n),'utf8');
const id=n=>'00000000-0000-4000-8000-'+String(n).padStart(12,'0');
const admin=id(1),manager=id(2),coach=id(3),coach2=id(4);
const value=async(sql,args=[])=>Object.values((await db.query(sql,args)).rows[0])[0];
let tests=0;
async function check(name,fn){await fn(); tests++;console.log('PASS '+name);}
async function as(actor,fn,role='authenticated'){
 await db.query("select set_config('request.jwt.claim.sub',$1,false)",[actor??'']);await db.exec('set role '+role);
 try{return await fn();}finally{await db.exec('reset role');}
}
const report=(who=manager,a='2026-10-01',b='2026-10-31')=>as(who,()=>value('select public.coach_performance_report($1,$2)',[a,b]));
const save=(who,key,rows,month='2026-10-01')=>as(who,()=>value('select public.save_coach_monthly_work_hours($1,$2,$3)',[key,month,JSON.stringify(rows)]));
const sum=(r,c,k)=>r.facts.filter(x=>x.coach_id===c&&x.metric===k).reduce((s,x)=>s+Number(x.value),0);
try{
 await db.exec(source('tests/fixtures/idempotency_setup.sql'));
 const finance=source('supabase/migrations/20261018091440_finance_center_v1_13_18.sql');
 await db.exec(finance.slice(finance.indexOf('create function public.finance_net_v1('),finance.indexOf('create function public.finance_session_net_v1(')));
 await db.exec(`create table public.profiles(id uuid primary key,username text,display_name text,role text,active boolean);
  create table public.purchases(id uuid primary key,coach_id uuid,member_id uuid,purchase_date date,expiry_date date,purchase_kind text,total_sessions integer,session_hours numeric,total_amount numeric,total_net_amount numeric,calculation_rule_version text);
  create table public.session_usages(id uuid primary key,purchase_id uuid,coach_id uuid,usage_date date,deducted_net_amount numeric,calculation_rule_version text);
  create table public.trial_items(id uuid primary key,coach_id uuid,entry_date date,amount numeric,net_amount numeric,hours numeric,calculation_rule_version text);
  create table public.single_sales(like public.trial_items including all);
  create table public.project_entries(id uuid primary key,coach_id uuid,entry_date date,line_amount numeric,net_amount numeric,item_hours numeric,quantity numeric,calculation_rule_version text);
  create table public.session_cancellations(coach_id uuid,cancel_date date,cancelled_sessions integer);
  create table public.course_terminations(id uuid primary key,purchase_id uuid,termination_date date,correction_posted_on date,reversed_at timestamptz);
  create table public.course_termination_events(purchase_id uuid,termination_date date,termination_type text,refund_net_amount numeric,is_reversal boolean,purchase_snapshot jsonb);
  insert into public.profiles values('${admin}','admin','合成管理員','admin',true),('${manager}','mgr','合成主管','manager',true),('${coach}','smc001','合成甲','coach',true),('${coach2}','smc002','合成乙','coach',true);
  insert into public.purchases values('${id(10)}','${coach}','${id(20)}','2026-09-01','2027-01-01','first',2,1,2100,2000,'historical-alignment-v3'),
   ('${id(11)}','${coach}','${id(21)}','2026-10-10','2027-01-01','renewal',4,.5,4200,4000,'historical-alignment-v3'),
   ('${id(12)}','${coach2}','${id(22)}','2026-09-01','2027-01-01','first',2,1,2100,2000,'historical-alignment-v3'),
   ('${id(13)}','${coach2}','${id(23)}','2026-09-01','2026-09-30','first',2,1,2100,2000,'historical-alignment-v3');
  insert into public.session_usages values('${id(30)}','${id(10)}','${coach2}','2026-09-30',1000,'historical-alignment-v3'),('${id(31)}','${id(10)}','${coach2}','2026-10-15',1000,'historical-alignment-v3');
  insert into public.trial_items values('${id(40)}','${coach}','2026-10-10',800,762,.5,'historical-alignment-v3'),('${id(41)}','${coach}','2026-10-11',0,0,.5,'historical-alignment-v3');
  insert into public.single_sales values('${id(42)}','${coach}','2026-10-12',1600,1524,1,'historical-alignment-v3');
  insert into public.project_entries values('${id(43)}','${coach}','2026-10-13',2100,2000,.5,2,'historical-alignment-v3');
  insert into public.session_cancellations values('${coach2}','2026-10-15',1);
  insert into public.course_terminations values('${id(50)}','${id(12)}','2026-10-15',null,'2026-11-01 00:00:00+08');
  insert into public.course_termination_events values('${id(12)}','2026-10-15','refund',1500,false,'{"coach_id":"${coach2}"}'),('${id(12)}','2026-11-01','refund',-1500,true,'{"coach_id":"${coach2}"}');
 `);
 await db.exec(source('supabase/migrations/20261121061449_coach_performance_monthly_hours_v1_13_49.sql'));
 await check('existing transaction rows unchanged; no default work hours',async()=>{
  assert.equal(await value('select count(*)::int from public.purchases'),4);
  assert.equal(await value('select count(*)::int from performance_private.monthly_hours'),0);
 });
 await check('owner sales vs executing coach; saved net; trial free/paid; project quantities',async()=>{
  const r=await report();assert.equal(r.schema_version,49);
  assert.equal(sum(r,coach,'sales_net'),4000);assert.equal(sum(r,coach2,'usage_net'),1000);
  assert.equal(sum(r,coach,'trial_visits'),2);assert.equal(sum(r,coach,'paid_trial_visits'),1);
  assert.equal(sum(r,coach,'oneoff_net'),4286);assert.equal(sum(r,coach,'project_hours'),1);
  assert.equal(sum(r,coach,'completed_courses'),1);assert.equal(sum(r,coach2,'completed_courses'),0);
  assert.ok(!JSON.stringify(r).includes(id(20)));assert.ok(!JSON.stringify(r).includes('purchase_id'));
 });
 await check('retention opening cohort distinct, new and expired excluded; termination at boundary',async()=>{
  const r=await report();const a=r.cohorts.find(x=>x.coach_id===coach),b=r.cohorts.find(x=>x.coach_id===coach2);
  assert.deepEqual([a.opening_members,a.retained_members],[1,0]);assert.deepEqual([b.opening_members,b.retained_members],[1,0]);
  const next=await report(manager,'2026-11-01','2026-11-30');
  assert.equal(sum(next,coach2,'refund_courses'),-1);assert.equal(sum(next,coach2,'refund_net'),-1500);
 });
 await check('multiple courses same member count once; renewal preserves cohort; late correction not backdated',async()=>{
  await db.exec(`insert into public.purchases values
    ('${id(14)}','${coach}','${id(20)}','2026-09-20','2027-01-01','renewal',1,1,1050,1000,'historical-alignment-v3'),
    ('${id(15)}','${coach}','${id(20)}','2026-10-20','2027-01-01','renewal',2,1,2100,2000,'historical-alignment-v3'),
    ('${id(16)}','${coach2}','${id(24)}','2026-09-20','2027-01-01','first',1,1,1050,1000,'historical-alignment-v3'),
    ('${id(17)}','${coach2}','${id(25)}','2026-09-20','2027-01-01','first',1,1,1050,1000,'historical-alignment-v3');
    insert into public.session_usages values
    ('${id(32)}','${id(14)}','${coach}','2026-10-22',1000,'historical-alignment-v3'),
    ('${id(33)}','${id(16)}','${coach2}','2026-10-15',1000,'historical-alignment-v3'),
    ('${id(34)}','${id(17)}','${coach2}','2026-10-15',1000,'historical-alignment-v3');
    insert into public.course_terminations values
    ('${id(51)}','${id(16)}','2026-10-14',null,null),
    ('${id(52)}','${id(17)}','2026-10-14','2026-10-25',null);`);
  const r=await report(),cohort=r.cohorts.find(x=>x.coach_id===coach);
  assert.deepEqual([cohort.opening_members,cohort.retained_members],[1,1]);
  assert.equal(sum(r,coach,'completed_courses'),2);assert.equal(sum(r,coach2,'completed_courses'),1);
 });
 await check('manager save idempotent, changed reuse rejected, versions protect concurrent updates',async()=>{
  const key=crypto.randomUUID(),rows=[{coach_id:coach,minutes:9600,revision:0}];
  const a=await save(manager,key,rows);assert.deepEqual(await save(manager,key,rows),a);
  await assert.rejects(save(manager,key,[{...rows[0],minutes:9000}]),/內容不同/);
  await assert.rejects(save(admin,crypto.randomUUID(),rows),/其他人修改/);
  const b=await save(admin,crypto.randomUUID(),[{coach_id:coach,minutes:9000,revision:1}]);
  assert.equal(b.hours[0].revision,2);assert.equal(b.hours[0].minutes,9000);
  assert.equal(await value('select count(*)::int from performance_private.hours_audit'),2);
  assert.equal(await value('select count(*)::int from performance_private.hours_receipts'),2);
 });
 await check('batch invalid value rolls back every row and receipt; explicit zero allowed',async()=>{
  const n=await value('select count(*)::int from performance_private.hours_audit');
  await assert.rejects(save(manager,crypto.randomUUID(),[{coach_id:coach,minutes:8000,revision:2},{coach_id:coach2,minutes:-1,revision:0}]),/工時需/);
  assert.equal(await value('select count(*)::int from performance_private.hours_audit'),n);
  assert.equal(await value('select minutes from performance_private.monthly_hours where coach_id=$1',[coach]),9000);
  const r=await save(manager,crypto.randomUUID(),[{coach_id:coach2,minutes:0,revision:0}]);assert.equal(r.hours.find(x=>x.coach_id===coach2).minutes,0);
  await assert.rejects(save(manager,crypto.randomUUID(),[{coach_id:coach2,minutes:42000,revision:1}],'2026-02-01'),/工時需/);
 });
 await check('coach/shared/disabled/anonymous cannot read or write; tables inaccessible even manager',async()=>{
  for(const role of ['coach','shared_coach','manager']){
   await db.query('update public.profiles set role=$1,active=$2 where id=$3',[role,role!=='manager',coach2]);
   await assert.rejects(report(coach2),/僅限有效/);
   await assert.rejects(save(coach2,crypto.randomUUID(),[{coach_id:coach2,minutes:1,revision:1}]),/僅限有效/);
  }
  await assert.rejects(as(null,()=>value("select public.coach_performance_report('2026-10-01','2026-10-31')"),'anon'),/permission denied/);
  await assert.rejects(as(manager,()=>value('select count(*) from performance_private.monthly_hours')),/permission denied/);
  await assert.rejects(as(manager,()=>value("update performance_private.monthly_hours set minutes=1 returning minutes")),/permission denied/);
 });
 await check('security catalog: all private tables use RLS; public RPCs invoker, anonymous blocked',async()=>{
  assert.equal(await value("select bool_and(c.relrowsecurity) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='performance_private' and c.relkind='r'"),true);
  for(const fn of ['coach_performance_report(date,date)','coach_monthly_work_hours(date)','save_coach_monthly_work_hours(uuid,date,jsonb)']){
   assert.equal(await value("select prosecdef from pg_proc where oid=$1::regprocedure",['public.'+fn]),false);
   assert.equal(await value("select has_function_privilege('anon',$1,'execute')",['public.'+fn]),false);
  }
  assert.equal(await value("select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='performance_private' and not ('search_path=\"\"'=any(p.proconfig))"),0);
 });
 await check('corrupt saved amount aborts entire report, never partial total',async()=>{
  await db.exec('update public.trial_items set net_amount=999');await assert.rejects(report(),/來源資料不完整/);
 });
 console.log(JSON.stringify({version:'v1.13.49',tests,passed:true,production_modified:false}));
}catch(error){console.error(error.message,error.code,error.position,error.detail??'');process.exitCode=1;}finally{await db.close();}
