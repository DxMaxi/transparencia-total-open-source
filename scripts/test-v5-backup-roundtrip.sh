#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_OS:-}" = Linux
test -n "${RUNNER_TEMP:-}"
export ENVIRONMENT=test CONFIRM_DISPOSABLE_DATABASE=true
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/transparencia_total_test
identity_file="$RUNNER_TEMP/synthetic-roundtrip.key"
ciphertext="$RUNNER_TEMP/synthetic-roundtrip.dump.age"
fingerprints="$RUNNER_TEMP/synthetic-roundtrip-fingerprints.json"
trap 'rm -f "$identity_file" "$ciphertext" "$fingerprints"' EXIT
age-keygen -o "$identity_file"
recipient="$(age-keygen -y "$identity_file")"
node scripts/verify-restored-migration.mjs capture "$fingerprints"
docker run --rm --network host postgres:17 pg_dump --dbname "$DATABASE_URL" \
  --format=custom --schema=public --no-owner --no-privileges \
  | age --recipient "$recipient" > "$ciphertext"
docker run --rm --network host postgres:17 psql --dbname "$DATABASE_URL" --set ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE transparencia_v5_roundtrip_test;' >/dev/null
export PGDATABASE=postgresql://postgres:postgres@localhost:5432/transparencia_v5_roundtrip_test
bash scripts/restore-public-backup-isolated.sh "$ciphertext" "$identity_file"
export DATABASE_URL="$PGDATABASE"
node scripts/bootstrap-supabase-test-database.mjs
node scripts/verify-restored-migration.mjs verify "$fingerprints" "$RUNNER_TEMP/synthetic-roundtrip.json"
