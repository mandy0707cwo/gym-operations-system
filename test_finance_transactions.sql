-- 必須與 schema migration 放在 BEGIN ... ROLLBACK 交易內；不留下測試交易。
do $$
declare actor uuid; coach uuid; member uuid; cat public.course_catalog%rowtype;
  response jsonb; pid uuid; payid uuid; row_term public.course_terminations%rowtype;
  initial_purchases bigint; initial_usages bigint; initial_payments bigint; failed boolean;
begin
  select id into actor from public.profiles where role='admin' and active limit 1;
  select id into coach from public.profiles where role='coach' and active limit 1;
  select id into member from public.members where active limit 1;
  select * into cat from public.course_catalog where active limit 1;
  if actor is null or coach is null or member is null or cat.id is null then raise exception '缺少交易測試前提'; end if;
  perform set_config('request.jwt.claim.sub',actor::text,true);
  perform set_config('request.jwt.claims',jsonb_build_object('sub',actor,'role','authenticated')::text,true);
  select count(*) into initial_purchases from public.purchases;
  select count(*) into initial_usages from public.session_usages;
  select count(*) into initial_payments from public.purchase_payments;
  response:=public.create_purchase_with_first_payment(jsonb_build_object(
    'member_id',member,'coach_id',coach,'course_name',cat.course_name,'report_category',cat.report_category,
    'purchase_kind','first','payment_plan','installment','installment_count',3,
    'total_sessions',3,'session_hours',cat.session_hours,'total_amount',2100,
    'purchase_date','2099-01-01','expiry_date','2099-12-31'),
    jsonb_build_object('amount',700,'paid_date','2099-01-01'));
  pid:=(response->>'purchase_id')::uuid;
  insert into public.purchase_payments(purchase_id,installment_no,amount,paid_date,created_by)
    values(pid,2,700,'2099-01-02',actor),(pid,3,700,'2099-01-03',actor);
  if (select sum(net_amount) from public.purchase_payments where purchase_id=pid)<>2000 then
    raise exception '分期付清未稅合計不符'; end if;
  if (select net_amount from public.purchase_payments where purchase_id=pid and installment_no=3)<>666 then
    raise exception '最後期款未吸收尾差'; end if;
  perform public.consume_session(pid,'2099-01-04',coach);
  perform public.consume_session(pid,'2099-01-05',coach);
  perform public.consume_session(pid,'2099-01-06',coach);
  if (select sum(deducted_net_amount) from public.session_usages where purchase_id=pid)<>2000
    or (select deducted_net_amount from public.session_usages where purchase_id=pid and session_seq=3)<>666 then
    raise exception '銷完課程未稅尾差不符'; end if;
  -- 管理員更正期款後，同課程後期未稅必須一併重分配，不只更新單列。
  select id into payid from public.purchase_payments where purchase_id=pid and installment_no=1;
  perform public.admin_correct_purchase_payment(payid,698,'2099-01-01','隔離交易測試，不會提交');
  if (select sum(net_amount) from public.purchase_payments where purchase_id=pid)<>1999 then
    raise exception '期款更正後未稅未連動'; end if;
  -- 購課與首期任一步失敗，兩者都不留下。
  failed:=false;
  begin
    perform public.create_purchase_with_first_payment(jsonb_build_object(
      'member_id',member,'coach_id',coach,'course_name',cat.course_name,'report_category',cat.report_category,
      'purchase_kind','first','payment_plan','full','installment_count',1,
      'total_sessions',3,'session_hours',cat.session_hours,'total_amount',2100,
      'purchase_date','2099-02-01','expiry_date','2099-12-31'),
      jsonb_build_object('amount',2101,'paid_date','2099-02-01'));
  exception when others then failed:=true; end;
  if not failed or (select count(*) from public.purchases)<>initial_purchases+1
    or (select count(*) from public.purchase_payments)<>initial_payments+3 then
    raise exception '原子購課失敗留下部分資料'; end if;
  response:=public.create_purchase_with_first_payment(jsonb_build_object(
    'member_id',member,'coach_id',coach,'course_name',cat.course_name,'report_category',cat.report_category,
    'purchase_kind','first','payment_plan','full','installment_count',1,
    'total_sessions',3,'session_hours',cat.session_hours,'total_amount',2100,
    'purchase_date','2099-03-01','expiry_date','2099-12-31'),
    jsonb_build_object('amount',2100,'paid_date','2099-03-01'));
  pid:=(response->>'purchase_id')::uuid;
  perform public.consume_session(pid,'2099-03-02',coach);
  perform public.terminate_course(pid,'2099-03-03','refund',true,false,null,'隔離退款測試，不會提交');
  select * into row_term from public.course_terminations where purchase_id=pid;
  if row_term.remaining_net_amount<>1333 or row_term.fee_net_amount<>267 or row_term.refund_net_amount<>1066 then
    raise exception '退款未稅拆分不符'; end if;
  if row_term.remaining_net_amount<>row_term.fee_net_amount+row_term.refund_net_amount then
    raise exception '退款未稅拆分不平衡'; end if;
  if has_schema_privilege('authenticated','finance_private','USAGE')
    or has_table_privilege('authenticated','finance_private.before_rows','SELECT')
    or has_function_privilege('authenticated','finance_private.rebuild_purchase(uuid)','EXECUTE')
    or has_function_privilege('anon','public.finance_net_v1(numeric)','EXECUTE') then
    raise exception '財務內部資料或函式意外開放權限'; end if;
  if not exists(select 1 from finance_private.change_log where row_id=pid) then
    raise exception '缺少交易更正稽核'; end if;
