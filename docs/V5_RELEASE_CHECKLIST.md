# Checklist de conclusão da V5

Esta checklist operacionaliza o [Plano de conclusão da V5](V5_RELEASE_PLAN.md). Um item marcado
significa que existe código ou evidência já verificada; não significa autorização para executar a
mesma operação noutro ambiente. Deploy, migração, segredos, Supabase, utilizadores e dados reais
continuam a exigir autorizações separadas.

## A. Baseline integrada

- [x] Licença PolyForm Noncommercial para o software V5 documentada.
- [x] Licença do conteúdo editorial e direitos das fontes delimitados.
- [x] V5.1 — fundação editorial privada integrada.
- [x] V5.2 — adaptador parlamentar privado integrado.
- [x] V5.3 — publicação parlamentar por âmbito integrada.
- [x] V5.4 — retirada parlamentar append-only integrada.
- [x] V5.5 e V5.5.1 — explorador público e compatibilidade integrada.
- [x] V5.6 — contrato de perfis auditáveis integrado.
- [x] V5.7 — estabilização e gate público integrados.
- [x] V5.8 — prontidão editorial para staging integrada.
- [x] V5.9 — diretório político paginado e auditável integrado.
- [x] V5.10 — blindagem dos privilégios futuros e do inspetor read-only integrada.
- [x] CI da integração V5.10 aprovado com PostgreSQL 17.
- [x] Frontend V5.10 publicado em modo de compatibilidade fail-closed.
- [x] README e documentação refletem a integração e publicação fail-closed da V5.10.
- [x] V5.11 — plano operacional revisto e integrado antes de qualquer operação remota em staging.
- [x] V5.12 — workflow segregado de staging revisto e integrado, ainda sem qualquer execução.
- [x] V5.13 — propostas privadas de IA com arquivo atestado e abstenção integradas.
- [x] V5.14 — revisão editorial privada de IA com MFA e histórico append-only integrada.
- [x] V5.15 — publicação e retirada específicas de explicações de IA integradas.
- [x] Capacidade pública de IA só é anunciada depois de a prontidão real do esquema ser provada.
- [x] V5.16 — antiabuso, revogação push, cache allowlist, acessibilidade e E2E local integrados.
- [x] V5.17 — CSP privada por pedido e gate automático WCAG A/AA integrados.
- [x] V5.18 — pesquisa global publicada e orçamento móvel repetível integrados.
- [x] V5.19 — auditoria sanitizada de dados, segredos e privacidade da história integrada.
- [x] V5.20 — vocabulário editorial seguro do Promessómetro integrado.
- [x] V5.21 — matriz de cobertura parlamentar e plano de preenchimento histórico integrados.
- [x] V5.22 — catálogo privado e versionado de fontes parlamentares por legislatura integrado.
- [x] V5.23 — manifesto privado de XML/JSON ligado a catálogo pai exato e atestado integrado.
- [x] V5.24 — arquivo limitado de um recurso exato, ainda não interpretado nem publicável, integrado.
- [x] V5.25 — primeira normalização histórica privada de iniciativas, derivável dos bytes, integrada.
- [x] V5.26 — normalização histórica privada de votações, com IDs exatos e atores desconhecidos
  preservados, integrada.
- [x] V5.27 — observações privadas e versionadas de deputados por `DepId`, com contactos excluídos
  e datas oficiais não convertidas automaticamente em mandatos, integrada.
- [x] V5.28 — observações por `DepId` entram apenas em casos privados `POLITICIAN_PROFILE` em
  `PENDING`, sem criar pessoa, mandato, revisão pública ou publicação.
- [x] V5.29 — porta read-only exige a fotografia inteira, todas as versões `APPROVED`, prova
  reconstruída e reconciliação explícita de revisões V4 antes de uma futura publicação de perfis.
- [x] V5.30 — publicação transacional da fotografia completa exige `ADMIN` com MFA, repete hashes e
  contagens, liga apenas por `DepId` exato e acrescenta todo o histórico ou recua tudo.
- [x] V5.31 — retirada não seletiva da fotografia de perfis acrescenta revisões, auditorias,
  decisões e eventos em bloco, calcula o efeito público e não apaga pessoas nem histórico.
