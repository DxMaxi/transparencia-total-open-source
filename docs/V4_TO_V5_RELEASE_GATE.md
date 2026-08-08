# Critérios para encerrar a V4 e iniciar a V5

A V5 só começa depois de a V4 estar em produção e cumprir todos os critérios abaixo.

Estado da release candidate: os gates de código estão implementados; CI remoto, migrações,
recolha/revisão real e validação no domínio oficial continuam pendentes até execução autorizada.

## Produção

- API pública com liveness e readiness reais.
- Migrações, recolhas e publicações separadas do arranque.
- Monitorização diária e verificação semanal do arquivo.
- Custos controlados e alertas antes de ultrapassar limites gratuitos.
- Backups e procedimento de recuperação documentados.

## Parlamento

- Deputados, sessões, iniciativas e votações recolhidos de fontes oficiais.
- Atualização versionada e idempotente, sem sobrescrever fotografias anteriores.
- Votos nominais separados de posições partidárias.
- URL, data de recolha e SHA-256 preservados.
- Campos ausentes permanecem vazios; não existem inferências publicadas como factos.
- Publicação sujeita a revisão humana e histórico append-only.

## Produto público

- Perfis, diretório, iniciativas e votações acessíveis em português claro.
- Estados LIVE, EMPTY e UNAVAILABLE visíveis.
- Dados DEMO proibidos no domínio oficial.
- Fontes e limitações apresentadas junto dos dados.
- Acessibilidade e navegação móvel validadas.

## Qualidade

- CI verde.
- Testes de migração desde base vazia.
- Testes de API, integração PostgreSQL e browser/preview.
- Smoke test após deploy.
- Sem bloqueios críticos de segurança ou integridade.

## Regra de passagem

A versão é marcada como V4 concluída apenas após validação em produção. A criação de funcionalidades
exclusivas da V5 não deve ocultar, adiar ou contornar falhas pendentes da V4.

