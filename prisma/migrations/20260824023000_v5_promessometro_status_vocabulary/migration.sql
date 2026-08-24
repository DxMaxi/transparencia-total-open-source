-- A V5 publica apenas o vocabulário editorial aprovado. Os valores legados
-- permanecem no tipo PostgreSQL para que esta migração não reescreva nem
-- reclassifique decisões históricas. As projeções públicas recusam-nos.
ALTER TYPE "PromiseStatus" ADD VALUE IF NOT EXISTS 'NOT_STARTED';
ALTER TYPE "PromiseStatus" ADD VALUE IF NOT EXISTS 'PARTIAL';
