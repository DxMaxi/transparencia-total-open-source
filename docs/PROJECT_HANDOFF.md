# PROJECT HANDOFF — Transparência Total / Fator Cívico

Atualizado em: **2026-08-26**

Este documento existe para permitir continuidade segura entre sessões de trabalho, colaboradores e chats sem depender de memória externa ao repositório.

> **Regra principal:** antes de alterar código, ler `docs/V5_RELEASE_CHECKLIST.md`, a issue #58 e a issue #76. Depois confirmar o estado real de `main`, porque este handoff é um checkpoint e pode existir trabalho posterior.

## 1. Objetivo do projeto

O Transparência Total / Fator Cívico é uma plataforma cívica para apresentar informação política e institucional verificável com fonte oficial, cobertura explícita, histórico e regras de publicação prudentes.

A V5 deve terminar como uma plataforma simultaneamente:

- tecnicamente robusta;
- auditável e verificável;
- segura e juridicamente prudente;
- acessível e responsiva;
- simples de utilizar por um cidadão comum;
- incapaz de transformar indisponibilidade técnica em afirmações factuais falsas.

## 2. Arquitetura atual

### Frontend

- Next.js 16 / React 19 / TypeScript
- Vercel em produção
- PWA com service worker explícito
- Playwright para testes E2E públicos
- Prisma no ecossistema da aplicação

### Backend

- FastAPI
- PostgreSQL / asyncpg
- Render em produção
- Supabase previsto/usado para autenticação editorial V5
- separação entre recolha, staging, revisão, aprovação e publicação

### URLs públicas

- Site: `https://www.transparenciatotal.pt`
- API: `https://transparencia-total-api.onrender.com`

Nunca adicionar neste documento segredos, chaves, `.env`, dumps, tokens, passwords ou dados pessoais não destinados a publicação.

## 3. Versões de runtime relevantes

- `package.json` exige **Node 24.x**.
- CI usa Node 24.
- O ambiente local oficial deve respeitar Node 24 para evitar resultados não reprodutíveis.
- O backend suporta exclusivamente Python `>=3.13,<3.14`.
- [`.python-version`](../.python-version) é a fonte canónica da revisão exata, atualmente
  `3.13.15`; os workflows GitHub leem esse ficheiro e Render e Docker têm de declarar a mesma
  revisão.
- `backend/scripts/check_python_runtime_policy.py` verifica a paridade e, no CI, confirma também o
  intérprete instalado. Não fechar a ocorrência P2.2 da issue #76 sem CI verde e verificação
  read-only do deployment Render correspondente.

## 4. Estado da V5

Issue canónica: **#58 — [V5] Plano de conclusão da versão 5**.

Frentes ainda pertencentes à V5:

- #52 — Supabase e autenticação em staging
- #53 — circuito editorial e Parlamento em staging
- #56 — perfis, Promessómetro e cobertura histórica
- #57 — Investigador Cívico e IA responsável
- #55 — pesquisa, comparação, desempenho e alertas PWA
- #54 — migração, segurança, recuperação e release de produção
- #76 — bugs, riscos e dívida técnica encontrados na auditoria profunda de 2026-08-15

