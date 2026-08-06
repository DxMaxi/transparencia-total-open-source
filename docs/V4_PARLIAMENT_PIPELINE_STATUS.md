# Estado da Fase 2 — Pipeline parlamentar

## Concluído

- contratos Pydantic para sessões, iniciativas e dataset agregado;
- normalização independente de sessões e iniciativas;
- deduplicação por identificador oficial;
- preservação de URL, data de recolha e SHA-256;
- campos ausentes permanecem vazios;
- testes para datas, duplicados, URLs e registos incompletos;
- critérios formais para encerrar a V4 antes de iniciar a V5.

## Em curso

- integração com o `ParlamentoCollector`;
- descoberta do recurso oficial de iniciativas;
- persistência incremental em PostgreSQL;
- ligação entre iniciativas, sessões e votações.

## Por fazer nesta fase

- publicação editorial controlada;
- endpoints públicos paginados;
- frontend de iniciativas e votações;
- testes end-to-end com dados oficiais;
- validação em produção.
