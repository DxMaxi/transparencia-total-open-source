#!/usr/bin/env bash
# Rebuild only application data. Auth rows below are inert FK placeholders, not accounts.
set -euo pipefail
test "$#" -eq 2
case "${PGDATABASE:-}" in
  postgresql://postgres:restore-drill-only@localhost:5432/transparencia_restore_test|postgresql://postgres:restore-drill-only@localhost:5432/transparencia_v5_roundtrip_test) ;;
  *) echo "O restauro recusa qualquer destino fora dos dois PostgreSQL efémeros." >&2; exit 1 ;;
esac
ciphertext="$1"
identity_file="$2"
emit_section() {
  age --decrypt --identity "$identity_file" "$ciphertext" \
    | docker run --rm --network host -i postgres:17 pg_restore \
        --file=- --section="$1" --clean --if-exists --no-owner --no-privileges --exit-on-error
}
(
  # COMMIT is emitted only after every decrypt/restore producer succeeds.
  echo 'BEGIN;'
  echo 'CREATE SCHEMA IF NOT EXISTS auth; CREATE TABLE IF NOT EXISTS auth.users (id UUID PRIMARY KEY);'
  emit_section pre-data
  emit_section data
  cat <<'SQL'
DO $restore_auth_placeholders$
BEGIN
  IF to_regclass('public.staff_profiles') IS NOT NULL THEN
    EXECUTE 'INSERT INTO auth.users(id) SELECT DISTINCT auth_user_id FROM public.staff_profiles ON CONFLICT DO NOTHING';
  END IF;
END
$restore_auth_placeholders$;
SQL
  emit_section post-data
  # The portable dump excludes ACLs. Restore the application's deny-all browser
  # model before committing, rather than inheriting PostgreSQL PUBLIC defaults.
  cat <<'SQL'
DO $restore_roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
END
$restore_roles$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;
SQL
  echo 'COMMIT;'
) | docker run --rm --network host -i -e PGDATABASE postgres:17 \
      psql --no-psqlrc --set ON_ERROR_STOP=1 --dbname "$PGDATABASE" >/dev/null
echo 'Restauro público isolado concluído; contas, credenciais e MFA não foram restaurados.'