Desde esse checkpoint, a V5.13–V5.15 fechou o circuito privado, a revisão e a publicação específica
de explicações DRE com IA. A capacidade pública é anunciada apenas quando o esquema real a suporta;
sem essa prova, API e frontend apresentam indisponibilidade controlada. A V5.16–V5.18 endureceu as
escritas públicas, consentimento e revogação push, cache PWA, acessibilidade, E2E, CSP, pesquisa
global e desempenho móvel. A V5.19 acrescentou a auditoria sanitizada de dados e história Git; um
contacto pessoal permanece apenas em diffs históricos e bloqueia a visibilidade pública até haver
decisão própria. A V5.20 substitui os estados públicos antigos do Promessómetro pelo vocabulário
aprovado e mantém qualquer valor legado fora da projeção até nova revisão humana. A V5.21 expõe a
última cobertura parlamentar publicada por legislatura, âmbito, período e fotografia, sempre com
fonte e hashes, e fixa o preenchimento histórico como uma fila editorial separada. Um recurso num
catálogo oficial continua a ser apenas candidato até arquivo, revisão e publicação. Estes avanços
não equivalem à execução dos gates de staging ou produção ainda abertos. A V5.22 acrescenta um
coletor versionado para arquivar os três catálogos parlamentares por legislatura e inventariar
apenas etiquetas e URLs oficiais exatas como `PENDING_INSPECTION`, sem descarregar os recursos,
criar casos editoriais ou publicar. A V5.23 acrescenta o manifesto privado de uma única pasta:
revalida a fotografia V5.22 e a respetiva atestação, arquiva o HTML e aceita apenas XML/JSON
inequívocos como `PENDING_DOWNLOAD`, ainda sem descarregar os ficheiros ou criar revisão. A V5.24
seleciona exatamente um desses recursos, repete a prova completa e arquiva os bytes com limite de
tamanho como `ARCHIVED_UNPARSED`, sem normalizar registos nem entrar no circuito editorial. A V5.25
normaliza apenas o JSON de iniciativas já arquivado, exige `source_id` oficial e URL parlamentar,
recalcula o resultado antes de persistir e conserva `NOT_ASSERTED`, sem criar revisão ou publicação.
A V5.26 deriva dos mesmos bytes uma fotografia privada separada de votações, recusa factos
contraditórios para o mesmo ID, mantém posições textuais como `UNKNOWN` e volta a provar toda a
cadeia antes da escrita; continua sem criar revisão, publicação ou relações por nome.
A V5.27 interpreta separadamente o recurso de atividade dos deputados já arquivado: exige `DepId`,
preserva `GpId`, `DepCPId` e intervalos oficiais de situação, grupo e cargo numa fotografia
append-only própria, não normaliza contactos e não cria pessoas, mandatos, revisão ou publicação.
A V5.28 liga cada observação a um caso privado `POLITICIAN_PROFILE` por `DepId` exato. O painel
reprova fonte, arquivo e manifesto, recebe do browser apenas o identificador e confirmações, conserva
anomalias de datas e não cria pessoa, mandato, revisão pública ou publicação mesmo após aprovação.
A V5.29 acrescenta a inspeção read-only da fotografia inteira: todas as versões atuais têm de estar
aprovadas, coincidir com a reconstrução determinística e conservar a decisão e a fonte exatas. Uma
revisão pública V4 exige reconciliação explícita. O hash de prontidão não publica nem autoriza uma
ação de escrita.
A V5.30 acrescenta a operação de publicação integral, separada e exclusivamente `ADMIN` com MFA.
Depois de repetir hashes, manifesto e aprovações, liga identidades apenas por `DepId` exato e
acrescenta pessoas, observações, revisões, auditorias, decisões e eventos numa única transação. Não
cria mandatos ou filiações e não foi executada sobre staging ou produção. A V5.31 acrescenta a
retirada não seletiva da fotografia completa: recalcula a prova de cada perfil e da publicação,
simula o recuo público, acrescenta revisões, auditorias, decisões e eventos negativos numa única
transação e preserva pessoas, fontes, observações e versões. Não foi executada sobre staging ou
produção. A republicação comprovada a partir de uma nova fotografia imutável era o gate seguinte.

A V5.32 fecha esse gate numa base PostgreSQL descartável: depois de publicar e retirar a primeira
fotografia, cria outra fonte, fotografia, observação, processo e versão; reutiliza a pessoa apenas
pelo mesmo `DepId` exato e publica a nova fotografia. A versão antiga permanece `WITHDRAWN`, os seus
eventos `PUBLISH` e `WITHDRAW` permanecem e a consulta passa para o novo SHA-256. Nenhuma operação
foi executada sobre staging ou produção.

A V5.33 inicia a porta independente dos mandatos. O painel privado lista cada `DepSituacao` por
hash canónico e só admite proposta quando a identidade já está publicada pelo mesmo `DepId`, o
círculo tem identificador oficial, as datas são coerentes e fonte, arquivo e manifesto coincidem.
O caso fica `PENDING`; mesmo depois de aprovação são criados zero `Mandate`, zero revisões públicas
e zero eventos de publicação. A publicação e a retirada imutável são o gate seguinte.

A V5.34 prepara a publicação individual do mandato, exclusiva de `ADMIN` com MFA. Uma migração
compatível acrescenta a observação oficial, a posição do intervalo e o SHA-256 a cada nova linha,
com chave estrangeira, unicidade e histórico append-only. A operação acrescenta `Mandate`, revisão
`MANDATE`, `AuditEvent`, decisão e evento numa só transação e cria zero pessoas ou filiações. O
teste de integração usa apenas PostgreSQL descartável; staging e produção permanecem intactos. A
ativação real permanecia bloqueada até a retirada imutável V5.35 ficar provada.

