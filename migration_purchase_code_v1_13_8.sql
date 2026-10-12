-- v1.13.8：固定對外購課編號；不修改 UUID、付款、銷課或金額。
-- 執行前備份。整個 migration 為單一交易；取得排他鎖避免歷史映射期間新增。
begin;
set local lock_timeout = '10s';
set local statement_timeout = '120s';
lock table public.purchases in access exclusive mode;

create schema if not exists purchase_identity;
revoke all on schema purchase_identity from public, anon, authenticated, service_role;
create table if not exists purchase_identity.daily_counters (
    code_date date primary key,
    last_sequence bigint not null check (last_sequence > 0)
);
-- 刻意不設定購課外鍵：已刪除購課的編號仍須保留，不能重新發出。
create table if not exists purchase_identity.issued_codes (
    purchase_id uuid primary key,
    purchase_code text not null unique,
    code_date date not null,
    sequence_no bigint not null check (sequence_no > 0),
    issued_at timestamptz not null default now(),
    unique (code_date, sequence_no)
);
alter table purchase_identity.daily_counters enable row level security;
alter table purchase_identity.issued_codes enable row level security;
revoke all on all tables in schema purchase_identity from public, anon, authenticated, service_role;

alter table public.purchases add column if not exists purchase_code text;

do $backfill$
declare before_hash text; after_hash text;
begin
    if exists (select 1 from public.purchases where purchase_date is null or not isfinite(purchase_date)) then
        raise exception '購課日期缺漏或不合法，停止編號升級，請先查核資料';
    end if;
    select md5(coalesce(string_agg((to_jsonb(p)-'purchase_code')::text, '' order by id), ''))
      into before_hash from public.purchases p;
    -- 只允許首次完整回填，或已完整升級的安全重跑；不對部分資料重新排序。
    if exists (select 1 from public.purchases where purchase_code is null) then
        if exists (select 1 from public.purchases where purchase_code is not null)
           or exists (select 1 from purchase_identity.issued_codes) then
            raise exception '固定編號部分缺漏，停止自動回填，禁止重新編排';
        end if;
        with ranked as (
            select id, to_char(purchase_date,'YYYYMMDD') as date_key,
              row_number() over (partition by purchase_date order by created_at, id) as seq
            from public.purchases
        )
        update public.purchases p set purchase_code = r.date_key || '-' ||
          lpad(r.seq::text, greatest(3,length(r.seq::text)), '0')
          from ranked r where p.id=r.id;
    end if;
    select md5(coalesce(string_agg((to_jsonb(p)-'purchase_code')::text, '' order by id), ''))
      into after_hash from public.purchases p;
    if before_hash is distinct from after_hash then
        raise exception '購課原有資料檢核不符，整筆升級回滾';
    end if;
end;
$backfill$;

alter table public.purchases alter column purchase_code set not null;
create unique index if not exists purchases_purchase_code_key on public.purchases(purchase_code);
do $constraints$
begin
    if not exists (select 1 from pg_constraint where conrelid='public.purchases'::regclass and conname='purchases_purchase_code_format') then
        alter table public.purchases add constraint purchases_purchase_code_format
          check (purchase_code ~ '^[0-9]{8}-[0-9]{3,}$');
    end if;
end;
$constraints$;

insert into purchase_identity.issued_codes(purchase_id,purchase_code,code_date,sequence_no)
select id,purchase_code,to_date(left(purchase_code,8),'YYYYMMDD'),split_part(purchase_code,'-',2)::bigint
from public.purchases on conflict (purchase_id) do nothing;
-- 任何 ledger 不一致均停止，不嘗試偷偷更換既有編號。
do $ledger_check$
begin
    if exists (select 1 from public.purchases p left join purchase_identity.issued_codes i on i.purchase_id=p.id
               where i.purchase_code is distinct from p.purchase_code) then
        raise exception '購課固定編號與保留紀錄不一致，停止升級';
    end if;
end;
$ledger_check$;
insert into purchase_identity.daily_counters(code_date,last_sequence)
select code_date,max(sequence_no) from purchase_identity.issued_codes group by code_date
on conflict (code_date) do update set last_sequence=greatest(purchase_identity.daily_counters.last_sequence,excluded.last_sequence);

-- SECURITY DEFINER 僅用於不可公開的計數器；不替代購課本身的 RLS。
-- 無 RPC 呼叫權限、固定 search_path、限制真實登入角色及有效員工。
create or replace function purchase_identity.assign_purchase_code()
returns trigger language plpgsql security definer set search_path = ''
as $function$
declare seq bigint; caller_role text := current_setting('role',true);
begin
    if tg_table_schema <> 'public' or tg_table_name <> 'purchases' or tg_when <> 'BEFORE' then
        raise exception '固定購課編號僅能由購課觸發器執行';
    end if;
    if tg_op='UPDATE' then
        if new.purchase_code is distinct from old.purchase_code or new.id is distinct from old.id then
            raise exception '購課識別碼及固定購課編號不可修改';
        end if;
        return new;
    end if;
    if caller_role='authenticated' then
        if auth.uid() is null or not exists (
            select 1 from public.profiles p where p.id=auth.uid() and p.active
            and p.role in ('coach','shared_coach','manager','admin')
        ) then
            raise exception '未登入或停用帳號不可建立購課編號';
        end if;
    elsif caller_role='service_role' then
        -- 伺服器匯入仍須指定有效系統管理員為建立者。
        if not exists (select 1 from public.profiles p where p.id=new.created_by and p.active and p.role='admin') then
            raise exception '伺服器匯入須由有效系統管理員建立';
        end if;
    elsif not (caller_role in ('none','postgres') and session_user='postgres') then
        raise exception '此角色不可建立購課編號';
    end if;
    if new.purchase_code is not null then
        raise exception '購課編號由系統產生，不可自行指定；還原備份請依升級文件處理';
    end if;
    if new.purchase_date is null or not isfinite(new.purchase_date) then
        raise exception '購課日期不可空白或不合法';
    end if;
    -- ON CONFLICT 取得同日期計數器的列鎖；交易提交前其他交易會等待。
    insert into purchase_identity.daily_counters(code_date,last_sequence) values(new.purchase_date,1)
    on conflict (code_date) do update set last_sequence=purchase_identity.daily_counters.last_sequence+1
    returning last_sequence into seq;
    new.purchase_code := to_char(new.purchase_date,'YYYYMMDD') || '-' || lpad(seq::text,greatest(3,length(seq::text)),'0');
    insert into purchase_identity.issued_codes(purchase_id,purchase_code,code_date,sequence_no)
      values(new.id,new.purchase_code,new.purchase_date,seq);
    return new;
end;
$function$;
revoke all on function purchase_identity.assign_purchase_code() from public,anon,authenticated,service_role;
drop trigger if exists assign_purchase_code on public.purchases;
create trigger assign_purchase_code before insert or update on public.purchases
for each row execute function purchase_identity.assign_purchase_code();
comment on column public.purchases.purchase_code is '永久對外購課編號；首次按全域管理員排序回填，之後不重新編排。UUID仍為外鍵。';
notify pgrst, 'reload schema';
commit;
