# Plano de conclusão da V5

## Estado de referência

Este plano fixa o âmbito necessário para concluir a `v0.5.0`. Foi preparado em 13 de agosto de
2026 e atualizado em 20 de agosto de 2026 a partir do código integrado em `main`, da produção
pública e dos princípios de governação do projeto. Não autoriza deploy, migração remota, criação de
utilizadores, alteração de segredos, geração por IA, publicação, retirada ou tratamento de dados
reais.

| Camada | Estado observado |
|---|---|
| Última release fechada | `v0.4.0` |
| Código V5 | V5.1 a V5.18 integradas; staging remoto pendente |
| Frontend público | V5.18 preparado; capacidades sem backend ou esquema pronto ficam fail-closed |
| API pública | `0.5.0-alpha.0`; capacidades anunciadas apenas após prova read-only do esquema |
| Painel editorial | implementado no código, não ativado em produção |
| IA | geração, revisão, publicação e retirada implementadas; esquema remoto ainda não ativado |
| Parlamento | legislatura XVII; API V5 e histórico editorial ainda inativos em produção |
| Perfis | contrato V5.6 preparado; várias áreas sem dados individuais publicáveis |
| Promessómetro | catálogo editorial inicial de 10 compromissos |
| Investigador Cívico | zero contratos e zero relações na projeção pública |
| PWA e alertas | consentimento, revogação e cache opt-in integrados; configuração remota pendente |
| Repositório | privado e licenciado como código disponível para uso não comercial |

## O que significa concluir a V5

A V5 não fica concluída apenas porque o código compila ou porque uma interface existe. Cada módulo
incluído na release tem de satisfazer quatro condições independentes:

1. **Código verificado:** testes, análise estática, compilação e contrato de segurança aprovados.
2. **Operação comprovada:** configuração e percurso completo ensaiados primeiro em staging.
3. **Dados honestos:** cobertura real, fontes, datas, hashes, limitações e revisão visíveis.
4. **Publicação controlada:** apenas projeções aprovadas chegam à API e ao website.

Uma área pode permanecer `UNAVAILABLE` quando a fonte oficial não fornece prova suficiente. Isso é
uma conclusão válida de cobertura, desde que a tentativa, o período e a limitação estejam
documentados. Não se preenche uma lacuna por semelhança de nomes, posição coletiva, notícia ou
inferência de IA.

## Princípios de passagem obrigatórios

- Fonte oficial, URL exato, data de recolha e SHA-256 antes de qualquer facto.
- Arquivo e atestação antes de staging; staging antes de revisão; revisão antes de publicação.
- Correspondências apenas por identificador oficial exato ou HMAC-SHA-256 com pepper privado.
- Nenhum NIF ou NIPC em claro no esquema, logs, ficheiros de revisão ou API.
- Nenhuma posição coletiva convertida em voto, iniciativa ou comportamento individual.
- Ausência de dados apresentada como indisponibilidade, nunca como incumprimento.
- Conteúdo de IA sempre privado em `PENDING` até decisão humana explícita.
- IA com direito a abster-se e proibida de atribuir intenção, culpa ou recomendação de voto.
- Correções, retiradas e direitos de resposta acrescentam versões e eventos; não apagam o passado.
- Nenhuma funcionalidade de recolha, revisão ou publicação é ativada implicitamente por um deploy.

## Sequência de entregas

### 1. Estabilização pública e gate de release

Objetivo: retirar ambiguidades conhecidas da versão pública e criar uma definição auditável de
conclusão.

Critérios de saída:

- paginação parlamentar não apresenta um total aproximado como se fosse exato;
- sitemap inclui os perfis políticos efetivamente publicados;
- páginas públicas e perfis têm URL canónica adequada;
- perfis inexistentes mantêm metadados de 404 e `noindex`;
- Node.js está fixado na versão principal usada pelo CI e pela produção;
- README, plano e checklist refletem o estado realmente integrado;
- testes de deployment cobrem estes contratos.

O diretório deixa de enviar todos os cartões para cada cidadão. A paginação progressiva, o total
exato condicionado e a compatibilidade temporária estão definidos em
[V5.9 — diretório político paginado e auditável](V5_POLITICIAN_DIRECTORY.md).

### 2. Ativação editorial em staging

Objetivo: comprovar a fundação V5.1 a V5.4 sem acesso de escrita à produção.

Critérios de saída:

- CI aplica as migrações num PostgreSQL 17 descartável com `auth.users`, `anon` e `authenticated`
  presentes antes da migração, exercitando o caminho específico do Supabase;