A V5.35 fecha esse ciclo no código e numa base PostgreSQL descartável. O preview privado reconstrói
a fonte, o intervalo, a versão, a revisão positiva, a auditoria e o evento `PUBLISH`; a ação `ADMIN`
com MFA acrescenta revisão negativa, `AuditEvent`, decisão e evento `WITHDRAW` numa só transação.
O mandato, a pessoa, a pertença parlamentar, a fonte e a publicação original ficam intactos. A
consulta pública deixa de selecionar apenas esse mandato pela revisão mais recente. Staging e
produção permanecem intactos e a ativação real continua dependente dos gates operacionais.

A V5.36 inicia a porta independente dos cargos parlamentares observados. O painel expande cada
`DepCargo` apenas dentro da área autenticada e exige `DepId`, `CarId`, círculo, período, fonte,
arquivo e manifesto coincidentes. O browser envia somente a observação, o SHA-256 do período e
confirmações fechadas; o servidor reconstrói a proposta `PARLIAMENT_OFFICE_PERIOD`. Aprovar cria
zero cargos, mandatos, revisões públicas ou eventos. A publicação e a retirada de cargos continuam
pendentes e terão de ser portas append-only próprias antes de qualquer ensaio operacional.

A V5.37 acrescenta a publicação específica desses cargos sem os converter em mandatos. Um
`ADMIN` com MFA volta a provar versão, fonte, arquivo, `DepId`, `CarId`, círculo e período antes de
acrescentar o cargo, a revisão `PARLIAMENT_OFFICE`, a auditoria, a decisão e o evento `PUBLISH`
numa única transação. A consulta pública exige que as revisões mais recentes da identidade e do
cargo continuem positivas e apresenta o cargo numa secção própria com fonte, data e SHA-256. A
V5.37 não executa migrações ou publicações reais.

A V5.38 fecha a retirada append-only deste domínio. O preview privado reconstrói a fonte, o
`DepId`, o `CarId`, o círculo, o período, a versão, a revisão positiva, a auditoria e o evento
`PUBLISH`; a ação `ADMIN` com MFA acrescenta revisão negativa, `AuditEvent`, decisão e evento
`WITHDRAW` numa transação. O cargo, a pessoa, os mandatos, a pertença parlamentar, a fonte e a
publicação original ficam intactos. A consulta pública deixa de selecionar apenas esse cargo.
Staging e produção permanecem intactos e a ativação continua dependente dos gates operacionais.

A V5.39 inicia o domínio individual das presenças sem confundir assiduidade numa reunião com mérito
ou incumprimento. Recolhe apenas uma página oficial de detalhe com BID da reunião, arquiva os bytes
e cria uma fotografia append-only com todos os BID individuais e os estados literais. A proposta
editorial é sempre da reunião inteira, nasce `PENDING`, não usa correspondência por nome e cria
zero sessões ou presenças públicas. Estados desconhecidos, identidades sem revisão ou ausência de
um mandato revisto para a data ficam visíveis como bloqueios de uma futura publicação. Nenhuma
operação de staging ou produção foi executada.

A melhoria de UX iniciada em agosto de 2026 faz parte da estabilização/conclusão da **V5**. Não deve ser tratada como início de uma V6 nem como autorização para reescrever o projeto.

## 5. Baseline técnico conhecido

Checkpoint histórico validado antes da auditoria profunda:

- commit `11bc16f` — `test: add public E2E audit coverage`
- commit `11bf420` — `fix: avoid false zero counts when public API is unavailable`
- suite `npm.cmd run test:frontend`: **64 testes, 64 pass, 0 fail** no checkpoint `11bf420`
- deployment Vercel desse commit confirmado com sucesso
- `npm audit --omit=dev` tinha devolvido **0 vulnerabilidades** na auditoria anterior
- pesquisa de segredos não encontrou credenciais reais conhecidas; repetir antes do release final
- auditoria V5.19 no commit `9f46c2f`: 89 contratos frontend e 355 testes backend aprovados; cinco
  alertas de história revistos como falsos positivos e um bloqueio de privacidade histórico
  documentado em `docs/V5_RELEASE_PRIVACY_AUDIT.md`

Este baseline não substitui a verificação do `HEAD` atual.

Baseline ao entrar na V5.16: `b6eda1a`, depois da integração das propostas, revisão e publicação
responsável de IA e da porta de prontidão de esquema. O número exato de testes deve ser recolhido
novamente no candidato final, não copiado deste handoff.

## 6. Correção importante já aplicada

Foi corrigido um erro de semântica pública: quando a API ficava temporariamente indisponível, a homepage apresentava falsamente `0 registos aprovados` e fontes como `Sem recolha`.

Com a correção `11bf420`:

- indisponibilidade temporária deixa de ser apresentada como zero;
- os contadores usam `—` quando não existe informação válida;
- as fontes aparecem como `Indisponível`;
- existe teste de regressão no contrato público da UI.