end $$;

-- 伺服器端管理員服務連線保留操作人員來源；非一般使用者可偽造的權限。
do $$
declare actor_id uuid; source_id uuid; audit_actor uuid; audit_basis text;
begin
  select id into actor_id from public.profiles where role='admin' and active limit 1;
  select id into source_id from public.trial_items limit 1;
  perform set_config('request.jwt.claim.sub','',true);
  perform set_config('request.jwt.claims','{"role":"service_role"}',true);
  perform set_config('request.headers',jsonb_build_object('x-finance-actor-id',actor_id)::text,true);
  execute 'set local role service_role';
  update public.trial_items set note=coalesce(note,'')||' [隔離審計測試]' where id=source_id;
  execute 'reset role';
  select actor,actor_basis into audit_actor,audit_basis from finance_private.change_log
    where table_name='trial_items' and row_id=source_id order by id desc limit 1;
  if audit_actor is distinct from actor_id or audit_basis<>'trusted_server_header' then
    raise exception '服務端操作人員未保留'; end if;
end $$;

-- 真正切換 authenticated + 教練身分測試，不以 postgres 的 RLS 繞過作為權限驗收。
do $$
declare coach uuid; member uuid; cat public.course_catalog%rowtype; response jsonb; pid uuid; blocked boolean:=false;
begin
  select id into coach from public.profiles where role='coach' and active limit 1;
  select id into member from public.members where active limit 1;
  select * into cat from public.course_catalog where active limit 1;
  perform set_config('request.jwt.claim.sub',coach::text,true);
  perform set_config('request.jwt.claims',jsonb_build_object('sub',coach,'role','authenticated')::text,true);
  execute 'set local role authenticated';
  response:=public.create_purchase_with_first_payment(jsonb_build_object(
    'member_id',member,'coach_id',coach,'course_name',cat.course_name,'report_category',cat.report_category,
    'purchase_kind','first','payment_plan','full','installment_count',1,
    'total_sessions',3,'session_hours',cat.session_hours,'total_amount',2100,
    'purchase_date','2099-04-01','expiry_date','2099-12-31'),
    jsonb_build_object('amount',2100,'paid_date','2099-04-01'));
  pid:=(response->>'purchase_id')::uuid;
  if (select sum(net_amount) from public.purchase_payments where purchase_id=pid)<>2000 then
    raise exception '教練購課收款未稅保存錯誤'; end if;
  perform public.consume_session(pid,'2099-04-02',coach);
  if (select sum(deducted_net_amount) from public.session_usages where purchase_id=pid)<>667 then
    raise exception '教練正常銷課未稅保存錯誤'; end if;
  begin
    perform public.terminate_course(pid,'2099-04-03','expired');
  exception when others then blocked:=true; end;
  if not blocked then raise exception '教練意外獲得中止權限'; end if;
  execute 'reset role';
end $$;
