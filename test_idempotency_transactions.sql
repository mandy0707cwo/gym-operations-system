-- 只能放在 BEGIN ... ROLLBACK 中執行，不提交虛構交易。
do $$
declare a uuid; m uuid; cat public.course_catalog%rowtype; key_purchase uuid:=gen_random_uuid();
  key_usage uuid; payload jsonb; payment jsonb; first jsonb; repeated jsonb; u jsonb; again jsonb;
  pid uuid; before_p bigint; before_pay bigint; before_u bigint; seq integer; rejected boolean;
begin
  select id into a from public.profiles where active and role='coach' order by id limit 1;
  select id into m from public.members where active order by id limit 1;
  select * into cat from public.course_catalog where active order by id limit 1;
  if a is null or m is null or cat.id is null then raise exception '缺少回滾驗證前提'; end if;
  select count(*) into before_p from public.purchases;
  select count(*) into before_pay from public.purchase_payments;
  select count(*) into before_u from public.session_usages;
  payload:=jsonb_build_object('member_id',m,'coach_id',a,'course_name',cat.course_name,
    'report_category',cat.report_category,'purchase_kind','first','payment_plan','full','installment_count',1,
    'total_sessions',3,'session_hours',cat.session_hours,'total_amount',2100,
    'purchase_date','2099-01-01','expiry_date','2099-12-31');
  payment:=jsonb_build_object('amount',2100,'paid_date','2099-01-01');
  perform set_config('request.jwt.claim.sub',a::text,true);
  perform set_config('request.jwt.claims',jsonb_build_object('sub',a,'role','authenticated')::text,true);
  execute 'set local role authenticated';
  first:=public.create_purchase_idempotent(key_purchase,payload,payment);
  repeated:=public.create_purchase_idempotent(key_purchase,payload,payment);
  if first is distinct from repeated then raise exception '購課重播結果不同'; end if;
  pid:=(first->>'id')::uuid;
  rejected:=false;
  begin
    perform public.create_purchase_idempotent(key_purchase,jsonb_set(payload,'{total_amount}','2200'),payment);
  exception when others then rejected:=true; end;
  if not rejected then raise exception '同碼內容衝突未拒絕'; end if;
  for seq in 1..3 loop
    key_usage:=gen_random_uuid();
    u:=public.consume_session_idempotent(key_usage,pid,'2099-01-02'::date+seq,a);
    again:=public.consume_session_idempotent(key_usage,pid,'2099-01-02'::date+seq,a);
    if u is distinct from again or (u->>'session_seq')::integer<>seq then
      raise exception '銷課重送重複扣堂或未回原結果';
    end if;
  end loop;
  if public.operation_status(key_purchase,'purchase')->>'state'<>'completed' then raise exception '成功收據未保存'; end if;
  if public.cancel_operation(key_purchase,'purchase')->>'state'<>'completed' then raise exception '取消不應刪除已成功交易'; end if;
  key_purchase:=gen_random_uuid();
  if public.cancel_operation(key_purchase,'purchase')->>'state'<>'cancelled' then raise exception '取消墓碑未保存'; end if;
  rejected:=false;
  begin perform public.create_purchase_idempotent(key_purchase,payload,payment);
  exception when others then rejected:=true; end;
  if not rejected then raise exception '已取消操作仍被執行'; end if;
  execute 'reset role';
  if (select count(*) from public.purchases)<>before_p+1 or
    (select count(*) from public.purchase_payments)<>before_pay+1 or
    (select count(*) from public.session_usages)<>before_u+3 then raise exception '操作筆數不符'; end if;
  if (select sum(deducted_net_amount) from public.session_usages where purchase_id=pid)<>2000
    or (select sum(net_amount) from public.purchase_payments where purchase_id=pid)<>2000 then
    raise exception '操作與正式計算中心不一致'; end if;
  if has_table_privilege('authenticated','operation_private.requests','SELECT')
    or has_table_privilege('authenticated','operation_private.requests','INSERT')
    or has_function_privilege('anon','public.create_purchase_idempotent(uuid,jsonb,jsonb)','EXECUTE') then
    raise exception '操作收據權限過寬'; end if;
end $$;
select 'PASS: purchase and usage replay, mismatch, cancellation, finance and privileges; transaction will roll back' as verification;