- migrações V5 aplicadas numa base descartável e depois em staging;
- Supabase Auth configurado com signing key assimétrica, URLs exatos e sem registo público;
- conta `ADMIN` de ensaio criada por convite e ligada a `staff_profiles`;
- MFA/TOTP `aal2` obrigatório e sessão `aal1` recusada;
- RLS e ausência de privilégios para `PUBLIC`, `anon` e `authenticated` verificadas;
- percurso `PENDING → IN_REVIEW → APPROVED` comprovado sem alteração da projeção pública;
- publicação e retirada parlamentares comprovadas em PostgreSQL descartável ou staging;
- correção cria nova versão e regressa a `PENDING` sem alterar o histórico.

O procedimento e a separação entre prova automática, inspeção read-only e controlos manuais estão
definidos em [V5.8 — prontidão editorial para staging](V5_EDITORIAL_STAGING_READINESS.md).
O reforço dos privilégios futuros e a ordem das autorizações seguintes estão definidos em
[V5.10 — gate de ativação editorial em staging](V5_EDITORIAL_STAGING_ACTIVATION.md).
O destino, as autorizações independentes, as condições de paragem e o pacote de evidência estão
definidos em
[V5.11 — plano de execução editorial em staging](V5_EDITORIAL_STAGING_EXECUTION_PLAN.md).
O workflow manual, as confirmações específicas e a validação inequívoca do destino estão integrados
em [V5.12 — fundação do workflow editorial de staging](V5_STAGING_WORKFLOW_FOUNDATION.md). Esta
fundação não configura nem consulta o Supabase e não autoriza a execução do workflow.

### 3. Backend V5 e migrações de produção

Objetivo: alinhar frontend e API sem promover qualquer dado por efeito do deployment.

Critérios de saída:

- backup cifrado recente e inventário anterior à migração disponíveis;
- migrações V5 aplicadas por uma operação separada e autorizada;
- API V5 publicada com liveness, readiness e compatibilidade V4;
- CORS, autenticação, limites e logs não sensíveis verificados;
- `/editorial/session`, explorador parlamentar e histórico respondem com o contrato esperado;
- painel continua fechado sem conta ativa e MFA;
- nenhuma linha pública muda apenas por aplicar migrações ou reiniciar serviços;
- novo backup restaurado num PostgreSQL 17 isolado.

### 4. Parlamento completo dentro da cobertura declarada

Objetivo: usar o novo circuito editorial e alargar o arquivo histórico sem inventar cobertura.

Critérios de saída:

- fotografia `parliament-activity-v5` recolhida e atestada;
- propostas distintas para atividade e votações entram em `PENDING`;
- diferenças por `source_id` oficial são revistas;
- os dois âmbitos são publicados apenas após decisão `ADMIN` com MFA;
- pesquisa, filtros, total exato, paginação e histórico funcionam na API V5;
- legislaturas anteriores disponíveis são carregadas por plano de backfill versionado;
- matriz pública identifica legislatura, período, tipo de registo e lacunas;
- títulos enriquecidos dependem de uma ligação oficial inequívoca;
- temas permanecem indisponíveis até existir taxonomia oficial ou decisão humana versionada;
- votações sem posições normalizáveis e sentidos `UNKNOWN` continuam explícitos.

### 5. Perfis políticos com portas independentes

Objetivo: completar a cobertura que as fontes permitem sem construir biografias por inferência.

Critérios de saída:

- mandatos têm datas oficiais, fonte arquivada e revisão `MANDATE` própria;
- cargos, círculo e observações parlamentares distinguem facto observado de período jurídico;
- presenças indicam período observado e dependem de mandato revisto;
- autoria de iniciativas exige relação individual por identificador oficial;
- votos do perfil são nominais, `PERSON` e ligados por `people.source_id` exato;
- declarações individuais exigem fonte EPT, arquivo e confirmação jurídica explícita;
- o portal geral da EPT permanece apenas uma porta de pesquisa;
- cada área mostra `AVAILABLE`, `PARTIAL` ou `UNAVAILABLE` com fundamento e período.

### 6. Promessómetro do Programa do XXV Governo

Objetivo: substituir a amostra inicial por um catálogo versionado de compromissos identificáveis.

Critérios de saída:

- todos os compromissos individualizáveis seguem critérios editoriais publicados;
- cada compromisso conserva página ou âncora, URL, data e SHA-256 do programa;
- diplomas, orçamento, regulamentação e execução oficial entram como provas separadas;
- estados limitam-se a `UNVERIFIED`, `NOT_STARTED`, `IN_PROGRESS`, `PARTIAL` e `FULFILLED`;
- anúncio, aprovação jurídica, entrada em vigor, execução e resultado material são distintos;
- cada alteração de estado acrescenta revisão, fundamento e evento temporal;
- filtros por ministério, área, estado e data usam apenas campos revistos.

### 7. Investigador Cívico

