# Revisão documental antes do lançamento da V5

Data: 11 de setembro de 2026. Base: `main`, commit
`642d8fc8a698c96af45d9c3abdaea9f04cf2866a`. Os dois documentos novos desta revisão são este
relatório e o [índice completo](README.md).

## Decisão

**A documentação ainda não permite declarar a V5 concluída para lançamento público.**
As incoerências operacionais identificadas abaixo foram corrigidas, mas continuam abertos
requisitos editoriais, de autenticação, recuperação, cobertura, privacidade e avaliação jurídica.
O site acessível e o esquema V5 aplicado não comprovam esses requisitos.

## Âmbito e verificações

- Inventário e leitura automática integral dos **90 documentos de origem**, totalizando
  **647 789 bytes**: todos os Markdown/MDX versionados, licenças textuais e JSON documental.
  Cada ficheiro teve tamanho e SHA-256 calculados no inventário local.
- Pesquisa transversal de estados, condições pendentes e referências de publicação; revisão
  semântica dirigida dos documentos de operação, segurança, arquitetura, neutralidade,
  governação, IA, fontes, licenciamento, plano, checklist e contratos de etapas V5.
- Zero destinos de ficheiros inexistentes nas ligações Markdown relativas verificadas. O teste
  exclui código cercado, destinos absolutos e âncoras internas; não valida todas as âncoras.
- **55 URLs externos únicos**, incluindo ligações Markdown e autoligações entre `<…>`,
  responderam **HTTP 200** nesta verificação, seguindo redirecionamentos. Este resultado prova
  acessibilidade momentânea, não estabilidade, correção do conteúdo, validade jurídica ou
  ausência de alteração posterior das fontes.
- Zero ocorrências dos três padrões pesquisados nos documentos: identidade privada age,
  cabeçalho de chave privada e chave secreta Supabase. Não é uma pesquisa universal de segredos
  nem uma repetição da auditoria de toda a história Git.
