# Índice documental e regra de leitura

Revisto em 11 de setembro de 2026 sobre o conjunto versionado de `main`
`642d8fc8a698c96af45d9c3abdaea9f04cf2866a`, com correções documentais nesta revisão.

## Começar aqui

- [Checklist canónica de conclusão da V5](V5_RELEASE_CHECKLIST.md): condições e provas por ambiente.
- [Registo de entrega e operações de produção](V5_DELIVERY_2026-09-09.md): consultar a entrada mais recente.
- [Revisão documental completa do inventário](V5_DOCUMENTATION_AUDIT_2026-09-11.md): alcance, correções e lacunas.
- [Publicação](DEPLOYMENT.md), [recuperação](DATABASE_RECOVERY.md) e [fontes](DATA_SOURCES.md).

## Como interpretar os documentos

Um contrato V5 numerado descreve o que a respetiva etapa acrescentou e os limites que deve manter.
Frases como “não executa produção” ou “próximo desenvolvimento” referem-se à entrega dessa etapa;
não são provas do estado remoto atual. Os checkpoints V2/V3/V4 e auditorias datadas preservam
a história e não devem ser usados como instruções para contornar os workflows V5.

Uma autorização operacional posterior do responsável deve ser considerada no seu âmbito; não se
pede novamente apenas por um documento antigo a chamar futura. Continuam obrigatórias as
condições técnicas e as decisões humanas específicas, incluindo revisão editorial e jurídica.
Aplicar o esquema em produção não autoriza ingestão ou publicação por um coletor limitado a staging.

Os valores de teste, contagens, RPO/RTO e estados de CI valem para a data e o commit indicados.
O código chega à V5.54; relações factuais V5.55 e ensaios remotos continuam na checklist.
Esta revisão não declara a `v0.5.0` pronta nem transforma modelos legais em pareceres concluídos.

## Inventário dos 90 documentos de origem

Inclui todos os Markdown/MDX versionados, licenças textuais e o JSON documental existente.
Os dois documentos novos desta revisão são este índice e o relatório ligado acima.

