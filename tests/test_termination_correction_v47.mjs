// PostgreSQL engine in memory only. No network or production data.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)), '..');
if (!process.env.PGLITE_RUNTIME) throw Error('Set PGLITE_RUNTIME to the local PGlite entry file');
const {PGlite}=await import(pathToFileURL(resolve(process.env.PGLITE_RUNTIME)).href);
const db=new PGlite();
const source=name=>readFileSync(resolve(root,name),'utf8').replace(/\r\n/g,'\n');
const v37='supabase/migrations/20261028095929_course_termination_reversal_v1_13_37.sql';
const v42='supabase/migrations/20261101022002_operations_completed_counts_v1_13_42.sql';
const v47='supabase/migrations/20261113030159_termination_correction_v1_13_47.sql';
const id=n=>'00000000-0000-4000-8000-'+String(n).padStart(12,'0');
const admin=id(1),coach=id(2),other=id(3),member=id(4);
const value=async(sql,args=[])=>Object.values((await db.query(sql,args)).rows[0])[0];
let tests=0;
async function check(name, test) {await test();tests++;console.log('PASS '+name);}
async function as(actor,fn,role='authenticated'){
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[actor??'']);
  await db.exec('set role '+role);
  try{return await fn();}finally{await db.exec('reset role');}
}
const todaySql="(clock_timestamp() at time zone 'Asia/Taipei')::date";
const today=()=>value(`select ${todaySql}::text`);
const originalDay=()=>value(`select (${todaySql}-2)::text`);
const beforeDay=()=>value(`select (${todaySql}-1)::text`);

async function buy(actor,coachId=other,dates={},key=crypto.randomUUID()) {
  const day=await today();
  const p={member_id:member,coach_id:coachId,course_name:'隔離測試課程',report_category:'測試',purchase_kind:'first',
    payment_plan:'full',installment_count:1,total_sessions:3,session_hours:1,total_amount:2100,
    purchase_date:dates.purchase??day,expiry_date:'2099-12-31'};
  return as(actor,()=>value('select public.create_purchase_idempotent($1,$2,$3)',[key,JSON.stringify(p),JSON.stringify({amount:2100,paid_date:dates.pay??day})]));
}
async function terminated(){
  const d=await originalDay();
  const p=await buy(admin,coach,{purchase:d,pay:d});
  const t=await as(admin,()=>value("select to_jsonb(public.terminate_course($1,$2,'expired',false,false,null,'合成原中止',null))",[p.id,d]));
  return {p,t,d};
}
async function correct(row,{actor=admin,role='authenticated',key=crypto.randomUUID(),date=row.d,reason='虛構更正',ack=true,reports=true,net=2000}={}){
  return as(actor,()=>value('select public.correct_course_termination($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)',
    [key,row.t.id,date,'refund',true,false,null,reason,null,ack,reports,net,400,1600]),role);
}