- Issues [#58](https://github.com/DxMaxi/transparencia-total-open-source/issues/58) e
  [#76](https://github.com/DxMaxi/transparencia-total-open-source/issues/76) consultadas.
  A #76 declara resolvidos os achados técnicos confirmados do seu checkpoint; mantém requisitos
  finais abertos. Não se converteu esse checkpoint numa auditoria atual de todo o código.

“Todos os documentos” significa cobertura do inventário versionado, com os limites de análise
acima. Não significa parecer jurídico linha a linha nem prova operacional de todos os contratos.
Anexos externos, páginas dos fornecedores, issues e conteúdo de outras branches não integram os
90 ficheiros. Os documentos históricos foram conservados, identificados e ligados ao estado atual.

## Incoerências corrigidas

| Documento | Problema | Correção |
|---|---|---|
| `NEUTRALITY.md` | Estados públicos antigos incompatíveis com a V5.20 | Cinco estados aprovados; valores legados fora das projeções e sem reclassificação automática |
| `DEPLOYMENT.md` | Migração manual e Blueprint Render podiam ser confundidos com a instalação Supabase existente | Workflow protegido, prova recente, destino exato, CA oficial e distinção entre instalação real e alternativas |
| `DEPLOYMENT.md` | Configuração incompleta de Auth e descrição desatualizada do preflight/smoke | Variáveis públicas Supabase, MFA, origens exatas, pesquisa global e eventos reais do workflow |
| `SECURITY.md` | Push descrito como inexistente e proteção de branch ainda apresentada como futura | Consentimento/configuração condicional e proteção de `main` comprovada, sem presumir outros scanners |
| `ARCHITECTURE.md` | Autorização editorial ainda descrita como chave administrativa e promoção ambígua | JWT, staff ativo, função, MFA e decisão humana específica de publicação |
| `ARCHITECTURE.md` / `DATA_SOURCES.md` | Organizações e correspondências V5.53–V5.54 ainda tratadas apenas como trabalho futuro | Código existente distinguido da ativação remota; relações factuais V5.55 continuam pendentes |
| `AI_GOVERNANCE.md` | Boletins admitiam resumos apenas aprovados | Apenas versões efetivamente publicadas e vigentes; aprovação isolada insuficiente |
| `DATABASE_RECOVERY.md` / `README.md` | Métricas antigas de agosto podiam ser lidas como atuais | Baseline histórica identificada e ligação ao registo operacional recente |
| `backend/README.md` | Título V4 e exemplos legados sem orientação suficiente para V5 | Contexto V5, autorização editorial e limites de staging explícitos |
| Plano, checklist e handoff | Estado anterior à V5.54 e à migração remota | Evidência atual acrescentada sem apagar a cronologia ou fechar requisitos sem prova |

## Provas técnicas atuais

- CI [34466173379](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/34466173379)
  aprovado para a correção de impressão do arquivo binário; inclui alteração real de bytes
  mantendo o hash declarado e ciclo cifrado de backup/restauro.
- Restauro [34547252155](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/34547252155)
  aprovado: 53 tabelas e 520 379 registos originais preservados após 33 migrações; segundo
  ciclo V5 aprovado com 78 tabelas e um perfil sintético inativo adicional.
- Migração de produção [34547739521](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/34547739521)
  aprovada: mesmos 520 379 registos originais preservados, 33 checksums, RLS e privilégios browser
  verificados. Consulta independente confirmou zero migrações incompletas.
- Perfil ADMIN autorizado criado. O responsável concluiu o MFA e comprovou o acesso ao painel.
  Consulta independente confirmou um fator TOTP verificado e zero pendentes; não foram recolhidos
  códigos ou segredos para efetuar essa verificação.
- Smoke público [34547988929](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/34547988929)
  aprovado após a migração, incluindo o percurso público Chromium do workflow.

Os resultados posteriores, incluindo a recuperação da cópia pós-migração, devem ser consultados
na última entrada do [registo de entrega](V5_DELIVERY_2026-09-09.md).

## Condições ainda abertas para concluir a V5

1. Ensaiar em staging separado o acesso `aal2`, recusa
   de operações privadas em `aal1`, revogação de conta e circuito editorial completo, incluindo
   concorrência, correção, publicação e retirada. A elegibilidade inicial da sessão é a exceção
   deliberada que aceita `aal1` para preparar o segundo fator.
2. Confirmar backup e restauro posteriores à migração, remover o segredo temporário e documentar
   recuperação de Auth/MFA separadamente. O dump do esquema `public` não recupera esses fatores.
3. Consolidar humanamente os 1 590 candidatos técnicos do Programa do Governo; definir critérios,
   preservar localizadores e separar prova legislativa, orçamental e de execução. Não são 1 590
   promessas já publicadas ou classificadas.
4. Ensaiar os módulos e declarar cobertura real das fontes e períodos. Completar os circuitos
   ainda necessários, incluindo relações factuais V5.55; V5.54 só cria candidatos privados.
5. Concluir a avaliação jurídica/AIPD aplicável antes de tratar casos protegidos, bem como
   contacto institucional, direitos das fontes e política de privacidade. `DPIA_TEMPLATE.md`
   é um modelo por preencher; a licença do código não concede direitos sobre documentos oficiais.
6. Repetir a pesquisa de segredos/história no candidato final e reconciliar o contacto histórico
   e credenciais expostas. A autorização para o repositório público não resolve automaticamente
   cada achado. Preservar a capacidade de restauro durante qualquer rotação de identidade age.
7. Fechar avaliações de IA, comparabilidade, configuração/custos e ensaios de PWA/notificações
   que continuam sem prova operacional na checklist.
8. Preparar notas de release e limitações; provar CI e deployment do candidato final; criar
   `v0.5.0` apenas depois de todos os requisitos aplicáveis terem evidência.

O [plano](V5_RELEASE_PLAN.md) e a [checklist](V5_RELEASE_CHECKLIST.md) continuam canónicos.
Uma página de documentação coerente não substitui a execução ou decisão que descreve.