Objetivo: publicar contratos e relações verificáveis, nunca suspeitas automáticas.

Critérios de saída:

- lotes BASE completos são arquivados, atestados e validados em staging;
- promoção para `PublicContract` exige revisão explícita;
- pessoas e organizações têm prova oficial própria;
- candidatos de correspondência ficam privados em `PENDING_REVIEW`;
- identificadores protegidos usam apenas HMAC-SHA-256 com pepper estável;
- cada relação exige os dois nós publicados, tipo, datas, fonte e revisão;
- grafo público explica que uma ligação não prova conflito, benefício ou ilícito;
- direito de resposta e retirada append-only abrangem os registos publicados;
- AIPD e revisão jurídica aplicáveis estão concluídas antes de relações pessoais reais.

### 8. Circuito responsável de IA

Objetivo: publicar explicações cívicas úteis sem transformar o modelo em fonte ou decisor.

Critérios de saída:

- geração disponível apenas a staff autenticado e com limites de custo;
- entrada limitada a documentos oficiais arquivados e factos previamente revistos;
- cada geração persiste fonte, hashes, modelo, fornecedor, instruções, versão e truncagem;
- cada proposta nasce privada, com origem `AI` e estado `PENDING`;
- âncoras inválidas e afirmações sem suporte bloqueiam aprovação;
- abstenção por dados insuficientes é testada e apresentada corretamente;
- aprovação, rejeição, correção e nova geração preservam todas as versões;
- projeção pública lê apenas versões aprovadas e rotuladas como auxiliadas por IA;
- cenários usam cálculos determinísticos versionados e apresentam pressupostos e incerteza;
- boletins incluem critérios, documentos incluídos e excluídos e ligações às provas;
- testes adversariais cobrem prompt injection, omissões, datas, exceções e enviesamento.

### 9. Pesquisa global, comparação, PWA e alertas

Objetivo: tornar o conjunto publicado compreensível e opcionalmente acompanhável.

Critérios de saída:

- pesquisa global consulta exclusivamente projeções públicas aprovadas;
- filtros e paginação têm semântica consistente entre módulos;
- comparações só usam períodos, universos e indicadores realmente comparáveis;
- diretório de políticos deixa de enviar todos os cartões quando a escala o desaconselhar;
- acessibilidade WCAG 2.2 AA é avaliada por auditoria externa ou método público equivalente;
- PWA é instalada apenas por escolha explícita;
- notificações só são pedidas após consentimento informado;
- preferências, cancelamento e eliminação da subscrição são acessíveis;
- nenhum alerta é criado a partir de conteúdo privado ou não revisto.

A pesquisa federada por secções, a prova visível em cada resultado, o gate de capacidade da API e
o orçamento móvel repetível estão definidos em
[V5.18 — pesquisa global publicada e orçamento móvel](V5_GLOBAL_SEARCH_AND_PERFORMANCE.md).
Comparações entre universos permanecem fora da pesquisa e continuam pendentes até existir uma
metodologia que prove comparabilidade.

### 10. Fontes adicionais e cobertura histórica

Objetivo: transformar coletores privados em módulos públicos com âmbito limitado e verificável.

Para DRE, BASE, EPT, Tribunal de Contas, Parlamento Europeu, SNS e cada fonte municipal incluída:

- âmbito, licença, período, território e identificador estável documentados;
- bytes arquivados, normalização versionada e testes por fixture;
- proposta privada e revisão específicas do domínio;
- projeção pública fail-closed;
- frequência, última recolha, atraso e falhas visíveis;
- ausência de cobertura nunca apresentada como ausência de factos;
- fontes municipais identificam explicitamente os territórios abrangidos.

## Gate de release `v0.5.0`

A release só pode ser criada quando a checklist complementar estiver integralmente resolvida ou
quando uma limitação tiver sido formalmente retirada do âmbito da V5, com fundamento público e sem
alterar os princípios acima. Não se transforma uma tarefa por fazer em `PASS` apenas porque o
frontend consegue esconder a funcionalidade.

O fecho exige, no mínimo:

- CI integral verde com PostgreSQL descartável;
- frontend e API na mesma versão compatível;
- smoke desktop e móvel das rotas públicas e privadas;
- zero erros críticos de execução conhecidos;
- verificação de segurança, acessibilidade e desempenho;
- inventário de cobertura e limitações publicado;
- AIPD e revisão jurídica nas áreas que tratem dados de maior risco;
- backup pós-migração e restauro isolado comprovado;
- pesquisa de segredos em toda a história antes de tornar o repositório público;
- documentação, changelog, tag `v0.5.0` e atestação final de release.

Consulte a lista operacional em [Checklist de conclusão da V5](V5_RELEASE_CHECKLIST.md).
