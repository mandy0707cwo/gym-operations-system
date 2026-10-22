-- v1.13.23：草稿只供本人與審核者，其他教練只能讀已核准班表。
-- 不修改排班內容、財務資料、寫入權限或防重送規則。
begin;
drop policy if exists schedule_month_read on public.staff_schedule_months;
create policy schedule_month_read on public.staff_schedule_months for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')
         or state='approved'));

drop policy if exists schedule_day_read on public.staff_schedule_days;
create policy schedule_day_read on public.staff_schedule_days for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')
         or exists(select 1 from public.staff_schedule_months m
                   where m.coach_id=staff_schedule_days.coach_id
                     and m.month_start=staff_schedule_days.month_start and m.state='approved')));

drop policy if exists schedule_preference_read on public.staff_schedule_preferences;
create policy schedule_preference_read on public.staff_schedule_preferences for select to authenticated
 using ((select schedule_private.actor_role()) is not null and
        (coach_id=(select auth.uid()) or (select schedule_private.actor_role()) in ('manager','admin')));
commit;
