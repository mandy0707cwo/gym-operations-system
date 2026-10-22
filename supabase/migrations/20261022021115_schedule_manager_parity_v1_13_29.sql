-- 僅同步排班主管與管理員；維持原子交易、鎖、收據、RLS與原授權。
-- 舊migration保持不動。若前置函式不符預期即失敗，不直接建立寬鬆替代函式。
do $migration$
declare definition text;
 old_guard text := $old$if r<>'admin' then raise exception using errcode='42501',message='僅系統管理員可確認排休額度';end if;$old$;
 new_guard text := $new$if r not in ('manager','admin') then raise exception using errcode='42501',message='僅主管或系統管理員可確認排休額度';end if;$new$;
begin
 definition:=pg_get_functiondef('schedule_private.allowance_save(uuid,date,integer,jsonb)'::regprocedure);
 if strpos(definition,old_guard)>0 then
  execute replace(definition,old_guard,new_guard);
 elsif strpos(definition,new_guard)=0 then
  raise exception '額度函式版本不符，停止更新，請查核前置migration';
 end if;
end $migration$;

alter policy allowance_log_read on public.staff_schedule_allowance_logs
 to authenticated using ((select schedule_private.actor_role()) in ('manager','admin'));

-- 不向教練／匿名帳號增加權限，不授予任何直接INSERT／UPDATE／DELETE。
