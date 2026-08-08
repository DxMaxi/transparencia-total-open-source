# Estado da Fase 2 — Pipeline parlamentar

## Concluído

- contratos Pydantic para reuniões observadas, iniciativas, votações e dataset agregado;
- normalização baseada nas tags documentadas pela Assembleia da República;
- propagação segura da chave da iniciativa e recusa de ligação ambígua de uma votação partilhada;
- preservação de bytes, URL, data de recolha, SHA-256 da fonte e SHA-256 normalizado;
- manifesto de fotografia e tabelas factuais protegidos contra `UPDATE`/`DELETE`;
- persistência idempotente que exige nova versão de parser para uma correção;
- pré-visualização e decisão humana append-only separadas para atividade e votos;
- endpoints públicos fail-closed, perfil/Investigador no mesmo gate e página parlamentar responsiva;
- dados de demonstração desativados em produção;
- lint, formatação, mypy, testes unitários, Prisma e build local verdes;
- teste de integração PostgreSQL do circuito arquivo → snapshot → revisão → público incluído no CI.

## Gate operacional pendente

- execução do CI remoto sobre o commit final;
- aplicação controlada das migrações no PostgreSQL de produção;
- primeira recolha real privada da XVII Legislatura;
- conferência humana dos dois hashes, contagens, cobertura e posições `UNKNOWN`;
- publicação explícita apenas dos âmbitos aprovados;
- deploy do frontend/API autorizado e smoke tests no domínio oficial.

## Fora do merge de código

O merge não publica fotografias, não executa migrações de produção e não altera
`www.transparenciatotal.pt`. Essas ações permanecem deliberadamente separadas e exigem autorização,
segredos do ambiente e revisão humana.
