-- v1.13.21：只攔截一般教練新增銷課；不改舊紀錄、收款、財務換算或其他角色權限。
-- 必須先在隔離測試庫驗證；正式升級前先備份，之後再部署配套畫面。
create or replace function finance_private.enforce_usage_funds_v1()
returns trigger language plpgsql security definer set search_path='' set lock_timeout='10s' as $$
declare
  actor_id uuid:=auth.uid(); actor_role text;
  p public.purchases%rowtype; received numeric; used numeric; used_count integer;
  expected numeric; available numeric;
begin
  -- 無 JWT 的受信任維護連線維持現況；一般登入者必須有有效 profile。
  if actor_id is null then
    if session_user in ('postgres','supabase_admin')
       or coalesce(current_setting('role',true),'')='service_role' then return new; end if;
    raise exception using errcode='42501',message='未授權銷課';
  end if;
  select role::text into actor_role from public.profiles where id=actor_id and active;
  if actor_role is null then
    raise exception using errcode='42501',message='帳號已停用或不存在';
  end if;
  if actor_role<>'coach' then return new; end if;

  -- 與原 consume_session 鎖同一購課，兩個不同識別碼也不能同時超扣實收款。
  select * into p from public.purchases where id=new.purchase_id for update;
  if not found or p.coach_id<>actor_id or new.coach_id<>actor_id or new.created_by<>actor_id then
    raise exception using errcode='42501',message='無權替此購課或教練建立銷課';
  end if;
  if p.status<>'active' then raise exception '此課程不是有效狀態'; end if;
  select count(*),coalesce(sum(deducted_amount),0) into used_count,used
    from public.session_usages where purchase_id=new.purchase_id;
  if used_count>=p.total_sessions then raise exception '剩餘堂數不足'; end if;
  expected:=case when used_count+1=p.total_sessions then round(p.total_amount-used,2)
                 else round(p.total_amount/p.total_sessions,2) end;
  -- 直接 INSERT 不能以較小金額繞過實收額檢查；沿用既有含稅逐堂及尾差規則。
  if expected<0 or new.deducted_amount is distinct from expected then
    raise exception '本次銷課金額不符課程分攤規則，請重新載入';
  end if;
  select coalesce(sum(amount),0) into received from public.purchase_payments
    where purchase_id=new.purchase_id;
  available:=received-used;
  if available<expected then
    raise exception using errcode='P0001',
      message=format('實際預收餘額不足：可用(含稅) %s，本次銷課(含稅) %s，差額 %s；請先確認並登錄後續期款',
                     available,expected,expected-available);
  end if;
  return new;
end $$;
revoke all on function finance_private.enforce_usage_funds_v1() from public,anon,authenticated,service_role;
drop trigger if exists usage_funds_guard_v1 on public.session_usages;
create trigger usage_funds_guard_v1 before insert on public.session_usages
for each row execute function finance_private.enforce_usage_funds_v1();
comment on function finance_private.enforce_usage_funds_v1() is
 'v1.13.21: coach INSERT requires recorded gross receipts minus all recorded gross usages >= current gross usage. No date cutoff; other roles unchanged.';
