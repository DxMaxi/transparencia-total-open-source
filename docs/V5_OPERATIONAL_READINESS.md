# V5.52.1 — diagnóstico operacional seguro e próximo incremento

## Estado observado em 3 de setembro de 2026

A V5.52 está integrada pela [PR #132](https://github.com/DxMaxi/transparencia-total-open-source/pull/132)
em `eb43279`. O [CI de main](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/33679101110)
e o [smoke público](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/33751408883)
passaram. Uma verificação local read-only das 13 páginas públicas também passou; o Investigador
Cívico respondeu 503 com a mensagem neutra esperada. Isto comprova indisponibilidade controlada,
não disponibilidade do módulo, atualização integral dos dados ou conclusão da V5.

O [monitor operacional](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/33749323293)
falhou corretamente porque `PARLIAMENT_ACTIVITY` não está operacional. A
[recolha diária](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/33732422886)
terminou essa etapa em `SCHEMA_MIGRATION_REQUIRED`: falta a porta V5.45 de identidade nominal.
Como esta recusa ocorre antes de escrever um SyncRun, o registo mais recente continua a ser uma
falha de 28-08-2026. Não se deve descrever essa falha histórica como uma nova tentativa, nem
interpretar o sucesso global do workflow como uma recolha parlamentar concluída.

## Correção do diagnóstico

- Recolha e monitor partilham a mesma consulta de prontidão V5.45, sem enfraquecer a recusa.
- O monitor consulta o catálogo e o último SyncRun numa transação `REPEATABLE READ, READ ONLY`,
  com limites de tempo de ligação e consulta. Não altera sequer registos de monitorização.
- `status=SCHEMA_MIGRATION_REQUIRED` identifica o bloqueio atual. `last_run_status`, `observed_at`,
  contagens e `stale` continuam a descrever a última execução registada.
- `blocking_reason`, `required_migration` e `ingestion_readiness` explicam a ação pendente. A
  prontidão indicada cobre apenas os três objetos V5.45 já exigidos pela recolha; não certifica
  todos os schemas, permissões, qualidade da fonte ou possibilidade de publicação.
- O estado global permanece `ATTENTION_REQUIRED` e a saída continua não zero. Uma migração
  presente também não torna um registo antigo ou falhado saudável.
- O monitor seleciona apenas a existência de `error_message`, nunca o seu texto. Os logs novos
  não copiam URLs parametrizados, conteúdo fiscal ou detalhes de ligação de erros anteriores.
  Não apaga a mensagem interna nem limpa retroativamente logs já emitidos.
- Falhas na própria verificação produzem `CHECK_FAILED`, mensagem fechada e saída não zero.
  Esse estado não é aceite como prova operacional num ensaio de restauro.

Não foram alterados workflows, horários, secrets, dados reais ou schemas remotos. Não foi
executada novamente uma recolha. A correção melhora o diagnóstico, não resolve a migração em falta.

## Testes necessários

Os testes unitários cobrem o bloqueio mesmo após sucesso recente, ausência de SyncRun, falhas e
frescura independentes do schema, compatibilidade da política anterior, erros sanitizados e
fecho da ligação. Os testes PostgreSQL confirmam a transação read-only, recusa de escrita,
contagem de SyncRun inalterada e recusa de cada um dos três objetos V5.45 em falta. A simulação de
objetos ausentes ocorre somente numa base local marcada como descartável e termina em rollback.

Validação local do candidato em 03-09-2026: 31 migrações de raiz após o bootstrap Supabase mínimo,
706 testes backend aprovados e 152 contratos frontend aprovados. A primeira repetição da suite
numa base de um ensaio anterior detetou quatro colisões de fixtures; a prova integral foi repetida
numa base nova, sem eliminar o ensaio anterior nem alterar os testes para aceitar duplicados.
Python local 3.12.13 e Node local 26.1.0 não substituem o CI em Python 3.13.15/Node 24.

## Próximo desenvolvimento: V5.53

Publicação e retirada de organizações exigem um processo novo `ORGANISATION_PUBLICATION`, ligado
à versão e aprovação exatas da identidade. O caso `ORGANISATION_IDENTITY` permanece sempre
privado, incluindo depois de uma futura publicação/retirada da projeção autorizada.

Critérios mínimos antes de integração:

1. Nova autorização nasce `PENDING` e exige revisão humana própria do âmbito público.
2. Publicação `ADMIN` com MFA acrescenta fotografia imutável, revisão, auditoria e evento próprio;
   zero partes contratuais, nós do grafo ou relações são criados implicitamente.
3. O identificador público é não fiscal. Referência de um ato não é confundida com identificador
   único da entidade e nomes iguais nunca justificam fusão.
4. HMAC e prova interna não aparecem na API, HTML, auditoria ou fotografia pública.
5. Retirada acrescenta eventos e preserva fontes, versões e direitos de resposta, sem reexpor
   automaticamente campos retirados por privacidade.
6. Projeção pública declara explicitamente a fonte IRN, sem fallback que a atribua ao Parlamento.
7. Concorrência, rollback, RLS, privilégios, correções e vias SQL alternativas ficam testados numa
   base descartável; o grafo existente não é reativado por esta entrega.

O presente patch não implementa a V5.53. Destino separado de staging, autenticação/MFA, avaliação
jurídica, migrações autorizadas e ensaios com dados reais continuam por comprovar. O estado público
atual do repositório também exige reconciliação com a [auditoria de privacidade](V5_RELEASE_PRIVACY_AUDIT.md).
