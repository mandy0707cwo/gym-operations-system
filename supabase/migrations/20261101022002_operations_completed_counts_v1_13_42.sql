-- 只新增受控統計介面，不變更交易、既有RLS或原始中止表的讀取權限。
begin;

create schema if not exists operations_private;
revoke all on schema operations_private from public, anon, authenticated;
grant usage on schema operations_private to authenticated;

create or replace function operations_private.completed_counts(p_start date, p_end date)
returns table(completed_date date, completed_courses bigint)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  -- 不使用既有is_manager()，因該函式也包含共用教練。
  if auth.uid() is null or not exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.active and p.role in ('manager', 'admin')
  ) then
    raise exception '營運統計僅限有效主管與系統管理員' using errcode = '42501';
  end if;
  if p_start is null or p_end is null or p_start > p_end then
    raise exception '請提供有效的統計日期區間' using errcode = '22023';
  end if;

  -- 與原唯讀計算相同：資料不完整時拒絕，不回傳看似完整的部分合計。
  if exists (
    select 1 from public.session_usages u
    left join public.purchases p on p.id = u.purchase_id
    where u.usage_date <= p_end and p.id is null
  ) or exists (
    select 1 from public.session_usages u
    join public.purchases p on p.id = u.purchase_id
    where u.usage_date <= p_end
    group by p.id, p.total_sessions
    having p.total_sessions is null or p.total_sessions <= 0 or count(*) > p.total_sessions
  ) then
    raise exception '銷課與購課資料不一致，請管理員查核' using errcode = '22000';
  end if;
  if exists (
    select 1 from public.course_terminations t
    where t.termination_date <= p_end and t.reversed_at is not null
      and (t.reversed_at at time zone 'Asia/Taipei')::date < t.termination_date
  ) then
    raise exception '中止撤銷日期不一致，請管理員查核' using errcode = '22000';
  end if;

  return query
    with completed as (
      select u.purchase_id, max(u.usage_date) as finished
      from public.session_usages u
      join public.purchases p on p.id = u.purchase_id
      where u.usage_date <= p_end and p.purchase_date <= p_end
      group by u.purchase_id, p.total_sessions
      having p.total_sessions > 0 and count(*) = p.total_sessions
    )
    select c.finished, count(*)::bigint
    from completed c
    where c.finished between p_start and p_end
      and not exists (
        select 1 from public.course_terminations t
        where t.purchase_id = c.purchase_id
          and t.termination_date <= c.finished
          and (t.reversed_at is null or (t.reversed_at at time zone 'Asia/Taipei')::date > c.finished)
      )
    group by c.finished
    order by c.finished;
end;
$function$;

revoke all on function operations_private.completed_counts(date,date) from public, anon, authenticated;
grant execute on function operations_private.completed_counts(date,date) to authenticated;

create or replace function public.operations_completed_counts(p_start date, p_end date)
returns table(completed_date date, completed_courses bigint)
language sql
stable
security invoker
set search_path = ''
as $function$
  select c.completed_date, c.completed_courses
  from operations_private.completed_counts(p_start, p_end) c;
$function$;

revoke all on function public.operations_completed_counts(date,date) from public, anon, authenticated;
grant execute on function public.operations_completed_counts(date,date) to authenticated;
comment on function public.operations_completed_counts(date,date) is
  'v1.13.42：僅有效主管與管理員；只回傳每日自然完成課程數，不含會員、課程ID、中止原因、退款或其他交易明細。';

notify pgrst, 'reload schema';
commit;
