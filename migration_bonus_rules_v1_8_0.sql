select 'v1.8.0' as migration_version;

create table if not exists public.bonus_rules (
  id uuid primary key default gen_random_uuid(),
  rule_name text not null check (length(trim(rule_name)) > 0),
  effective_from date not null,
  effective_to date,
  talk_rate numeric(7,6) not null check (talk_rate >= 0 and talk_rate <= 1),
  completion_rate numeric(7,6) not null check (completion_rate >= 0 and completion_rate <= 1),
  referral_first_talk_eligible boolean not null default false,
  referral_first_completion_eligible boolean not null default false,
  referral_renewal_talk_eligible boolean not null default true,
  referral_renewal_completion_eligible boolean not null default true,
  active boolean not null default true,
  note text,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from)
);

create index if not exists idx_bonus_rules_effective_dates
  on public.bonus_rules(effective_from desc,effective_to);

create or replace function public.validate_bonus_rule_period()
returns trigger language plpgsql set search_path=public as $$
begin
  if new.active and exists (
    select 1 from public.bonus_rules r
    where r.id <> new.id and r.active
      and daterange(r.effective_from,coalesce(r.effective_to,'infinity'::date),'[]')
          && daterange(new.effective_from,coalesce(new.effective_to,'infinity'::date),'[]')
  ) then
    raise exception '啟用中的獎金規則生效期間不可重疊';
  end if;
  new.updated_at=now();
  return new;
end $$;

drop trigger if exists trg_validate_bonus_rule_period on public.bonus_rules;
create trigger trg_validate_bonus_rule_period
before insert or update on public.bonus_rules
for each row execute function public.validate_bonus_rule_period();

alter table public.bonus_rules enable row level security;
drop policy if exists bonus_rules_read on public.bonus_rules;
drop policy if exists bonus_rules_admin_all on public.bonus_rules;
create policy bonus_rules_read on public.bonus_rules
  for select to authenticated
  using (exists(select 1 from public.profiles where id=auth.uid() and active));
create policy bonus_rules_admin_all on public.bonus_rules
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

grant select,insert,update,delete on public.bonus_rules to authenticated;

insert into public.bonus_rules(
  rule_name,effective_from,effective_to,talk_rate,completion_rate,
  referral_first_talk_eligible,referral_first_completion_eligible,
  referral_renewal_talk_eligible,referral_renewal_completion_eligible,
  note
)
select
  '初始獎金規則',date '1900-01-01',null,0.03,0.04,
  false,false,true,true,
  '醫生轉介首購不計談單及結單獎金；其他購買依設定比例計算。'
where not exists(select 1 from public.bonus_rules);

select rule_name,effective_from,effective_to,talk_rate,completion_rate,active
from public.bonus_rules
order by effective_from;
