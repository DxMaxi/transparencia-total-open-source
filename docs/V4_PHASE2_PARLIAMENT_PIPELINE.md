# Fase 2 — Pipeline parlamentar da V4

## Objetivo público

Transformar dados oficiais da Assembleia da República em informação clara e verificável para o cidadão, sem converter ausência de informação em conclusão política.

## Regras obrigatórias

- Cada reunião observada, iniciativa e votação conserva URL oficial, data de recolha e SHA-256.
- A recolha escreve primeiro em área privada de staging.
- Nenhum registo é publicado apenas porque foi recolhido.
- Campos ausentes na fonte permanecem vazios.
- Uma posição de grupo parlamentar não é atribuída a deputados individuais.
- Uma votação só é marcada como nominal quando os atores individuais estão explicitamente identificados.
- Duplicados são resolvidos por identificadores oficiais e não por semelhança de texto.
- Correções acrescentam novas versões e eventos de auditoria.

## Contratos de dados

- `ParliamentarySessionRecord`: reunião observada num evento de votação; não representa a agenda completa.
- `ParliamentaryInitiativeRecord`: iniciativa legislativa ou parlamentar.
- `ParliamentActivityDataset`: fotografia privada de sessões, iniciativas e votações pertencentes ao mesmo documento oficial.

## Estado

Os seis pontos técnicos — descoberta, normalização, snapshots append-only, associação segura,
revisão fail-closed e API/PWA — estão implementados na release candidate. A recolha, revisão,
publicação e validação no ambiente de produção continuam gates operacionais separados.

O contrato e o runbook canónicos estão em `V4_PARLIAMENT_PIPELINE.md`; o estado de fecho está em
`V4_PARLIAMENT_PIPELINE_STATUS.md`.
