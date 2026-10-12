// 僅隔離記憶體資料庫與虛構資料；不連接正式 Supabase。
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const runtime=process.env.PGLITE_RUNTIME || path.join(root,"output/qa_atomic_runtime/node_modules/@electric-sql/pglite/dist/index.js");
const {PGlite}=await import(pathToFileURL(runtime).href);
const db=new PGlite();
const source=fs.readFileSync(path.join(root,"database.sql"),"utf8");
const migration=fs.readFileSync(path.join(root,"migration_atomic_purchase_v1_13_6.sql"),"utf8");
const codeMigration=fs.readFileSync(path.join(root,"migration_purchase_code_v1_13_8.sql"),"utf8");
const ids={admin:"00000000-0000-0000-0000-000000000001",coach:"00000000-0000-0000-0000-000000000002",
 other:"00000000-0000-0000-0000-000000000003",manager:"00000000-0000-0000-0000-000000000004",
 shared:"00000000-0000-0000-0000-000000000005",inactive:"00000000-0000-0000-0000-000000000006",
 member:"00000000-0000-0000-0000-000000000010",inactiveMember:"00000000-0000-0000-0000-000000000011"};
const tableDDL=name=>source.match(new RegExp("create table public\\."+name+" \\([\\s\\S]+?\\n\\);"))?.[0]
 ?? (()=>{throw Error("Missing table "+name)})();
const functionDDL=name=>source.match(new RegExp("create or replace function public\\."+name+"\\(\\)[\\s\\S]+?\\$\\$;"))?.[0]
 ?? (()=>{throw Error("Missing function "+name)})();
