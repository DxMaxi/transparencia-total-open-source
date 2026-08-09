# Fecho da V4 e entrada na V5

Este documento regista a validação efetivamente executada em produção em 9 de agosto de 2026.
Não é uma declaração de conformidade jurídica nem substitui auditoria independente.

## Decisão de release

**Estado: PASS — a V4 está tecnicamente e operacionalmente validada.**

Existe uma cópia lógica externa cifrada no Backblaze B2 EU, protegida por Object Lock em modo
`COMPLIANCE`, e essa cópia foi restaurada com sucesso num PostgreSQL 17 isolado e efémero. O
ensaio confirmou migrações, contagens, integridade do arquivo e estado operacional sem utilizar a
base de produção como destino.

A tag `v0.4.0` pode ser criada depois de esta atualização documental passar no CI, ser integrada
em `main` e o smoke final continuar verde. A partir dessa tag, a V5 pode começar sem ocultar
limitações conhecidas da V4.

Esta decisão é técnica e operacional. Não constitui declaração de conformidade jurídica nem
substitui auditoria independente.

## Evidência de produção

| Gate | Estado | Evidência observada |
| --- | --- | --- |
| Baseline integrada | PASS | [Merge da correção de restauro #35](https://github.com/DxMaxi/transparencia-total-open-source/commit/3614b1d57d06640d473a5480eef221705586ce29); deployment Vercel concluído com `success` |
| CI da correção | PASS | [CI 31317774424](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31317774424): frontend, Prisma, build, PostgreSQL, migrações, Ruff, formatação, mypy e pytest aprovados |
| Migrações de produção | PASS | [Operação 31292923666](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31292923666): todas as migrações aplicadas |
| Recolha oficial | PASS com limitação visível | [Operação 31293089510](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293089510): zero fontes falhadas; Entidade para a Transparência em `PARTIAL` com fallback oficial; snapshots `publishable=false` |
| Arquivo de produção | PASS | [Operação 31293164635](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293164635): 32 objetos válidos, zero corrupção e zero falhas |
| Estado operacional | PASS | [Operação 31293212776](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293212776): `HEALTHY`, zero fontes não saudáveis e nenhuma fonte desatualizada |
| Capacidade | PASS | [Verificação 31293247737](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293247737): 32,6 MB físicos, 8,16% do limiar de aviso; estado `OK` |
| Backup externo | PASS | [Backup B2 31313078924](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31313078924): cópia cifrada de 27 966 268 bytes, SHA-256 confirmado e Object Lock `COMPLIANCE` até 9 de setembro de 2026 |
| Restauro isolado | PASS | [Ensaio 31318699132](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31318699132): PostgreSQL 17 efémero, produção não utilizada, 13 migrações, 54 tabelas, 104 737 linhas, arquivo íntegro e estado `HEALTHY` |
| Recuperação medida | PASS | RPO observado de 7 759 segundos; RTO observado de 37 segundos; atestação SHA-256 `ed19814bbc93b3fcd8fff918a2465b52a41b2904e5a23d0ee40bea54a7abd859` |
| Segurança PostgreSQL | PASS | 13 funções de integridade com `search_path` fixo; advisor Supabase sem `WARN` ou `ERROR`; privilégios públicos sem `USAGE`/`CREATE` para `anon` e `authenticated` |
| API pública | PASS | versão `0.4.0`, modo `LIVE` e 5 106 registos aprovados |
| Website público | PASS | smoke repetido após o merge #35: 14 rotas HTTP 200, sete cabeçalhos de segurança e zero mensagens de protótipo ou dados demonstrativos |

`PASS com limitação visível` não transforma ausência de dados em sucesso silencioso. Significa que
a operação terminou sem fonte falhada, preservou prova e publicou o estado incompleto como tal.

## Produção

- A API tem liveness e readiness reais e falha fechada sem a base de dados.
- Migrações, recolhas, revisões e publicações são operações separadas do arranque.
- A recolha diária, o controlo de saúde diário e a verificação semanal do arquivo estão definidos
  em GitHub Actions.
- O limiar de capacidade de 400 MB falha a workflow antes de exigir armazenamento adicional; a
  medição atual é 32 645 120 bytes físicos.
- Nenhuma compra ou serviço de IA foi ativado nesta validação.
- A recuperação externa está ativa e foi comprovada por um ensaio isolado; os valores observados não são uma garantia de disponibilidade futura.
- A implementação Backblaze B2 está descrita em
  [Backup PostgreSQL cifrado no Backblaze B2 EU](BACKUP_BACKBLAZE_B2.md). Código preparado não é
  contado como cópia nem como ensaio.

## Parlamento

- A API pública apresenta 286 políticos, 237 reuniões observadas, 2 100 iniciativas e 2 473
  votações, exclusivamente a partir de fotografias aprovadas.
- Atualizações são versionadas e idempotentes; uma correção cria nova fotografia e não sobrescreve
  a anterior.
- Votos nominais e posições coletivas permanecem separados.
- URL oficial, data de recolha, SHA-256 e versão do coletor ficam associados à prova.
- A fotografia pública aprovada (`parliament-activity-v4`) contém 20 331 posições: todas mantêm
  `actor_type=UNKNOWN` e cinco mantêm também o sentido de voto `UNKNOWN`. Os rótulos textuais
  observados são preservados, mas não são ligados a pessoas ou partidos sem identificador
  inequívoco. A recolha assinala ainda 344 votações sem posições normalizáveis. Isto é uma limitação
  de cobertura, não uma autorização para correspondência aproximada.
- Campos ausentes permanecem vazios ou `UNKNOWN`; ausência não é convertida em incumprimento.
- A publicação exige decisão humana e acrescenta revisão e `AuditEvent`; a ingestão final de
  índices oficiais manteve todos os snapshots privados e `publishable=false`.

## Identificadores protegidos

- Em produção existem zero linhas em `protected_identifier_digests`, zero digests em staging BASE,
  zero candidatos de correspondência e zero contratos publicados.
- Sem `PROTECTED_IDENTIFIER_PEPPER`, o circuito fiscal permanece indisponível e não persiste NIF ou
  NIPC. Quando for autorizado no futuro, aceita apenas HMAC-SHA-256 com pepper estável; nunca texto
  em claro, nunca fuzzy matching e nunca publicação automática.

## Produto público

- Os modos `LIVE`, `EMPTY` e `UNAVAILABLE` são explícitos; não há dados de demonstração no domínio
  oficial.
- Fontes e limitações acompanham os dados e as páginas legais estão publicadas.
- O smoke test confirmou navegação essencial e conteúdo em português de Portugal.
- As listas longas de políticos, reuniões e votações continuam auditáveis, mas a pesquisa, filtros,
  agrupamento temático, paginação orientada ao cidadão e explicadores de consequências pertencem à
  V5. Não são introduzidos no fecho da V4 para ocultar gates operacionais.
- Como nenhuma das 20 331 posições da fotografia atual tem ligação inequívoca a uma pessoa ou
  partido, os perfis individuais não devem fingir um histórico nominal. A V5 pode melhorar a
  ligação apenas com identificadores oficiais exatos e nova revisão humana.

## IA e conteúdo cívico

- `AI_PROVIDER=disabled` é o estado correto da V4 em produção.
- Os serviços atuais apenas geram propostas imediatas; ainda não existe fila persistente de
  rascunhos, revisão editorial autenticada, projeção pública apenas de aprovados, nem registo
  completo de modelo, prompt, âncoras e hashes por geração.
- Por isso a V4 não apresenta “notícias de IA”. IA nunca é fonte e não deve imitar uma redação
  noticiosa sem prova. A primeira entrega V5 deve criar propostas privadas `PENDING`, ligadas a
  fontes oficiais, permitir abstenção, exigir revisão humana e preservar todas as versões.
- O objetivo editorial é explicar factos, escolhas públicas, consequências verificáveis,
  alternativas e incerteza. A plataforma não atribui intenções a partidos, não recomenda voto e
  não classifica intervenientes como favoráveis ou contrários ao progresso de Portugal.

## Prova de recuperação que fechou o gate

A primeira cópia externa comprovada foi produzida pela execução
[31313078924](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31313078924):

- objeto: `database/daily/2026/08/09/transparencia-total-20260809T122221Z-31313078924-1.dump.age`;
- tamanho cifrado: 27 966 268 bytes;
- SHA-256 cifrado: `5255c0fa9a85711d0c0c7f86162376aece2b1d26026e32056916c2234bb41337`;
- SHA-256 canónico do manifesto: `2f954648dfab7c46df474d6b37caacbbdd9070c59ac6c6bcbb74f9fcfec28232`;
- SHA-256 do ficheiro de manifesto: `1daa8e5ea2ccd646b490b238efa978a76e672ce792322e9f0653564458f02729`;
- retenção confirmada: Object Lock `COMPLIANCE` até `2026-09-09T12:22:21Z`.

O ensaio [31318699132](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31318699132)
usou exatamente esse objeto e esses hashes. A atestação não sensível registou:

- `outcome=PASS`;
- `production_target_used=false`;
- destino `ISOLATED_EPHEMERAL_POSTGRESQL`;
- `archive_integrity=PASS`, com 32 objetos;
- `migrations=PASS`, com 13 migrações;
- `table_counts=PASS`, com 54 tabelas e 104 737 linhas;
- `operational_status=HEALTHY`;
- RPO observado de 7 759 segundos e RTO de 37 segundos;
- SHA-256 da atestação `ed19814bbc93b3fcd8fff918a2465b52a41b2904e5a23d0ee40bea54a7abd859`.

A identidade privada `age` foi removida do environment `recovery` depois do ensaio. As
credenciais B2 permanecem separadas: escrita limitada no environment de produção e leitura limitada
no environment de recuperação.

## Condições para iniciar a V5

1. Integrar esta atualização documental depois de CI verde.
2. Repetir o smoke público após a integração.
3. Criar a tag/release `v0.4.0` no commit final de `main`.
4. Manter as limitações V4 visíveis e transportar novas funcionalidades apenas para trabalho V5.

Falhas futuras de backup, saúde ou arquivo devem abrir um incidente operacional; não devem ser
silenciadas nem convertidas em dados atuais.

## Regra de passagem

Todos os gates técnicos e operacionais da V4 têm evidência real. Depois de CI verde, integração
deste fecho e criação da tag `v0.4.0`, a V4 fica congelada e a V5 pode começar. Uma limitação de
cobertura permanece uma limitação documentada; nunca é preenchida por inferência ou dados
demonstrativos.
