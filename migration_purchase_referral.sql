-- 為課程購買增加轉介欄位，並讓管理查詢可讀取；可重複執行。
alter table public.purchases
  add column if not exists referral text;

create or replace view public.purchase_balances with (security_invoker=true) as
select p.id purchase_id, p.member_id, m.member_name, p.course_name, p.coach_id,
       pr.display_name coach_name, p.total_sessions, p.total_amount,
       count(u.id)::integer used_sessions,
       p.total_sessions-count(u.id)::integer remaining_sessions,
       round(p.total_amount-coalesce(sum(u.deducted_amount),0),2) remaining_amount,
       p.expiry_date, p.status, p.note, p.referral
from public.purchases p
join public.members m on m.id=p.member_id
join public.profiles pr on pr.id=p.coach_id
left join public.session_usages u on u.purchase_id=p.id
group by p.id,m.member_name,pr.display_name;
