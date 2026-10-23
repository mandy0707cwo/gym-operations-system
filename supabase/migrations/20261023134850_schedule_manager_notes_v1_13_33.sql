-- v1.13.33：排班更正不另要求原因；保留角色、版本鎖、收據及前後值稽核。
-- 只調整既有私有函式，不修改資料、舊migration、RLS或財務。
begin;
set local lock_timeout='10s';
do $migration$
declare definition text;
 old_guard text := $old$if r in ('manager','admin') and reason='' then raise exception '主管或管理員更正須填寫原因';end if;$old$;
 new_guard text := '-- v33: 日班更正不另要求原因，備註及前後值仍記錄';
 old_reason text := $old$reason text:=trim(coalesce(p_payload->>'reason',''));$old$;
 new_reason text := $new$reason text:=trim(coalesce(nullif(p_payload->>'reason',''),p_payload->>'note',''));$new$;
begin
 definition:=pg_get_functiondef('schedule_private.command(uuid,uuid,date,integer,text,jsonb)'::regprocedure);
 if strpos(definition,'m.coach_locked or m.state')=0 then raise exception '缺少v32整月鎖定，停止升級';end if;
 if strpos(definition,old_guard)>0 then definition:=replace(definition,old_guard,new_guard);
 elsif strpos(definition,new_guard)=0 then raise exception '排班原因檢核版本不符，停止升級';end if;
 if strpos(definition,old_reason)>0 then definition:=replace(definition,old_reason,new_reason);
 elsif strpos(definition,new_reason)=0 then raise exception '排班說明來源版本不符，停止升級';end if;
 execute definition;
 definition:=pg_get_functiondef('schedule_private.manager_confirm(uuid,uuid,date,integer,text,jsonb)'::regprocedure);
 if strpos(definition,$old$or reason='' or length(reason)>1000$old$)>0 then
  definition:=replace(definition,$old$or reason='' or length(reason)>1000$old$,$new$or length(reason)>1000$new$);
 elsif strpos(definition,$new$or jsonb_typeof(p_payload)<>'object' or length(reason)>1000$new$)=0 then
  raise exception '代填確認函式版本不符，停止升級';
 end if;
 execute definition;
end $migration$;
commit;