**Invariante:** nunca voltar a representar uma falha de API como ausência factual de dados.

## 7. Auditoria aprofundada de 2026-08-15

Documento detalhado: `docs/AUDIT_2026-08-15.md`

Issue de acompanhamento: **#76**.

Regra de gate:

> A V5 não deve ser fechada enquanto existir qualquer P1 confirmado aberto.

Os achados de maior prioridade incluem:

- dependências Python divergentes entre `pyproject.toml` e `requirements.txt`;
- risco de um perfil político temporariamente indisponível ser tratado como 404 real;
- public smoke não provar necessariamente o deployment do commit que o disparou;
- startup da API depender diretamente da disponibilidade do PostgreSQL;
- Playwright existir mas ainda não correr no CI;
- falta de observabilidade suficiente nas falhas frontend→API;
- necessidade de rever timeout/retry/stale data sem mascarar erros reais.

Consultar #76 para estado atualizado de cada item.

## 8. Comandos de validação relevantes

Em Windows PowerShell usar `npm.cmd` quando necessário.

### Frontend / contratos

```powershell
npm.cmd run test:frontend
```

### Qualidade frontend completa

```powershell
npm.cmd run quality
```

### Build Next usado no CI relevante

```powershell
npm.cmd run build:next
```

### Smoke público

```powershell
npm.cmd run smoke:public
```

### Backend

No ambiente Python correto:

```text
ruff check backend
ruff format --check backend
mypy --config-file backend/pyproject.toml backend/app
pytest backend
```

O CI executa os E2E Playwright contra o artefacto Next local. O workflow `Public smoke` repete-os no
browser real depois de um deployment Production bem-sucedido; ambos têm de ficar verdes no
candidato final.

## 9. Regras de dados e publicação que não podem ser quebradas

- Não substituir dados oficiais indisponíveis por exemplos fictícios.
- Não inventar relações entre pessoas, empresas, contratos ou entidades.
- Não transformar coincidência de nomes em identidade.
- Não criar acusações, scores reputacionais ou conclusões políticas automáticas.
- Preservar URL/fonte oficial, proveniência e cobertura quando disponíveis.
- Distinguir sempre recolha, normalização, evidência, revisão, aprovação e publicação.
- Aprovação editorial não deve publicar automaticamente.
- Falha de endpoint não equivale a `0`, `não existe`, `sem recolha` ou 404.
- Manter direito de resposta, histórico e limitações públicas.
- Staging nunca prova uma condição de produção.
- Não colocar segredos, dados privados ou dumps em commits, issues ou logs públicos.

## 10. UX V5

Problema identificado: a plataforma é tecnicamente rigorosa mas ainda apresenta demasiada complexidade interna ao cidadão.

Direção aprovada para a revisão UX:

- rever página a página, começando pela homepage;
- mostrar primeiro a tarefa que o cidadão quer realizar;
- usar progressive disclosure para metodologia, cobertura e limitações;
- manter toda a rastreabilidade, mas não obrigar o visitante a compreendê-la antes de pesquisar;
- simplificar linguagem pública sem simplificar as regras internas;
- testar sempre desktop, mobile, teclado e estados de indisponibilidade.

Antes de alterar uma página, identificar:

1. objetivo principal do utilizador;
2. fonte de confusão atual;
3. hierarquia de informação proposta;
4. impacto em acessibilidade e estados de erro;
5. testes de regressão necessários.

## 11. Processo de trabalho recomendado

Para cada correção:

1. confirmar `HEAD` e working tree;
2. reproduzir ou provar o problema;
3. corrigir o mínimo necessário;
4. adicionar teste que falharia antes da correção;
5. correr testes direcionados;
6. correr a suite/gate relevante;
7. rever `git diff` e `git status`;
8. commit com mensagem específica;
9. push;
10. confirmar CI/deployment/smoke aplicável;
11. atualizar a issue correspondente com evidência, sem segredos.

Evitar grandes alterações simultâneas. Os P1 da #76 devem ser tratados um de cada vez.

## 12. O que um novo chat deve ler primeiro

Ordem recomendada:

1. `docs/PROJECT_HANDOFF.md`
2. `docs/V5_RELEASE_CHECKLIST.md`
3. issue #58
4. issue #76
5. a issue específica da tarefa (#52–#57)
6. `docs/AUDIT_2026-08-15.md` quando o trabalho tocar em resiliência, CI, segurança ou release

Depois deve inspecionar o código atual e não assumir que um documento de handoff substitui o estado real do repositório.