- [x] V5.32 — republicação exige uma nova fonte e fotografia imutáveis, reutiliza a pessoa apenas por
  `DepId` exato e mantém a versão retirada definitivamente inativa.
- [x] V5.33 — intervalos oficiais entram numa fila privada própria por hash, identidade publicada e
  `DepId` exato; aprovação continua sem criar mandato, revisão pública ou evento de publicação.
- [x] V5.34 — publicação transacional ADMIN+MFA acrescenta um mandato por intervalo exato, revisão
  `MANDATE`, auditoria, decisão e evento, com constraints e histórico append-only.
- [x] V5.35 — retirada transacional e imutável do mandato acrescenta revisão negativa, auditoria,
  decisão e evento, preserva a linha e a publicação originais e recua tudo perante divergência.
- [x] V5.36 — cada `DepCargo` com DepId, CarId, círculo, período, fonte e SHA-256 exatos pode criar
  apenas uma proposta privada `PENDING`; aprovação ainda não cria cargo, mandato ou publicação.
- [x] V5.37 — publicação transacional ADMIN+MFA acrescenta um cargo numa estrutura própria,
  revisão `PARLIAMENT_OFFICE`, auditoria, decisão e evento append-only; cria zero mandatos e zero
  filiações e a ficha pública mantém os dois conceitos separados.
- [x] V5.38 — retirada transacional e imutável do cargo acrescenta revisão negativa, auditoria,
  decisão e evento, preserva cargo, identidade, mandatos, fonte e publicação e recua tudo perante
  qualquer divergência.
- [x] V5.39 — presenças oficiais por reunião entram numa fotografia privada integral e append-only,
  com BID exato, fonte arquivada e proposta `PENDING`; aprovação cria zero sessões ou presenças
  públicas e uma falta nunca é convertida automaticamente em incumprimento.
- [x] V5.40 — publicação transacional ADMIN+MFA acrescenta a reunião integral, todas as linhas,
  revisão própria, auditoria, decisão e evento numa única transação; cada BID exige exatamente um
  mandato revisto e a ficha pública conserva a fonte de cada reunião.
- [x] V5.41 — retirada transacional e imutável acrescenta revisão negativa, auditoria, decisão e
  evento para a reunião inteira; sessão, presenças, identidades, mandatos e publicação original
  permanecem e não existe retirada seletiva.
