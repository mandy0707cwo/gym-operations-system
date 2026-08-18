-- v1.9.1：修正刪除中間銷課堂次後，新增銷課發生 session_seq 唯一鍵衝突。
create or replace function public.consume_session(
  p_purchase_id uuid, p_usage_date date, p_coach_id uuid, p_note text default null
) returns public.session_usages
language plpgsql security invoker set search_path=public as $$
declare
  v_purchase public.purchases%rowtype;
  v_used integer;
  v_next_seq integer;
  v_deducted numeric(12,2);
  v_row public.session_usages%rowtype;
begin
  select * into v_purchase from public.purchases where id=p_purchase_id for update;
  if not found then raise exception '找不到購買紀錄'; end if;
  if v_purchase.status <> 'active' then raise exception '此課程不是有效狀態'; end if;

  select count(*) into v_used from public.session_usages where purchase_id=p_purchase_id;
  if v_used >= v_purchase.total_sessions then raise exception '剩餘堂數不足'; end if;

  select candidate.seq into v_next_seq
  from generate_series(1,v_purchase.total_sessions) as candidate(seq)
  where not exists (
    select 1 from public.session_usages usage
    where usage.purchase_id=p_purchase_id and usage.session_seq=candidate.seq
  )
  order by candidate.seq
  limit 1;
  if v_next_seq is null then raise exception '找不到可用的銷課堂次'; end if;

  if v_used + 1 = v_purchase.total_sessions then
    select round(v_purchase.total_amount-coalesce(sum(deducted_amount),0),2)
      into v_deducted from public.session_usages where purchase_id=p_purchase_id;
  else
    v_deducted := round(v_purchase.total_amount/v_purchase.total_sessions,2);
  end if;

  insert into public.session_usages(purchase_id,usage_date,coach_id,session_seq,deducted_amount,note,created_by)
  values(p_purchase_id,p_usage_date,p_coach_id,v_next_seq,v_deducted,nullif(trim(p_note),''),auth.uid())
  returning * into v_row;

  insert into public.daily_operations(operation_date,coach_id,classes_held,classes_cancelled,trial_visits,trial_conversions)
  values(p_usage_date,p_coach_id,1,0,0,0)
  on conflict(operation_date,coach_id) do update
  set classes_held=(select count(*) from public.session_usages
                    where usage_date=p_usage_date and coach_id=p_coach_id);

  if v_used+1=v_purchase.total_sessions then
    update public.purchases set status='completed' where id=p_purchase_id;
  end if;
  return v_row;
end; $$;

grant execute on function public.consume_session(uuid,date,uuid,text) to authenticated;