let checks=0;
const check=async(name,fn)=>{await fn();checks++;console.log("PASS "+name);};
async function counts(){
 await db.exec("reset role;");
 return (await db.query("select (select count(*)::int from public.purchases) as purchases,(select count(*)::int from public.purchase_payments) as payments")).rows[0];
}
async function call(purchase={},payment={},actor=ids.admin,dbRole="authenticated"){
 await db.exec("reset role;");
 await db.query("select set_config('request.jwt.claim.sub',$1,false)",[actor || ""]);
 await db.exec("set role "+dbRole+";");
 const today=(await db.query("select to_char((current_timestamp at time zone 'Asia/Taipei')::date,'YYYY-MM-DD') as day")).rows[0].day;
 const p={member_id:ids.member,purchase_kind:"first",coach_id:ids.coach,course_name:"測試課程",
  report_category:"測試分類",total_sessions:10,session_hours:1,total_amount:10500,purchase_date:today,
  expiry_date:"2099-12-31",payment_plan:"installment",installment_count:3,referral:"虛構轉介",note:"虛構備註",...purchase};
 const pay={amount:1050,paid_date:today,...payment};
 const data=(await db.query("select public.create_purchase_with_first_payment($1::jsonb,$2::jsonb) as data",
  [JSON.stringify(p),JSON.stringify(pay)])).rows[0].data;
 await db.exec("reset role;");
 return data;
}
async function rejected(name,p={},pay={},actor=ids.admin,role="authenticated",message){
 await check(name,async()=>{
  const before=await counts();
  const beforeLedger=(await db.query("select jsonb_agg(to_jsonb(c) order by code_date) as data from purchase_identity.daily_counters c")).rows[0].data;
  await assert.rejects(call(p,pay,actor,role),message ? new RegExp(message) : undefined);
  assert.deepEqual(await counts(),before,"失敗不得留下購課或首期付款");
  const afterLedger=(await db.query("select jsonb_agg(to_jsonb(c) order by code_date) as data from purchase_identity.daily_counters c")).rows[0].data;
  assert.deepEqual(afterLedger,beforeLedger,"失敗不得留下配號計數");
 });
}
try{
 await db.exec("create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls; create schema auth; create table auth.users(id uuid primary key);");
 await db.exec("create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;");
 const types=[...source.matchAll(/create type public\.(?:app_role|purchase_kind|payment_plan) as enum [^;]+;/g)].map(x=>x[0]).join("\n");
 await db.exec(types+"\n"+["profiles","members","course_catalog","purchases","purchase_payments"].map(tableDDL).join("\n"));
 await db.exec("alter table public.course_catalog add column active boolean not null default true;");
 await db.exec(functionDDL("is_manager"));
 await db.exec(functionDDL("validate_purchase_payment"));
 await db.exec("create trigger check_purchase_payment before insert or update on public.purchase_payments for each row execute function public.validate_purchase_payment();");
 for(const name of ["profiles","members","course_catalog","purchases","purchase_payments"])
  await db.exec("alter table public."+name+" enable row level security;");
 for(const policy of ["profiles_read","members_read","course_catalog_read","purchase_read","purchase_insert","purchase_update","payment_read","payment_insert"]){
  const sql=source.match(new RegExp("create policy "+policy+" [\\s\\S]+?;"))?.[0];
  assert.ok(sql,policy);await db.exec(sql);
 }
 await db.exec("grant usage on schema public,auth to authenticated,anon; grant execute on function auth.uid() to authenticated,anon; grant select on public.profiles,public.members,public.course_catalog,public.purchases,public.purchase_payments to authenticated; grant insert on public.purchases,public.purchase_payments to authenticated; grant update on public.purchases to authenticated;");
 for(const [key,role] of [["admin","admin"],["coach","coach"],["other","coach"],["manager","manager"],["shared","shared_coach"],["inactive","coach"]]){
  await db.query("insert into auth.users values($1)",[ids[key]]);
  await db.query("insert into public.profiles(id,display_name,role,active) values($1,$2,$3,$4)",[ids[key],"虛構"+key,role,key!=="inactive"]);
 }
 await db.query("insert into public.members(id,member_name,created_by,active) values($1,'虛構客戶',$2,true),($3,'停用虛構客戶',$2,false)",[ids.member,ids.admin,ids.inactiveMember]);
 await db.exec("insert into public.course_catalog(course_name,report_category,session_hours,active) values('測試課程','測試分類',1,true),('停用課程','測試分類',1,false);");
 await check("migration installs and safely reruns",async()=>{await db.exec(migration);await db.exec(migration);});
 // 先放入歷史虛構購課，驗證回填排序及所有原欄位不變。
 async function insertHistorical(actor,date,stamp,creator=ids.admin) {
  return (await db.query("insert into public.purchases(member_id,purchase_kind,coach_id,course_name,total_sessions,total_amount,purchase_date,expiry_date,payment_plan,installment_count,created_by,created_at) values($1,'first',$2,'測試課程',10,10500,$3,'2099-12-31','installment',3,$4,$5) returning id",[ids.member,actor,date,creator,stamp])).rows[0].id;
 }
 const first=await insertHistorical(ids.other,"2026-10-08","2026-10-08T08:10:00Z");
 const second=await insertHistorical(ids.coach,"2026-10-08","2026-10-08T09:33:00Z");
 const snapshot=(await db.query("select jsonb_agg(to_jsonb(p) order by id) as data from public.purchases p")).rows[0].data;
 await check("historical backfill preserves all original fields",async()=>{
  await db.exec(codeMigration);
  const after=(await db.query("select jsonb_agg(to_jsonb(p)-'purchase_code' order by id) as data from public.purchases p")).rows[0].data;
  assert.deepEqual(after,snapshot);
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[second])).rows[0].purchase_code,"20261008-002");
 });
 await check("code migration safely reruns without resequencing",async()=>{await db.exec(codeMigration);});
 await check("coach RLS sees its permanent global 002, not 001",async()=>{
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[ids.coach]);await db.exec("set role authenticated;");
  const rows=(await db.query("select id,purchase_code from public.purchases")).rows;
  assert.equal(rows.length,1);assert.equal(rows[0].id,second);assert.equal(rows[0].purchase_code,"20261008-002");
  await db.exec("reset role;");
 });
 await check("date and coach edits preserve permanent code",async()=>{
  await db.query("update public.purchases set purchase_date='2026-10-09',coach_id=$1 where id=$2",[ids.other,second]);
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[second])).rows[0].purchase_code,"20261008-002");
 });
 await check("code edit is rejected even for privileged migration owner",async()=>{
  await assert.rejects(db.query("update public.purchases set purchase_code='20261008-099' where id=$1",[second]),/不可修改/);
 });
 await check("UUID edit is rejected",async()=>{
  await assert.rejects(db.query("update public.purchases set id=gen_random_uuid() where id=$1",[second]),/不可修改/);
 });
 await check("deletion never releases an issued code",async()=>{
  await db.query("delete from public.purchases where id=$1",[first]);
  const inserted=await insertHistorical(ids.coach,"2026-10-08","2026-10-08T07:00:00Z");
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[inserted])).rows[0].purchase_code,"20261008-003");
  assert.equal((await db.query("select count(*)::int as n from purchase_identity.issued_codes where purchase_id=$1",[first])).rows[0].n,1);
 });
 await check("client supplied code rejected",async()=>{
  await assert.rejects(db.query("insert into public.purchases(member_id,purchase_kind,coach_id,course_name,total_sessions,total_amount,purchase_date,expiry_date,payment_plan,installment_count,created_by,purchase_code) values($1,'first',$2,'測試課程',10,10500,'2026-10-08','2099-12-31','installment',3,$3,'20261008-004')",[ids.member,ids.coach,ids.admin]),/不可自行指定/);
 });
 await check("private counter and function are not exposed to client roles",async()=>{
  for(const role of ["anon","authenticated","service_role"]){
   const p=(await db.query("select has_schema_privilege($1,'purchase_identity','usage') as schema_ok,has_table_privilege($1,'purchase_identity.daily_counters','update') as update_ok,has_function_privilege($1,'purchase_identity.assign_purchase_code()','execute') as execute_ok",[role])).rows[0];
   assert.deepEqual(p,{schema_ok:false,update_ok:false,execute_ok:false});
  }
  const f=(await db.query("select prosecdef,proconfig from pg_proc where oid='purchase_identity.assign_purchase_code()'::regprocedure")).rows[0];
  assert.equal(f.prosecdef,true);assert.ok(f.proconfig.includes('search_path=""'));
 });
 await check("queued same-date inserts produce 20 distinct permanent codes (not multi-session simulation)",async()=>{
  const inserted=await Promise.all(Array.from({length:20},()=>insertHistorical(ids.coach,"2026-01-01","2026-10-01T00:00:00Z")));
  const rows=(await db.query("select purchase_code from public.purchases where id=any($1::uuid[]) order by purchase_code",[inserted])).rows;
  assert.equal(rows.length,20);assert.equal(new Set(rows.map(x=>x.purchase_code)).size,20);
  assert.equal(rows[0].purchase_code,"20260101-001");assert.equal(rows[19].purchase_code,"20260101-020");
 });
 await check("counter sequences over 999 are not truncated",async()=>{
  await db.exec("insert into purchase_identity.daily_counters values('2025-01-01',999);");
  const id=await insertHistorical(ids.coach,"2025-01-01","2026-10-01T00:00:00Z");
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[id])).rows[0].purchase_code,"20250101-1000");
 });
 await check("authenticated direct insert runs trigger without direct execute privilege",async()=>{
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[ids.coach]);await db.exec("set role authenticated;");
  const id=await insertHistorical(ids.coach,"2026-10-08","2026-10-08T10:00:00Z",ids.coach).catch(async error=>{await db.exec("reset role;");throw error;});
  await db.exec("reset role;");
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[id])).rows[0].purchase_code,"20261008-004");
 });
 await check("RLS failure rolls back the code reservation",async()=>{
  const before=(await db.query("select last_sequence from purchase_identity.daily_counters where code_date='2026-10-08'")).rows[0].last_sequence;
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[ids.coach]);await db.exec("set role authenticated;");
  await assert.rejects(insertHistorical(ids.other,"2026-10-08","2026-10-08T10:00:00Z",ids.coach),/row-level security/);
  await db.exec("reset role;");
  assert.equal((await db.query("select last_sequence from purchase_identity.daily_counters where code_date='2026-10-08'")).rows[0].last_sequence,before);
 });
 await check("server import requires an active admin creator",async()=>{
  await db.exec("grant usage on schema public to service_role;grant select,insert on public.purchases to service_role;set role service_role;");
  const id=await insertHistorical(ids.coach,"2026-10-08","2026-10-08T10:00:00Z",ids.admin);
  await assert.rejects(insertHistorical(ids.coach,"2026-10-08","2026-10-08T10:00:00Z",ids.coach),/有效系統管理員/);
  await db.exec("reset role;");
  assert.equal((await db.query("select purchase_code from public.purchases where id=$1",[id])).rows[0].purchase_code,"20261008-005");
 });

 await check("invoker, fixed search path, authenticated-only grant",async()=>{
  const r=(await db.query("select prosecdef,proconfig,has_function_privilege('anon',oid,'execute') as anon_ok,has_function_privilege('authenticated',oid,'execute') as auth_ok from pg_proc where oid='public.create_purchase_with_first_payment(jsonb,jsonb)'::regprocedure")).rows[0];
  assert.equal(r.prosecdef,false);assert.equal(r.anon_ok,false);assert.equal(r.auth_ok,true);
  assert.ok(r.proconfig.some(x=>x==='search_path=""'));
 });
 for(const actor of [ids.admin,ids.coach,ids.manager,ids.shared])
  await check("successful installment pair with permanent code "+actor.slice(-1),async()=>{
   const before=await counts();const result=await call({}, {},actor);const after=await counts();
   assert.equal(after.purchases,before.purchases+1);assert.equal(after.payments,before.payments+1);
   assert.equal(result.id,result.purchase_id);assert.ok(result.payment_id);
   const record=(await db.query("select p.created_by,p.installment_count,pp.purchase_id,pp.created_by as payment_creator,pp.installment_no,pp.amount,pp.payment_kind from public.purchases p join public.purchase_payments pp on p.id=pp.purchase_id where p.id=$1",[result.id])).rows[0];
   assert.equal(record.created_by,actor);assert.equal(record.payment_creator,actor);assert.equal(record.installment_no,1);
   assert.equal(record.installment_count,3);assert.equal(Number(record.amount),1050);assert.equal(record.payment_kind,"installment");
  });
 await check("full payment stores complete pair",async()=>{
  const r=await call({payment_plan:"full",installment_count:1},{amount:10500});
  assert.equal(Number((await db.query("select amount from public.purchase_payments where id=$1",[r.payment_id])).rows[0].amount),10500);
 });
 // 注入測試專用的付款 BEFORE INSERT 例外，確認第一筆也回滾。
 await db.exec("create function public.qa_reject_payment() returns trigger language plpgsql as $$begin raise exception '模擬付款拒絕'; end;$$; create trigger qa_reject_payment before insert on public.purchase_payments for each row execute function public.qa_reject_payment();");
 await rejected("payment trigger rollback leaves neither row",{}, {},ids.admin,"authenticated","模擬付款拒絕");
 await db.exec("drop trigger qa_reject_payment on public.purchase_payments; drop function public.qa_reject_payment();");
 await db.exec("create policy qa_payment_deny on public.purchase_payments as restrictive for insert to authenticated with check(false);");
 await rejected("payment RLS denies after purchase insert",{}, {},ids.admin,"authenticated","row-level security");
 await db.exec("drop policy qa_payment_deny on public.purchase_payments;");
 await rejected("purchase constraint rejection",{total_sessions:-1});
 await rejected("overpayment rejection",{}, {amount:10501});
 await rejected("full must be paid in full",{payment_plan:"full",installment_count:1},{amount:1000});
 await rejected("invalid installment count",{installment_count:4});
 await rejected("blank payment date",{}, {paid_date:null});
 await rejected("invalid expiry date",{expiry_date:"2000-01-01"});
 await rejected("infinite date rejected",{expiry_date:"infinity"});
 await rejected("non-finite monetary input",{total_amount:"NaN"});
 await rejected("unknown customer",{member_id:"00000000-0000-0000-0000-000000000099"});
 await rejected("inactive customer",{member_id:ids.inactiveMember});
 await rejected("inactive coach",{coach_id:ids.inactive});
 await rejected("inactive course",{course_name:"停用課程"});
 await rejected("catalog hours cannot be forged",{session_hours:2});
 await rejected("report category cannot be forged",{report_category:"偽造"});
 await rejected("creator cannot be forged",{created_by:ids.other});
 await rejected("first installment number cannot be forged",{}, {installment_no:2});
 await rejected("coach cannot assign another coach",{coach_id:ids.other},{},ids.coach);
 await rejected("coach cannot backdate purchase",{purchase_date:"2000-01-01"},{},ids.coach);
 await rejected("coach cannot backdate payment",{}, {paid_date:"2000-01-01"},ids.coach);
 await rejected("inactive caller rejected",{}, {},ids.inactive);
 await rejected("unsigned caller rejected",{}, {},null);
 await rejected("anonymous execute privilege denied",{}, {},null,"anon","permission denied");
 console.log(JSON.stringify({checks,counts:await counts(),engine:(await db.query("select version() as version")).rows[0].version,formalWrites:0}));
}finally{
 await db.close();
}
