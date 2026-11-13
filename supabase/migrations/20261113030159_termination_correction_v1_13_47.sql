-- 僅新增結構與受控操作；不回寫既有業務資料。
begin;
set local lock_timeout='10s';
set local statement_timeout='45s';

alter table public.course_terminations
  add column corrects_termination_id uuid unique references public.course_terminations(id),
  add column correction_posted_on date,
  add constraint termination_correction_dates check (
    (corrects_termination_id is null and correction_posted_on is null) or
    (corrects_termination_id is not null and correction_posted_on is not null
      and corrects_termination_id<>id and isfinite(correction_posted_on) and correction_posted_on>=termination_date));

create table termination_private.correction_receipts (
  actor_id uuid not null,
  operation_id uuid not null,
  original_id uuid not null unique references public.course_terminations(id),
  replacement_id uuid not null unique references public.course_terminations(id),
  posted_on date not null,
  request jsonb not null,
  result jsonb not null,
  primary key(actor_id,operation_id)
);
alter table termination_private.correction_receipts enable row level security;
revoke all on termination_private.correction_receipts from public,anon,authenticated,service_role;

-- 只接受受控交易先寫入的收據；保護新舊關聯，不變更既有表的角色權限。
create function termination_private.guard_correction_link() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  if tg_op='UPDATE' then
    if old.corrects_termination_id is not null then
      if new.corrects_termination_id is distinct from old.corrects_termination_id
        or new.correction_posted_on is distinct from old.correction_posted_on
        or new.purchase_id is distinct from old.purchase_id
        or new.termination_date is distinct from old.termination_date then
        raise exception '更正關聯及日期不可改寫，請另留更正紀錄';
      end if;
      return new;
    end if;
  end if;
  if new.corrects_termination_id is not null and not exists (
    select 1 from termination_private.correction_receipts c
    join public.course_termination_reversals r on r.termination_id=c.original_id
    where c.original_id=new.corrects_termination_id and c.replacement_id=new.id
      and c.posted_on=new.correction_posted_on and r.reversal_date=c.posted_on
      and r.purchase_id=new.purchase_id and r.created_by=c.actor_id
  ) then
    raise exception '更正關聯只能由完整更正交易建立';
  end if;
  return new;
end $$;
revoke all on function termination_private.guard_correction_link() from public,anon,authenticated,service_role;
create trigger guard_termination_correction before insert or update on public.course_terminations
for each row execute function termination_private.guard_correction_link();

create function termination_private.correct_course(
  p_operation_id uuid,p_termination_id uuid,p_termination_date date,p_termination_type text,
  p_charge_fee boolean,p_completion_bonus_eligible boolean,p_completion_bonus_coach_id uuid,
  p_reason text,p_note text,p_settlement_confirmed boolean,p_reports_confirmed boolean,
  p_expected_remaining_net numeric,p_expected_fee_net numeric,p_expected_refund_net numeric
) returns jsonb language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare
  a uuid:=auth.uid(); old_term public.course_terminations%rowtype;
  new_term public.course_terminations%rowtype;
  request_data jsonb; receipt termination_private.correction_receipts%rowtype;
  reverse_result jsonb; answer jsonb; posted date;
  today date:=(clock_timestamp() at time zone 'Asia/Taipei')::date;
  reason_value text:=btrim(coalesce(p_reason,''));
