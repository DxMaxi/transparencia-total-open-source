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
- [ ] Plano de backfill define legislaturas e fontes disponíveis.
- [ ] Matriz pública de cobertura parlamentar concluída.

## F. Perfis políticos

- [ ] Identidade publicada depende de revisão positiva e fonte atestada.
- [ ] Observação parlamentar não é apresentada como início de mandato.
- [ ] Mandatos têm datas oficiais e revisão `MANDATE` própria.
- [ ] Cargos e círculo têm fonte e período explícitos.
- [ ] Presenças dependem de mandato revisto e fotografia publicada.
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
- [ ] Estados limitados ao vocabulário editorial aprovado.
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

- [ ] Endpoint de geração exige staff autenticado e MFA adequado.
- [ ] Documento de entrada existe no arquivo atestado.
- [ ] Geração persiste fonte, modelo, fornecedor, prompt, versões e hashes.
- [ ] Proposta nasce com origem `AI`, `created_by_id` nulo e `PENDING`.
- [ ] `requires_human_review` permanece obrigatório.
- [ ] O modelo pode responder que não existem dados suficientes.
- [ ] Citações e âncoras fora da entrada são rejeitadas.
- [ ] Prompt injection no documento não altera instruções.
- [ ] Revisão permite aprovar, rejeitar, corrigir ou regenerar.
- [ ] Apenas a versão aprovada entra na projeção pública.
- [ ] Conteúdo público mostra rótulo de IA, fontes, modelo e data.
- [ ] Cenários usam factos e cálculos determinísticos, não previsão livre.
- [ ] Limite de custo, tamanho, taxa e cache configurados.
- [ ] Avaliação mede fidelidade, omissões, abstenção e diferenças entre grupos.

## J. Pesquisa, comparação e PWA

- [ ] Pesquisa global indexa apenas dados publicados.
- [ ] Resultados mostram tipo, fonte, data e estado de cobertura.
- [ ] Comparações exigem o mesmo universo, período e metodologia.
- [ ] Navegação e filtros são consistentes em desktop e telemóvel.
- [ ] Auditoria de acessibilidade completa ou método público equivalente concluído.
- [ ] Metas de desempenho definidas e medidas em rede móvel.
- [x] Instalação PWA e ativação do modo offline são escolhas explícitas e reversíveis.
- [ ] Pedido de notificações ocorre apenas após consentimento informado.
- [ ] Preferências de alerta podem ser alteradas e apagadas.
- [ ] Revogação desativa a subscrição no navegador e no backend.
- [ ] Alertas usam apenas conteúdo aprovado.

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
- [ ] Backend V5 publicado sem promover dados automaticamente.
- [ ] Frontend e backend anunciam versões compatíveis.
- [ ] CORS, CSP, rate limit, autenticação e logs revistos.
- [ ] Email institucional configurado com SPF, DKIM e DMARC.
- [ ] Políticas legais atualizadas após ativar IA, perfis sensíveis ou PWA.
- [ ] AIPD e aconselhamento jurídico independente registados onde aplicável.
- [ ] Backup pós-migração cifrado e retido fora do fornecedor principal.
- [ ] Restauro pós-migração aprovado num PostgreSQL 17 isolado.
- [ ] Segredos temporários de recuperação removidos depois do ensaio.
- [ ] Monitorização não cria perfis de visitantes nem recolhe conteúdo sensível.

## M. Publicação do código e release

- [ ] História Git integral pesquisada por segredos, dumps e identificadores protegidos.
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