- [x] Existe um [conjunto de issues de conclusão](https://github.com/DxMaxi/transparencia-total-open-source/issues/58) para todos os itens ainda abertos.

## B. Estabilização pública

- [x] Paginação sem denominador quando o total não é exato.
- [x] Paginação com `Página N de M` apenas quando a API fornece total exato.
- [x] Sitemap inclui todas as rotas de perfis publicadas e nenhuma ficha privada.
- [x] Todas as páginas públicas principais têm URL canónica.
- [x] Perfil inexistente devolve 404, título correto e `noindex`.
- [x] Diretório dos políticos medido e preparado para paginação progressiva.
- [x] Versão principal do Node fixada e igual no CI e no deployment.
- [x] Testes de contrato impedem regressões destes comportamentos.
- [x] Estado público distingue fontes recentes, parciais e desatualizadas pelo limite operacional.

## C. Base de dados e autenticação em staging

- [x] Migrações V5 aplicadas numa base PostgreSQL 17 descartável com forma mínima do Supabase.
- [x] CI confirma a FK `auth.users`, RLS, triggers, `search_path` e ausência de privilégios browser.
- [x] Workflow manual de staging integrado com confirmações por operação e recusa do destino de
  produção.
- [ ] Inventário de esquema, triggers, RLS e privilégios revisto no projeto de staging confirmado.
- [x] CI confirma que defaults globais e específicos de `public` não reabrem objetos futuros aos
  papéis browser.
- [ ] Migrações V5 aplicadas em staging.
- [ ] Projeto Supabase usa signing key assimétrica.
- [ ] URL público e redirects exatos configurados sem wildcard amplo.
- [ ] Registo público desativado; convite reservado ao dashboard Supabase.
- [ ] Conta `ADMIN` de ensaio criada e associada a `staff_profiles`.
- [ ] Conta `REVIEWER` de ensaio criada apenas se necessária ao teste de funções.
- [ ] MFA/TOTP configurado.
- [ ] Sessão `aal1` recusada e sessão `aal2` aceite.
- [ ] Browser sem acesso direto às tabelas editoriais.
- [ ] Conta inativa recusada imediatamente.

## D. Circuito editorial em staging

- [ ] Fonte oficial arquivada aparece na seleção privada.
- [ ] Fonte sem atestação não pode iniciar processo.
- [ ] Processo `HUMAN`, `INGESTION` e `AI` conserva a origem correta.
- [ ] `PENDING → IN_REVIEW → APPROVED` comprovado.
- [ ] Rejeição preserva processo, versão e decisão.
- [ ] Correção acrescenta versão e regressa a `PENDING`.
- [ ] Aprovação não altera qualquer tabela pública.
- [ ] Auditoria identifica alias, função, instante, fundamento e hashes.
- [ ] Tentativa concorrente com revisão antiga é recusada.
- [ ] NIF/NIPC em claro é recusado nos dados normalizados.

## E. Parlamento V5

- [ ] Fotografia `parliament-activity-v5` recolhida e atestada em staging.
- [ ] Manifesto volta a contar reuniões, iniciativas, votações e posições.
- [ ] Diferenças usam apenas `source_id` oficial exato.
- [ ] Proposta `activity` criada em `PENDING`.
- [ ] Proposta `votes` criada em `PENDING`.
- [ ] Cobertura nominal e valores `UNKNOWN` revistos.
- [ ] Publicação por âmbito comprovada em staging.
- [ ] Retirada e efeito público comprovados em staging.
- [ ] Correção e republicação de nova versão comprovadas em staging.
- [ ] Explorador V5 devolve total exato e filtros parametrizados.
- [ ] Histórico público não divulga notas privadas nem IDs internos.
- [x] Plano de backfill versionado define a ordem das legislaturas, fontes-candidatas e portas de
  arquivo, revisão e publicação sem confundir disponibilidade na fonte com cobertura pública.
- [x] Matriz pública de cobertura parlamentar concluída, com período observado, recolha, revisão,
  fonte, hashes e completude histórica não afirmada.
- [x] Catálogos de iniciativas, atividades e atividade dos deputados têm inventário privado por
  etiqueta e URL exatas, sem descarga automática, proposta editorial ou publicação.
- [x] Uma pasta candidata só produz manifesto privado depois de revalidar o catálogo pai; formatos
  ambíguos ou externos são recusados e os ficheiros permanecem por descarregar.
- [x] Um recurso só é arquivado depois de provar catálogo e manifesto exatos; permanece
  `ARCHIVED_UNPARSED`, sem normalização, caso editorial ou publicação.
- [x] O JSON histórico de iniciativas só é normalizado a partir do arquivo atestado, com IDs e URLs
  oficiais exatos, recálculo antes da escrita e cobertura `NOT_ASSERTED`.
- [x] As votações históricas derivadas do JSON de iniciativas exigem ID oficial, recusam factos
  contraditórios, preservam posições sem identificador como `UNKNOWN` e continuam fora do circuito
  editorial.
- [x] As fichas históricas de deputados usam apenas o bloco principal e `DepId`, conservam `GpId` e
  `DepCPId`, excluem contactos e permanecem numa fotografia privada sem criar pessoas ou mandatos.
- [x] O comparador privado de deputados volta a provar manifesto, fonte e arquivo e reconstrói a
  proposta no servidor; intervalos contraditórios ficam visíveis e nunca originam mandatos.
- [x] A prontidão V5.29 é calculada por fotografia completa e permanece read-only; qualquer processo
  em falta ou divergente bloqueia a prova usada pela operação V5.30 separada.
- [x] A publicação V5.30 cria a projeção mínima da fotografia inteira numa única transação e prova
  zero mandatos e zero filiações inferidas num PostgreSQL descartável.
- [x] A retirada V5.31 volta a provar todos os perfis e a publicação original, acrescenta a decisão
  negativa numa única transação e faz recuar a consulta ou mostrar dados indisponíveis.
- [x] A republicação de perfis a partir de uma nova fotografia imutável está comprovada sem reativar
  a versão retirada.

## F. Perfis políticos

- [x] Identidade publicada depende de revisão positiva e fonte atestada.
- [x] Observação parlamentar não é apresentada como início de mandato.
- [x] Mandatos têm datas oficiais e revisão `MANDATE` própria dentro da cobertura V5.33–V5.35.
  - [x] Proposta privada por intervalo oficial exato, com semântica sujeita a revisão humana.
  - [x] Publicação transacional append-only com revisão `MANDATE` própria.
  - [x] Retirada append-only específica, sem alteração ou eliminação da linha publicada.
- [x] Cargos e círculo têm fonte e período explícitos.
  - [x] Proposta privada específica por `DepCargo`, DepId, CarId, círculo e período exatos.
  - [x] Publicação append-only do cargo com revisão própria e projeção pública.
  - [x] Retirada append-only específica do cargo, sem apagar a linha nem a prova anterior.
- [x] Presenças dependem de mandato revisto e fotografia publicada.
  - [x] Recolha privada da reunião inteira, arquivo, SHA-256 e manifesto append-only.
  - [x] Proposta editorial integral por BID exato, sem correspondência por nome ou seleção individual.
  - [x] V5.40 — publicação transacional da reunião inteira com revisão própria.
  - [x] V5.41 — retirada transacional e imutável da reunião inteira, sem apagar observações,
    sessão, linhas ou prova anterior.
- [ ] Autoria de iniciativas usa relação oficial individual.
- [ ] Votos do perfil são nominais e ligados por identificador oficial exato.
- [ ] Posições coletivas permanecem fora do histórico individual.
- [ ] Declaração individual exige fonte EPT, arquivo e revisão jurídica.
- [ ] Ligação geral à EPT continua rotulada apenas como pesquisa institucional.
- [ ] Cada área declara cobertura e intervalo observado.

## G. Promessómetro

- [ ] Critério público para identificar um compromisso verificável aprovado.
- [ ] Programa do XXV Governo arquivado e versionado.
- [ ] Todos os compromissos individualizáveis catalogados.
- [ ] Página ou âncora oficial preservada por compromisso.
- [ ] Provas de diploma, orçamento, regulamentação e execução separadas.
- [x] Estados públicos limitados ao vocabulário editorial aprovado, com
  [compatibilidade histórica fail-closed](V5_PROMESSOMETRO_VOCABULARY.md).
- [ ] Revisão e fundamento obrigatórios para qualquer mudança de estado.
- [ ] Linha temporal pública preserva todos os estados anteriores.
- [ ] Filtros por ministério, área, estado e data testados.
- [ ] Uma lei publicada não é tratada automaticamente como execução material.

## H. Investigador Cívico

- [ ] Âmbito temporal do Portal BASE definido.
- [ ] Lotes completos arquivados e persistidos apenas em staging.
- [ ] Promoção revista para `PublicContract` implementada e testada.
- [ ] Organizações e titulares têm fontes próprias.
- [ ] Pepper HMAC estável configurado fora do repositório.
- [ ] Nenhum identificador fiscal em claro persiste ou aparece em logs.
- [ ] Correspondências exatas entram apenas em `PENDING_REVIEW`.
- [ ] Não existe fuzzy matching.
- [ ] Relações exigem dois nós publicados, fonte, tipo e datas.
- [ ] Grafo público distingue ligação factual de acusação ou conflito.
- [ ] Direito de resposta e retirada cobrem contratos e relações.
- [ ] AIPD e revisão jurídica aplicáveis concluídas.

## I. IA responsável

- [x] Endpoint de geração exige staff autenticado e MFA adequado.
- [x] Documento de entrada existe no arquivo atestado.
- [x] Geração persiste fonte, modelo, fornecedor, prompt, versões e hashes.
- [x] Proposta nasce com origem `AI`, `created_by_id` nulo e `PENDING`.
- [x] `requires_human_review` permanece obrigatório.
- [x] O modelo pode responder que não existem dados suficientes.
- [x] Citações e âncoras fora da entrada são rejeitadas.
- [ ] Prompt injection no documento não altera instruções.
- [x] Revisão permite aprovar, rejeitar, corrigir ou regenerar.
- [x] Apenas a versão aprovada entra na projeção pública.
- [x] Conteúdo público mostra rótulo de IA, fontes, modelo e data.
- [ ] Cenários usam factos e cálculos determinísticos, não previsão livre.
- [ ] Limite de custo, tamanho, taxa e cache configurados.
- [ ] Avaliação mede fidelidade, omissões, abstenção e diferenças entre grupos.

## J. Pesquisa, comparação e PWA

- [x] Pesquisa global consulta apenas projeções publicadas e não cria um índice editorial paralelo.
- [x] Resultados mostram tipo, fonte, recolha, revisão, SHA-256 e estado de cobertura.
- [ ] Comparações exigem o mesmo universo, período e metodologia.
- [ ] Navegação e filtros são consistentes em desktop e telemóvel.
- [x] Método público equivalente com axe-core no Chromium e limites documentados concluído.
- [x] Metas móveis definidas e medidas pela mediana de três execuções Lighthouse no CI.
- [x] Instalação PWA e ativação do modo offline são escolhas explícitas e reversíveis.
- [x] Pedido de notificações ocorre apenas após consentimento informado.
- [x] Preferências de alerta podem ser alteradas e apagadas.
- [x] Revogação desativa a subscrição no navegador e pede eliminação exata no backend; uma falha
  remota fica visível e pode ser repetida.
- [x] Alertas usam apenas conteúdo humano publicado, vigente e ligado a fonte atestada.

## K. Fontes e cobertura histórica

- [ ] DRE tem circuito de promoção público próprio.
- [ ] BASE tem circuito de promoção público próprio.
- [ ] EPT tem tratamento juridicamente revisto e sem equivaler portal a declaração.
- [ ] Tribunal de Contas publica apenas factos adequados ao documento oficial.
- [ ] Parlamento Europeu só atribui votos nominais com identificador inequívoco.
- [ ] SNS declara indicador, período e cobertura territorial.
- [ ] Cada fonte municipal identifica os territórios efetivamente cobertos.
- [ ] Frequência e atraso de cada fonte são públicos.
- [ ] Falha de recolha não substitui silenciosamente a versão revista.
- [ ] Histórico preserva todas as fotografias e decisões.

## L. Produção, privacidade e recuperação

- [ ] Backup cifrado válido obtido antes das migrações V5.
- [ ] Migrações de produção autorizadas e executadas separadamente.
- [x] Backend V5 publicado sem promover dados automaticamente.
- [x] Frontend e backend anunciam capacidades compatíveis e falham fechados quando o esquema ainda
  não suporta uma área.
- [ ] CORS, CSP, rate limit, autenticação e logs revistos.
- [ ] Email institucional configurado com SPF, DKIM e DMARC.
- [ ] Políticas legais atualizadas após ativar IA, perfis sensíveis ou PWA.
- [ ] AIPD e aconselhamento jurídico independente registados onde aplicável.
- [ ] Backup pós-migração cifrado e retido fora do fornecedor principal.
- [ ] Restauro pós-migração aprovado num PostgreSQL 17 isolado.
- [ ] Segredos temporários de recuperação removidos depois do ensaio.
- [ ] Monitorização não cria perfis de visitantes nem recolhe conteúdo sensível.

## M. Publicação do código e release

- [x] História Git integral pesquisada por segredos, dumps e identificadores protegidos; a
  [auditoria sanitizada](V5_RELEASE_PRIVACY_AUDIT.md) mantém a publicação pública bloqueada por um
  contacto pessoal ainda presente em diffs históricos.
- [ ] Todas as credenciais anteriormente expostas confirmadas como revogadas.
- [ ] Licenças do software, conteúdo e fontes verificadas.
- [ ] Comunicação pública usa `source-available` enquanto vigorar PolyForm Noncommercial.
- [ ] Visibilidade pública do repositório autorizada separadamente.
- [ ] CI final verde no commit candidato.
- [ ] Smoke público desktop e móvel aprovado.
- [ ] Zero falhas críticas conhecidas abertas.
- [ ] Limitações conhecidas publicadas sem linguagem de completude absoluta.
- [ ] Changelog e notas de release preparados.
- [ ] Tag assinada ou protegida `v0.5.0` criada no commit aprovado.
- [ ] Gate final regista evidência de deployment, dados, backup e restauro.

## Regra de fecho

Uma caixa não pode ser marcada apenas porque existe um modelo, botão, coletor ou teste isolado. A
evidência tem de corresponder ao ambiente e à condição descritos. Um item que dependa de decisão
jurídica, fonte externa ou autorização operacional permanece aberto e visível até essa condição
existir.