begin
  if a is null or not exists(select 1 from public.profiles where id=a and active and role='admin') then
    raise exception using errcode='42501',message='僅有效系統管理員可更正中止';
  end if;
  if p_operation_id is null or p_termination_id is null or p_settlement_confirmed is distinct from true or p_reports_confirmed is distinct from true
    or length(reason_value) not between 1 and 1000 or length(coalesce(p_note,''))>1000
    or p_termination_date is null or not isfinite(p_termination_date) or p_termination_date>today
    or p_termination_type is null or p_termination_type not in ('expired','refund')
    or p_charge_fee is null or p_completion_bonus_eligible is null
    or p_expected_remaining_net is null or p_expected_fee_net is null or p_expected_refund_net is null then
    raise exception '更正日期、類型、原因、款項確認或未稅金額不完整';
  end if;
  if (p_termination_type='expired' and p_charge_fee) or
     (p_termination_type='refund' and p_completion_bonus_eligible) or
     (p_completion_bonus_eligible is distinct from (p_completion_bonus_coach_id is not null)) then
    raise exception '更正類型與手續費或獎金設定不符';
  end if;
  request_data:=jsonb_build_object('original',p_termination_id,'date',p_termination_date,'kind',p_termination_type,
    'fee',p_charge_fee,'bonus',p_completion_bonus_eligible,'coach',p_completion_bonus_coach_id,
    'reason',reason_value,'note',nullif(btrim(p_note),''),'settlement_confirmed',true,'reports_confirmed',true,'remaining_net',p_expected_remaining_net,
    'fee_net',p_expected_fee_net,'refund_net',p_expected_refund_net);
  -- 與單獨撤銷用同一操作鎖；再由既有撤銷鎖住購課及中止列。
  perform pg_advisory_xact_lock(hashtextextended(a::text||':'||p_operation_id::text,37));
  select * into receipt from termination_private.correction_receipts where actor_id=a and operation_id=p_operation_id;
  if found then
    if receipt.request is distinct from request_data then raise exception '操作識別碼已使用，但更正內容不同'; end if;
    return receipt.result;
  end if;
  if exists(select 1 from public.course_termination_reversals where created_by=a and operation_id=p_operation_id) then
    raise exception '操作識別碼已用於其他撤銷';
  end if;
  select * into old_term from public.course_terminations where id=p_termination_id;
  if not found then raise exception '找不到原中止紀錄'; end if;
  if p_completion_bonus_eligible and not exists(select 1 from public.profiles where id=p_completion_bonus_coach_id and role='coach' and active) then
    raise exception '結單獎金教練不存在或已停用';
  end if;
  reverse_result:=termination_private.reverse_course(p_operation_id,p_termination_id,reason_value,true);
  posted:=(reverse_result->>'reversal_date')::date;
  new_term:=public.terminate_course(old_term.purchase_id,p_termination_date,p_termination_type,p_charge_fee,
    p_completion_bonus_eligible,p_completion_bonus_coach_id,reason_value,nullif(btrim(p_note),''));
  -- 讀回財務派生觸發器保存的數字；變動即整筆失敗，不會留下單獨撤銷。
  select * into strict new_term from public.course_terminations where id=new_term.id;
  if new_term.remaining_net_amount is distinct from p_expected_remaining_net
    or new_term.fee_net_amount is distinct from p_expected_fee_net
    or new_term.refund_net_amount is distinct from p_expected_refund_net then
    raise exception '未稅金額與確認畫面不符，更正未儲存；請重新核對';
  end if;
  answer:=jsonb_build_object('id',new_term.id,'termination_id',p_termination_id,'purchase_id',new_term.purchase_id,
    'reversal_id',reverse_result->>'id','posted_on',posted);
  insert into termination_private.correction_receipts values(a,p_operation_id,p_termination_id,new_term.id,posted,request_data,answer);
  update public.course_terminations set corrects_termination_id=p_termination_id,
    correction_posted_on=posted,created_at=clock_timestamp() where id=new_term.id;
  return answer;
end $$;
revoke all on function termination_private.correct_course(uuid,uuid,date,text,boolean,boolean,uuid,text,text,boolean,boolean,numeric,numeric,numeric)
  from public,anon,authenticated,service_role;
grant execute on function termination_private.correct_course(uuid,uuid,date,text,boolean,boolean,uuid,text,text,boolean,boolean,numeric,numeric,numeric) to authenticated;