try {
  await db.exec(source('tests/fixtures/idempotency_setup.sql'));
  await db.exec(source('tests/fixtures/base_database.sql').replace('create extension if not exists pgcrypto;',''));
  await db.exec(source('tests/fixtures/idempotency_catalog.sql'));
  await db.exec(source('migration_purchase_code_v1_13_8.sql'));
  await db.exec(source('tests/fixtures/current_transaction_functions.sql'));
  await db.exec(source('migration_course_termination_v1_11_0.sql'));
  await db.exec(source('migration_bonus_rules_v1_8_0.sql'));
  await db.exec(`create schema finance_private;
    alter table public.purchases add column total_net_amount numeric default 0,add column calculation_rule_version text default 'historical-alignment-v3';
    alter table public.purchase_payments add column net_amount numeric default 0,add column calculation_rule_version text default 'historical-alignment-v3';
    alter table public.session_usages add column calculation_rule_version text default 'historical-alignment-v3';
    alter table public.course_terminations add column remaining_net_amount numeric default 0,add column recognized_net_amount numeric default 0,
      add column fee_net_amount numeric default 0,add column refund_net_amount numeric default 0,add column calculation_rule_version text default 'historical-alignment-v3';
    grant usage on schema public to anon,authenticated;
    grant select,insert,update on public.purchases,public.purchase_payments,public.course_terminations to authenticated;
    grant select on public.profiles,public.members,public.course_catalog,public.session_usages to authenticated;`);
  await db.exec(source('tests/fixtures/termination_v36_functions.sql'));
  for(const name of ['purchases','purchase_payments','session_usages','course_terminations']){
    await db.exec(`create trigger finance_rebuild after insert or update or delete on public.${name} for each row execute function finance_private.source_changed()`);
  }
  await db.exec(source('supabase/migrations/20261018111949_purchase_usage_idempotency_v1_13_19.sql'));
  await db.exec(source(v37));
  await db.exec(source(v42));
  const preexisting=await terminated();
  const original=await value('select to_jsonb(t) from public.course_terminations t where id=$1',[preexisting.t.id]);
  await db.exec(source(v47));
  await check('migration preserves original rows',async()=>{
    assert.deepEqual(await value("select to_jsonb(t)-'corrects_termination_id'-'correction_posted_on' from public.course_terminations t where id=$1",[preexisting.t.id]),original);
  });
  await check('correction saves atomic linked events and exact net values',async()=>{
    const x=await correct(preexisting);assert.equal(x.termination_id,preexisting.t.id);assert.equal(x.posted_on,await today());
    const saved=(await db.query('select corrects_termination_id,remaining_net_amount,fee_net_amount,refund_net_amount from public.course_terminations where id=$1',[x.id])).rows[0];
    assert.equal(saved.corrects_termination_id,preexisting.t.id);
    assert.deepEqual([saved.remaining_net_amount,saved.fee_net_amount,saved.refund_net_amount].map(Number),[2000,400,1600]);
    assert.deepEqual(await value("select to_jsonb(t)-'reversed_at'-'corrects_termination_id'-'correction_posted_on' from public.course_terminations t where id=$1",[preexisting.t.id]),Object.fromEntries(Object.entries(original).filter(([k])=>k!=='reversed_at')));
    assert.equal(await value('select status from public.purchases where id=$1',[preexisting.p.id]),'cancelled');
    assert.equal(await value('select count(*)::int from public.course_termination_events where purchase_id=$1 and termination_date <= $2',[preexisting.p.id,await beforeDay()]),1);
    assert.equal(await value('select count(*)::int from public.course_termination_events where purchase_id=$1 and termination_date=$2',[preexisting.p.id,await today()]),2);
    assert.equal(await value('select count(*)::int from public.purchase_payments where purchase_id=$1',[preexisting.p.id]),1);
  });
  await check('new termination failure rolls back reversal, state, receipt',async()=>{
    const row=await terminated();
    await assert.rejects(correct(row,{date:'2000-01-01'}),/不可早於成交/);
    await assert.rejects(correct(row,{net:1999}),/與確認畫面不符/);
    assert.equal(await value('select reversed_at is null from public.course_terminations where id=$1',[row.t.id]),true);
    assert.equal(await value('select count(*)::int from public.course_termination_reversals where termination_id=$1',[row.t.id]),0);
    assert.equal(await value('select count(*)::int from termination_private.correction_receipts where original_id=$1',[row.t.id]),0);
    assert.equal(await value('select status from public.purchases where id=$1',[row.p.id]),'expired');
  });
  await check('same operation returns original result; changed payload and duplicate denied',async()=>{
    const row=await terminated();const key=crypto.randomUUID();const a=await correct(row,{key});
    assert.deepEqual(await correct(row,{key}),a);
    await assert.rejects(correct(row,{key,reason:'不同原因'}),/內容不同/);
    await assert.rejects(correct(row),/已撤銷/);
    assert.equal(await value('select count(*)::int from public.course_terminations where purchase_id=$1',[row.p.id]),2);
  });
  await check('only active admins can correct and acknowledgment is required',async()=>{
    const row=await terminated();
    await assert.rejects(correct(row,{actor:coach}),/僅有效系統管理員/);
    await assert.rejects(correct(row,{actor:null,role:'anon'}),/permission denied/);
    await db.exec(`update public.profiles set role='manager' where id='${other}'`);
    await assert.rejects(correct(row,{actor:other}),/僅有效系統管理員/);
    await db.exec(`update public.profiles set role='coach' where id='${other}'`);
    await assert.rejects(correct(row,{ack:false}),/不完整/);
    await assert.rejects(correct(row,{reports:false}),/不完整/);
    assert.equal(await value('select reversed_at is null from public.course_terminations where id=$1',[row.t.id]),true);
  });
  await check('coach can create for other coach, still cannot see their purchase or pay retroactively',async()=>{
    const key=crypto.randomUUID();const p=await buy(coach,other,{},key);
    assert.deepEqual(await buy(coach,other,{},key),p);
    assert.equal(await value('select created_by from public.purchases where id=$1',[p.id]),coach);
    assert.equal(await value('select coach_id from public.purchases where id=$1',[p.id]),other);
    assert.equal(await value('select created_by from public.purchase_payments where id=$1',[p.payment_id]),coach);
    assert.equal(await as(coach,()=>value('select count(*)::int from public.purchases where id=$1',[p.id])),0);
    assert.equal(await as(coach,()=>value('select count(*)::int from public.purchase_payments where id=$1',[p.payment_id])),0);
    const old=await beforeDay();
    await assert.rejects(buy(coach,other,{purchase:old}),/僅限今日或未來/);
    await assert.rejects(buy(coach,other,{pay:old}),/僅限今日或未來/);
    await db.exec(`update public.profiles set active=false where id='${other}'`);
    await assert.rejects(buy(coach,other),/不存在或未啟用/);
    await db.exec(`update public.profiles set active=true where id='${other}'`);
  });
  console.log(JSON.stringify({database:'isolated PGlite',passed:tests,production:false}));
} catch(error){console.error(error.message, error.code??'', error.where??'', error.detail??'');process.exitCode=1;}
finally { await db.close(); }
