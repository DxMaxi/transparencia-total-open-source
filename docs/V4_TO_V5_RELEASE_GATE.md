# Fecho da V4 e entrada na V5

Este documento regista a validação efetivamente executada em produção em 9 de agosto de 2026.
Não é uma declaração de conformidade jurídica nem substitui auditoria independente.

## Decisão de release

**Estado: V4 tecnicamente validada, mas a tag `v0.4.0` e o início da V5 continuam bloqueados por
um único gate operacional: não existe uma cópia de segurança externa com restauro testado.**

O PostgreSQL de produção está num projeto Supabase `ACTIVE_HEALTHY`, em plano Free. O plano foi
confirmado diretamente na configuração da organização; não se presume backup gerido nem
point-in-time recovery. O arquivo interno está íntegro, mas não é um backup se a própria base de
dados for perdida. O estado e o procedimento estão documentados em
[Recuperação da base de dados](DATABASE_RECOVERY.md).

Não criar a tag `v0.4.0`, não anunciar recuperação garantida e não iniciar funcionalidades V5 até
existir uma cópia externa cifrada, com retenção definida, e um ensaio de restauro isolado concluído.

## Evidência de produção

| Gate | Estado | Evidência observada |
| --- | --- | --- |
| Commit de produção | PASS | `3512ba7c0d5d66193437e44b1c18b1b53e676c86`; deployment Vercel `dpl_9vLqGWHxrGFAr3zGcdvKkrT3yC1R`, `READY`, alvo `production` |
| CI | PASS | [CI de `main` 31292844496](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31292844496) concluída com sucesso |
| Migrações | PASS | [Operação 31292923666](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31292923666): migração `20260809043000_v4_pin_database_function_search_paths` aplicada; todas as migrações concluídas |
| Recolha oficial | PASS com limitação visível | [Operação 31293089510](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293089510): zero fontes falhadas; Entidade para a Transparência em `PARTIAL` com fallback para o portal oficial; todos os snapshots `publishable=false` |
| Arquivo | PASS | [Operação 31293164635](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293164635): 32 objetos verificados, 32 válidos, zero corrupção, zero falhas |
| Estado operacional | PASS | [Operação 31293212776](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293212776): `HEALTHY`, limite 36 horas, zero fontes não saudáveis e nenhuma fonte desatualizada |
| Capacidade | PASS | [Verificação 31293247737](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31293247737): 32,6 MB físicos, 8,16% do limiar de aviso de 400 MB; estado `OK` |
| Segurança PostgreSQL | PASS | 13 funções de integridade com `search_path` fixo; advisor Supabase com zero `WARN` e zero `ERROR` de segurança; privilégios públicos sem `USAGE`/`CREATE` para `anon` e `authenticated` |
| Desempenho PostgreSQL | PASS | advisor Supabase com zero `WARN` e zero `ERROR`; avisos informativos de índices permanecem observáveis para reavaliação com carga real |
| API pública | PASS | readiness HTTP 200 com `database_ready=true`; estado público `LIVE`; 5 106 registos aprovados |
| Website público | PASS | homepage, políticos, atividade parlamentar, promessas, metodologia, direito de resposta, privacidade, termos e acessibilidade renderizados sem erro |
| Backup externo e restauro | **BLOCKED** | plano Supabase Free confirmado; nenhuma cópia externa nem ensaio de restauro foram demonstrados nesta validação |

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
- A capacidade de recuperação continua limitada conforme a secção bloqueadora acima.

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

## Critérios para desbloquear a tag e a V5

1. Produzir uma cópia lógica cifrada fora do projeto Supabase de produção, sem expor segredos em
   argumentos, logs ou no repositório.
2. Registar destino, responsável, retenção, data e SHA-256 do artefacto sem guardar a chave junto da
   cópia.
3. Restaurar essa cópia num PostgreSQL isolado e descartável.
4. Aplicar/verificar migrações, executar `verify_v4_archive` e `check_v4_operational_status`, e
   comparar contagens e eventos de auditoria.
5. Registar resultado, RPO e RTO observados. Só então alterar este gate para `PASS`, repetir CI e
   smoke final e criar a tag/release `v0.4.0`.

## Regra de passagem

A V4 só é marcada como concluída após todos os gates, incluindo recuperação, terem evidência real.
A V5 não pode ocultar, adiar ou contornar uma falha pendente da V4.
