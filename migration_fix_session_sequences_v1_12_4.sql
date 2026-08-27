begin;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.session_usage_seq_corrections (
  batch_version text not null,
  usage_id uuid not null,
  purchase_id uuid not null,
  usage_date date not null,
  old_session_seq integer not null,
  new_session_seq integer not null,
  corrected_at timestamptz not null default now(),
  primary key (batch_version, usage_id)
);

revoke all on private.session_usage_seq_corrections from public, anon, authenticated;

create temporary table seq_fix_v1_12_4 on commit drop as
with ranked as (
  select
    su.id as usage_id,
    su.purchase_id,
    su.usage_date,
    su.session_seq as old_session_seq,
    row_number() over (
      partition by su.purchase_id
      order by su.usage_date, su.created_at, su.id
    )::integer as new_session_seq
  from public.session_usages su
)
select *
from ranked
where old_session_seq is distinct from new_session_seq;

do $$
declare
  affected_rows integer;
  purchases_over_total integer;
begin
  select count(*) into affected_rows from seq_fix_v1_12_4;
  if affected_rows <> 481 then
    raise exception '預期更正481筆，但目前偵測到%筆；為避免誤改，已取消整批更新', affected_rows;
  end if;

  select count(*) into purchases_over_total
  from (
    select p.id
    from public.purchases p
    join public.session_usages su on su.purchase_id=p.id
    group by p.id,p.total_sessions
    having count(*)>p.total_sessions
  ) x;
  if purchases_over_total <> 0 then
    raise exception '偵測到%筆購買課程的銷課數超過購買堂數，已取消整批更新', purchases_over_total;
  end if;
end $$;

insert into private.session_usage_seq_corrections
  (batch_version,usage_id,purchase_id,usage_date,old_session_seq,new_session_seq)
select 'v1.12.4',usage_id,purchase_id,usage_date,old_session_seq,new_session_seq
from seq_fix_v1_12_4
on conflict (batch_version,usage_id) do nothing;

-- 先移至不會與正常堂次重疊的暫存編號，避開唯一限制。
update public.session_usages su
set session_seq=1000000+fix.new_session_seq
from seq_fix_v1_12_4 fix
where su.id=fix.usage_id;

-- 再寫回依日期排序後的正式連續堂次。
update public.session_usages su
set session_seq=fix.new_session_seq
from seq_fix_v1_12_4 fix
where su.id=fix.usage_id;

do $$
declare
  remaining_errors integer;
begin
  with ranked as (
    select
      su.session_seq,
      row_number() over (
        partition by su.purchase_id
        order by su.usage_date, su.created_at, su.id
      )::integer as expected_seq
    from public.session_usages su
  )
  select count(*) into remaining_errors
  from ranked
  where session_seq is distinct from expected_seq;

  if remaining_errors <> 0 then
    raise exception '更新後仍有%筆堂次不連續，交易已取消', remaining_errors;
  end if;
end $$;

commit;

select
  count(*) as corrected_rows,
  count(distinct purchase_id) as corrected_purchases
from private.session_usage_seq_corrections
where batch_version='v1.12.4';

