alter table public.course_catalog add column active boolean not null default true;
insert into auth.users(id,email) values
('00000000-0000-4000-8000-000000000001','test-admin@localhost'),
('00000000-0000-4000-8000-000000000002','test-coach@localhost'),
('00000000-0000-4000-8000-000000000003','test-other@localhost');
update public.profiles set role='admin' where id='00000000-0000-4000-8000-000000000001';
insert into public.members(id,member_name,created_by) values
('00000000-0000-4000-8000-000000000004','獨立資料庫虛構客戶','00000000-0000-4000-8000-000000000001');
insert into public.course_catalog(id,course_name,report_category) values
('00000000-0000-4000-8000-000000000005','隔離測試課程','測試');