| Documento | Uso e limite |
|---|---|
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Instruções ou governação; ler com o checkpoint atual |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Instruções ou governação; ler com o checkpoint atual |
| [LICENSE](../LICENSE) | Licenciamento; direitos das fontes separados |
| [LICENSES/CC-BY-NC-4.0.txt](../LICENSES/CC-BY-NC-4.0.txt) | Licenciamento; direitos das fontes separados |
| [LICENSES/MIT-v0.4.0.txt](../LICENSES/MIT-v0.4.0.txt) | Licenciamento; direitos das fontes separados |
| [LICENSING.md](../LICENSING.md) | Licenciamento; direitos das fontes separados |
| [README.md](../README.md) | Instruções ou governação; ler com o checkpoint atual |
| [SECURITY.md](../SECURITY.md) | Instruções ou governação; ler com o checkpoint atual |
| [backend/README.md](../backend/README.md) | Instruções ou governação; ler com o checkpoint atual |
| [config/certificates/README.md](../config/certificates/README.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/AI_GOVERNANCE.md](AI_GOVERNANCE.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/AUDIT_2026-08-15.md](AUDIT_2026-08-15.md) | Checkpoint/contrato histórico |
| [docs/BACKUP_BACKBLAZE_B2.md](BACKUP_BACKBLAZE_B2.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/DATABASE_RECOVERY.md](DATABASE_RECOVERY.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/DATA_SOURCES.md](DATA_SOURCES.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/DEPLOYMENT.md](DEPLOYMENT.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/DPIA_TEMPLATE.md](DPIA_TEMPLATE.md) | Modelo por preencher; não é uma AIPD concluída |
| [docs/GOVERNANCE.md](GOVERNANCE.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/NEUTRALITY.md](NEUTRALITY.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/PUBLIC_API_RESILIENCE.md](PUBLIC_API_RESILIENCE.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/PYTHON_RUNTIME_POLICY.md](PYTHON_RUNTIME_POLICY.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/RESTORE_ATTESTATION_2026-09-09.json](RESTORE_ATTESTATION_2026-09-09.json) | Checkpoint/contrato histórico |
| [docs/V2_GOVERNANCE.md](V2_GOVERNANCE.md) | Checkpoint/contrato histórico |
| [docs/V3_LIVE_DATA.md](V3_LIVE_DATA.md) | Checkpoint/contrato histórico |
| [docs/V4_BASE_STAGING.md](V4_BASE_STAGING.md) | Checkpoint/contrato histórico |
| [docs/V4_PARLIAMENT_PIPELINE.md](V4_PARLIAMENT_PIPELINE.md) | Checkpoint/contrato histórico |
| [docs/V4_PARLIAMENT_PIPELINE_STATUS.md](V4_PARLIAMENT_PIPELINE_STATUS.md) | Checkpoint/contrato histórico |
| [docs/V4_PHASE2_PARLIAMENT_PIPELINE.md](V4_PHASE2_PARLIAMENT_PIPELINE.md) | Checkpoint/contrato histórico |
| [docs/V4_PRODUCTION_OPERATIONS.md](V4_PRODUCTION_OPERATIONS.md) | Checkpoint/contrato histórico |
| [docs/V4_PUBLIC_ROLLOUT.md](V4_PUBLIC_ROLLOUT.md) | Checkpoint/contrato histórico |
| [docs/V4_RAW_EVIDENCE.md](V4_RAW_EVIDENCE.md) | Checkpoint/contrato histórico |
| [docs/V4_RELEASE_CHECKLIST.md](V4_RELEASE_CHECKLIST.md) | Checkpoint/contrato histórico |
| [docs/V4_TO_V5_RELEASE_GATE.md](V4_TO_V5_RELEASE_GATE.md) | Checkpoint/contrato histórico |
| [docs/V5_AI_PUBLICATION.md](V5_AI_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_CONTRACT_EDITORIAL.md](V5_BASE_CONTRACT_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_CONTRACT_ORGANISATION_MATCHING.md](V5_BASE_CONTRACT_ORGANISATION_MATCHING.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_CONTRACT_PUBLICATION.md](V5_BASE_CONTRACT_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_ORGANISATION_IDENTITY.md](V5_BASE_ORGANISATION_IDENTITY.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_ORGANISATION_PUBLICATION.md](V5_BASE_ORGANISATION_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_BASE_TEMPORAL_SCOPE.md](V5_BASE_TEMPORAL_SCOPE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_DELIVERY_2026-09-09.md](V5_DELIVERY_2026-09-09.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/V5_EDITORIAL_FOUNDATION.md](V5_EDITORIAL_FOUNDATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_EDITORIAL_STAGING_ACTIVATION.md](V5_EDITORIAL_STAGING_ACTIVATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_EDITORIAL_STAGING_EXECUTION_PLAN.md](V5_EDITORIAL_STAGING_EXECUTION_PLAN.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_EDITORIAL_STAGING_READINESS.md](V5_EDITORIAL_STAGING_READINESS.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_EPT_LEGAL_PUBLICATION_GATE.md](V5_EPT_LEGAL_PUBLICATION_GATE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_EPT_PUBLIC_INTEREST_EDITORIAL.md](V5_EPT_PUBLIC_INTEREST_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_GLOBAL_SEARCH_AND_PERFORMANCE.md](V5_GLOBAL_SEARCH_AND_PERFORMANCE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_OPERATIONAL_READINESS.md](V5_OPERATIONAL_READINESS.md) | Checkpoint/contrato histórico |
| [docs/V5_PARLIAMENT_COVERAGE_AND_BACKFILL.md](V5_PARLIAMENT_COVERAGE_AND_BACKFILL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_DEPUTY_OBSERVATIONS.md](V5_PARLIAMENT_DEPUTY_OBSERVATIONS.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_EDITORIAL_ADAPTER.md](V5_PARLIAMENT_EDITORIAL_ADAPTER.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_PUBLIC_EXPERIENCE.md](V5_PARLIAMENT_PUBLIC_EXPERIENCE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_RESOURCE_ARCHIVE.md](V5_PARLIAMENT_RESOURCE_ARCHIVE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_RESOURCE_MANIFEST.md](V5_PARLIAMENT_RESOURCE_MANIFEST.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_RESOURCE_NORMALIZATION.md](V5_PARLIAMENT_RESOURCE_NORMALIZATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_SCOPE_PUBLICATION.md](V5_PARLIAMENT_SCOPE_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_SOURCE_CATALOGUE.md](V5_PARLIAMENT_SOURCE_CATALOGUE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_VOTE_NORMALIZATION.md](V5_PARLIAMENT_VOTE_NORMALIZATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PARLIAMENT_WITHDRAWAL.md](V5_PARLIAMENT_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_ATTENDANCE_EDITORIAL.md](V5_POLITICIAN_ATTENDANCE_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_ATTENDANCE_PUBLICATION.md](V5_POLITICIAN_ATTENDANCE_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_ATTENDANCE_WITHDRAWAL.md](V5_POLITICIAN_ATTENDANCE_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_DIRECTORY.md](V5_POLITICIAN_DIRECTORY.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md](V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION.md](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL.md](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_MANDATE_EDITORIAL.md](V5_POLITICIAN_MANDATE_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_MANDATE_PUBLICATION.md](V5_POLITICIAN_MANDATE_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_MANDATE_WITHDRAWAL.md](V5_POLITICIAN_MANDATE_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_NOMINAL_VOTE_IDENTITY.md](V5_POLITICIAN_NOMINAL_VOTE_IDENTITY.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_OFFICE_EDITORIAL.md](V5_POLITICIAN_OFFICE_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_OFFICE_PUBLICATION.md](V5_POLITICIAN_OFFICE_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_OFFICE_WITHDRAWAL.md](V5_POLITICIAN_OFFICE_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILES.md](V5_POLITICIAN_PROFILES.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILE_EDITORIAL.md](V5_POLITICIAN_PROFILE_EDITORIAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILE_PUBLICATION_READINESS.md](V5_POLITICIAN_PROFILE_PUBLICATION_READINESS.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION.md](V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILE_SNAPSHOT_REPUBLICATION.md](V5_POLITICIAN_PROFILE_SNAPSHOT_REPUBLICATION.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_POLITICIAN_PROFILE_SNAPSHOT_WITHDRAWAL.md](V5_POLITICIAN_PROFILE_SNAPSHOT_WITHDRAWAL.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PROMESSOMETRO_CATALOGUE.md](V5_PROMESSOMETRO_CATALOGUE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PROMESSOMETRO_VOCABULARY.md](V5_PROMESSOMETRO_VOCABULARY.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_PUBLIC_QUALITY_GATE.md](V5_PUBLIC_QUALITY_GATE.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_RELEASE_CHECKLIST.md](V5_RELEASE_CHECKLIST.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/V5_RELEASE_HARDENING.md](V5_RELEASE_HARDENING.md) | Contrato de etapa V5; ativação depende da checklist |
| [docs/V5_RELEASE_PLAN.md](V5_RELEASE_PLAN.md) | Instruções ou governação; ler com o checkpoint atual |
| [docs/V5_RELEASE_PRIVACY_AUDIT.md](V5_RELEASE_PRIVACY_AUDIT.md) | Checkpoint/contrato histórico |
| [docs/V5_STAGING_WORKFLOW_FOUNDATION.md](V5_STAGING_WORKFLOW_FOUNDATION.md) | Contrato de etapa V5; ativação depende da checklist |
