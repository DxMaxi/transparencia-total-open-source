-- V5.10: impedir que objetos futuros recuperem acesso browser por defeito.
--
-- PostgreSQL concede EXECUTE a PUBLIC nas novas funcoes. Uma revogacao
-- limitada a `IN SCHEMA public` nao remove esse privilegio global; apenas
-- desfaz GRANTs predefinidos anteriormente para esse esquema. A migracao V4
-- ja fechou os objetos existentes e os defaults especificos de `public`.
-- Esta migracao acrescenta a parte global para o papel que executa as
-- migracoes, sem conceder qualquer acesso novo.

ALTER DEFAULT PRIVILEGES
  REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES
  REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES
  REVOKE ALL PRIVILEGES ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
  api_role TEXT;
BEGIN
  FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES REVOKE ALL PRIVILEGES ON TABLES FROM %I',
        api_role
      );
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES REVOKE ALL PRIVILEGES ON SEQUENCES FROM %I',
        api_role
      );
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES REVOKE ALL PRIVILEGES ON FUNCTIONS FROM %I',
        api_role
      );
    END IF;
  END LOOP;
END
$$;
