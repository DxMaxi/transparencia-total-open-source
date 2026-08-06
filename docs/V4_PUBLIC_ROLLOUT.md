# Activação pública da V4

## Objectivo

A activação pública mantém quatro estados distintos: recolha, arquivo privado, revisão humana e publicação. Um estado `SUCCEEDED` numa fonte significa que o índice ou catálogo oficial foi recolhido e preservado; não significa que todos os seus registos foram publicados.

## Primeira publicação

O directório factual da XVII Legislatura é a primeira projecção pública da V4. O bootstrap só autoriza a publicação quando a base de produção confirma simultaneamente:

- SHA-256 `e54b30869212ea3d50a401637a31847339e29dcfdac9ec7b66e51c0def0cd9b9`;
- exactamente 286 pessoas na fotografia;
- original oficial atestado no arquivo privado;
- correspondência com o artefacto `data/revisao-deputados-xvii.json`.

Qualquer divergência bloqueia o arranque. A decisão cria uma revisão e um evento de auditoria por pessoa e é idempotente.

## Cobertura automática após o arranque

O backend recolhe, em segundo plano, apenas índices ou catálogos públicos:

- catálogo oficial do Portal BASE;
- índice público do Diário da República;
- índice da Entidade para a Transparência;
- índice do Tribunal de Contas;
- portal de dados abertos do Parlamento Europeu;
- índice público do SNS.

Os bytes exactos são guardados em armazenamento privado content-addressed no PostgreSQL, ligados a `SourceDocument`, `SourceArchiveAttestation`, `SyncRun` e `AuditEvent`. As tabelas de prova são append-only.

## Limites públicos

- Votações parlamentares continuam `PARTIAL` enquanto não existir identificação individual oficial inequívoca.
- O catálogo BASE não equivale a contratos publicados.
- O índice DRE não equivale a diplomas publicados.
- O índice EPT não recolhe declarações nem áreas autenticadas.
- O índice SNS não representa cobertura territorial nacional.
- Tribunal de Contas e Parlamento Europeu são cobertura de origem; não produzem conclusões automáticas.
- Promessas, contratos, relações e alertas continuam a exigir revisão própria antes da publicação.

## Operação protegida

Os endpoints em `/api/v1/admin/v4-rollout` exigem `X-Admin-Key`. Permitem pré-visualizar e confirmar a fotografia parlamentar com SHA e contagem exactos, ou repetir a recolha dos índices. Não existe endpoint de aprovação automática de votações, contratos, declarações ou relações.
