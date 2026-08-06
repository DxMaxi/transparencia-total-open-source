# Fase 2 — Pipeline parlamentar da V4

## Objetivo público

Transformar dados oficiais da Assembleia da República em informação clara e verificável para o cidadão, sem converter ausência de informação em conclusão política.

## Regras obrigatórias

- Cada sessão, iniciativa e votação conserva URL oficial, data de recolha e SHA-256.
- A recolha escreve primeiro em área privada de staging.
- Nenhum registo é publicado apenas porque foi recolhido.
- Campos ausentes na fonte permanecem vazios.
- Uma posição de grupo parlamentar não é atribuída a deputados individuais.
- Uma votação só é marcada como nominal quando os atores individuais estão explicitamente identificados.
- Duplicados são resolvidos por identificadores oficiais e não por semelhança de texto.
- Correções acrescentam novas versões e eventos de auditoria.

## Contratos de dados

- `ParliamentarySessionRecord`: sessão ou reunião oficial.
- `ParliamentaryInitiativeRecord`: iniciativa legislativa ou parlamentar.
- `ParliamentActivityDataset`: fotografia privada de sessões, iniciativas e votações pertencentes ao mesmo documento oficial.

## Próximas etapas

1. Descobrir os recursos oficiais de iniciativas e atividade parlamentar.
2. Normalizar sessões e iniciativas.
3. Persistir snapshots incrementais e append-only.
4. Relacionar votações a iniciativas apenas por chaves oficiais.
5. Criar revisão e publicação fail-closed.
6. Expor API pública com limitações e proveniência visíveis.
