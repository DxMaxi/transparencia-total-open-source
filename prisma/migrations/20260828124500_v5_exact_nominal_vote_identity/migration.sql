-- V5.45 preserva o identificador oficial que justificou a classificação PERSON.
-- Não existe backfill: fotografias anteriores ficam sem prova e exigem uma nova
-- versão do parser, nova revisão humana e nova publicação.
ALTER TABLE "vote_records"
ADD COLUMN "actor_source_id" TEXT;

ALTER TABLE "vote_records"
ADD CONSTRAINT "vote_records_actor_source_id_not_blank"
CHECK ("actor_source_id" IS NULL OR btrim("actor_source_id") <> '');

CREATE INDEX "vote_records_actor_type_actor_source_id_idx"
ON "vote_records"("actor_type", "actor_source_id");

CREATE UNIQUE INDEX "vote_records_person_official_id_per_event_key"
ON "vote_records"("vote_event_id", "actor_source_id")
WHERE "actor_type" = 'PERSON'::"VoteActorType" AND "actor_source_id" IS NOT NULL;