create function public.correct_course_termination(
  p_operation_id uuid,p_termination_id uuid,p_termination_date date,p_termination_type text,
  p_charge_fee boolean,p_completion_bonus_eligible boolean,p_completion_bonus_coach_id uuid,
  p_reason text,p_note text,p_settlement_confirmed boolean,p_reports_confirmed boolean,
  p_expected_remaining_net numeric,p_expected_fee_net numeric,p_expected_refund_net numeric
) returns jsonb language sql security invoker set search_path='' as $$
  select termination_private.correct_course(p_operation_id,p_termination_id,p_termination_date,p_termination_type,
    p_charge_fee,p_completion_bonus_eligible,p_completion_bonus_coach_id,p_reason,p_note,p_settlement_confirmed,p_reports_confirmed,
    p_expected_remaining_net,p_expected_fee_net,p_expected_refund_net);
$$;
revoke all on function public.correct_course_termination(uuid,uuid,date,text,boolean,boolean,uuid,text,text,boolean,boolean,numeric,numeric,numeric)
  from public,anon,authenticated,service_role;
grant execute on function public.correct_course_termination(uuid,uuid,date,text,boolean,boolean,uuid,text,text,boolean,boolean,numeric,numeric,numeric) to authenticated;

-- 正數更正與負數沖回同列更正日；保留舊報表欄位與原業務日期供規則查找。
create or replace view public.course_termination_events with (security_invoker=true) as
 select t.id,t.purchase_id,coalesce(t.correction_posted_on,t.termination_date) as termination_date,t.termination_type,t.remaining_sessions,t.remaining_amount,
 t.charge_fee,t.fee_rate,t.fee_amount,t.refund_amount,t.recognized_amount,t.completion_bonus_eligible,
 t.completion_bonus_coach_id,t.reason,t.note,t.created_at,t.created_by,t.remaining_net_amount,
 t.recognized_net_amount,t.fee_net_amount,t.refund_net_amount,t.calculation_rule_version,
 false as is_reversal,t.termination_date as original_termination_date,t.id as original_termination_id,
 r.original_purchase as purchase_snapshot,r.bonus_rule_snapshot,(r.id is not null) as snapshot_available
 from public.course_terminations t left join public.course_termination_reversals r on r.termination_id=t.id
 union all
 select r.id,t.purchase_id,r.reversal_date,t.termination_type,-t.remaining_sessions,-t.remaining_amount,
 t.charge_fee,t.fee_rate,-t.fee_amount,-t.refund_amount,-t.recognized_amount,t.completion_bonus_eligible,
 t.completion_bonus_coach_id,r.reason,t.note,r.created_at,r.created_by,-t.remaining_net_amount,
 -t.recognized_net_amount,-t.fee_net_amount,-t.refund_net_amount,t.calculation_rule_version,
 true,t.termination_date,t.id,r.original_purchase,r.bonus_rule_snapshot,true
 from public.course_termination_reversals r join public.course_terminations t on t.id=r.termination_id;

-- 僅放寬原子購課函式的教練歸屬比對，保留日期、有效教練、原始登錄人及原本的讀寫 RLS。
do $upgrade$
declare target regprocedure:='public.create_purchase_with_first_payment(jsonb,jsonb)'::regprocedure;
  definition text; old_part text:=$body$if v_role='coach' and (v_coach_id<>v_actor
     or v_purchase_date<$body$;
begin
  definition:=pg_get_functiondef(target);
  if md5(definition)<>'d74801f371d2331462bc8b341cb2050f' or strpos(definition,old_part)=0 then
    raise exception '購課函式基準版本不同，不套用權限更動';
  end if;
  execute replace(replace(definition,old_part,'if v_role=''coach'' and (v_purchase_date<'),
    '教練僅可建立自己的購課及今日或未來的付款','教練的購課與付款日期僅限今日或未來');
end $upgrade$;

-- 營運完成數與歷史餘額使用相同的更正生效日；不改查詢角色或回傳欄位。
do $upgrade$
declare definition text:=pg_get_functiondef('operations_private.completed_counts(date,date)'::regprocedure);
  old_part text:='t.termination_date <= c.finished';
begin
  if strpos(definition,old_part)=0 then raise exception '完成課程彙總函式版本不同'; end if;
  execute replace(definition,old_part,'coalesce(t.correction_posted_on,t.termination_date) <= c.finished');
end $upgrade$;

notify pgrst,'reload schema';
commit;
