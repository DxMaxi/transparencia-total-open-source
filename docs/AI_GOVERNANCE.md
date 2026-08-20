# Governação do pipeline de IA

## Estado de implementação

`AI_PROVIDER=disabled` mantém novas gerações de IA desligadas por omissão. Esta configuração não
apaga nem oculta uma explicação anteriormente publicada e revista: geração e leitura pública são
operações independentes. A V5 dispõe de um circuito privado para propostas de resumo DRE que só
aceita snapshots previamente persistidos, concluídos e ligados ao arquivo oficial atestado; exige
staff ativo com MFA; e cria uma versão editorial imutável `PENDING`. Ingestão, geração, revisão,
aprovação e publicação continuam a ser operações diferentes.

O painel privado permite pesquisar snapshots DRE que voltaram a passar a verificação do texto,
hashes e atestação, pedir a proposta com confirmações explícitas e comparar lado a lado o texto
oficial arquivado com a saída estruturada. O catálogo não devolve o texto jurídico; o texto integral
só é entregue, em excertos navegáveis e limitados, no detalhe MFA do processo exato. Uma regeneração
exige que o revisor já tenha iniciado a revisão, fica ligada à revisão e ao SHA-256 da versão que viu
e acrescenta uma versão `AI` seguida de uma decisão humana `CORRECT`. Nunca altera nem apaga a versão
anterior.

A projeção pública para `AI_EXPLANATION` só aceita a versão exata já aprovada e exige uma segunda
decisão explícita de um `ADMIN` com MFA `aal2`. O servidor reconstrói a projeção, valida novamente a
fonte, a atestação, o texto, as âncoras e todos os hashes, e grava revisão pública, auditoria, decisão
e evento de publicação na mesma transação. A publicação não chama o modelo. Se qualquer prova não
coincidir, se existir ambiguidade ou se faltar uma peça, a explicação não é apresentada.

As antigas rotas de geração direta e o script que imprimia resumos sem persistência continuam a
devolver uma recusa explícita. A consulta pública expõe apenas o contrato revisto, a fonte oficial,
as provas por SHA-256 e o alias público do revisor; não expõe notas privadas nem identificadores
internos do processo editorial.

## Papel permitido

O modelo transforma linguagem jurídica em uma proposta de leitura simples. Não determina verdade,
constitucionalidade, mérito, intenção, impacto económico ou cumprimento do programa do Governo.

## Configuração

`AI_PROVIDER=disabled` é o valor seguro por omissão. `AI_PROVIDER=openai` ativa
`OpenAISummarizer`, que usa a Responses API e valida a saída diretamente contra `CitizenSummary`.
O modelo é configurável por `OPENAI_MODEL`; a chave existe apenas no backend.

O prompt versionado exige português de Portugal, proíbe conhecimento externo, distingue entrada em
vigor de execução e pede âncoras internas literais. `PROMPT_SHA256` permite saber exatamente quais
regras produziram cada proposta. O servidor rejeita âncoras que não existam literalmente no snapshot,
salvo quando a saída se abstém de forma explícita e não apresenta itens factuais.

Cada proposta conserva no JSON normalizado imutável: contrato, fornecedor, modelo, versão e SHA-256
do prompt, SHA-256 da entrada e saída estruturadas, referências SHA-256 do snapshot, documento-fonte
e tentativa, hashes do conteúdo e texto normalizado, atestação de arquivo, datas, versão do extrator,
tamanho processado e truncagem. Os identificadores técnicos exatos continuam ligados pelo processo
editorial e pela fonte privada, sem serem duplicados no texto normalizado.
A versão e o processo têm origem `AI` e `created_by_id` nulo. A decisão `SUBMIT` identifica a pessoa
que pediu a geração, sem transformar essa pessoa em autora do texto do modelo.

## Saída estruturada

- resumo para cerca de dois minutos;
- mudanças descritas no diploma;
- pessoas ou entidades afetadas;
- datas e prazos;
- deveres e direitos;
- incertezas e omissões;
- glossário;
- artigos, capítulos ou secções de suporte.

Textos longos são divididos por parágrafos. Cada parte é resumida e uma chamada final consolida
apenas essas saídas. O limite evita pedidos excessivos, mas não prova que o diploma foi totalmente
coberto; o revisor vê o tamanho processado e se houve truncagem.

## Revisão antes de publicação

1. Confirmar título, identificador, hash e URL.
2. Comparar cada afirmação com a âncora indicada.
3. Verificar datas, exceções, âmbito territorial e normas transitórias.
4. Remover inferências e assinalar conteúdo não extraído.
5. Aprovar, rejeitar ou pedir nova geração.
6. Registar revisor, data, modelo, prompt e decisão.
7. Publicar separadamente, confirmando a projeção e os hashes exatos apresentados pelo servidor.

Pedir nova geração conta para o limite diário e faz o processo regressar a `PENDING`. Não é uma
aprovação implícita: a nova versão tem de percorrer novamente todo o circuito humano.

Conteúdo `PENDING`, `IN_REVIEW` ou apenas `APPROVED` não entra na consulta pública. Uma retirada
preserva a versão e todos os eventos, substitui o efeito público ativo por **dados indisponíveis** e
mantém um histórico redigido. Uma correção ou nova geração acrescenta outra versão `PENDING` e exige
todo o circuito de revisão e publicação. Uma nova versão do diploma não altera silenciosamente a
explicação anterior.

## Contrato público e limites

Cada explicação publicada é rotulada **“Explicação gerada por IA — revista por humano”** e mostra a
fonte oficial, data de recolha, SHA-256 do documento, modelo, versão e SHA-256 do prompt, entrada,
saída, versão editorial, projeção e evento. Mostra também âncoras e limitações, incluindo truncagem da
fonte quando aplicável.

O contrato declara expressamente que a IA não é fonte, que o texto não é notícia automática, que
não é previsão e que não recomenda partidos nem sentido de voto. O identificador público deriva do
SHA-256 do documento oficial; IDs internos, notas privadas e fundamentações internas permanecem fora
da API pública. O detalhe e o histórico são lidos em transações `repeatable read` e falham fechados
se as provas imutáveis deixarem de coincidir.

## Boletins

O gerador de boletins deve receber apenas resumos `APPROVED`, ordenar por publicação e agrupar por
tema através de taxonomia editorial versionada. Cada boletim inclui período, critérios, lista de
diplomas, exclusões e links individuais. O balanço de mandato não converte número de diplomas em
avaliação de desempenho.

## Privacidade, segurança e custo

- Enviar apenas texto de documentos públicos, nunca dados de utilizadores ou chaves.
- `OPENAI_STORE=false` é obrigatório e uma configuração `true` impede o arranque.
- `store=false` não significa retenção zero. A política normal do fornecedor pode conservar registos
  de monitorização de abuso por até 30 dias; só são enviados documentos públicos, nunca dados de
  utilizadores, credenciais, NIF/NIPC ou texto editorial privado. Ver [controlos de dados da API
  OpenAI](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint).
- Aplicar limite de tamanho e limite diário antes da chamada. Um bloqueio PostgreSQL fail-closed
  impede concorrência entre instâncias; cada tentativa fica num `AuditEvent` append-only.
- Reutilizar por `snapshot + provider + model + promptSha256`, sem nova chamada externa.
- Tratar o texto da fonte como dados não confiáveis; o prompt do documento não altera instruções.
- Registar métricas e IDs técnicos sem guardar a chave nem cabeçalhos de autenticação.

## Modelo local

Para acrescentar um modelo local, implemente a interface abstrata `Summarizer`, mantenha o mesmo
contrato Pydantic e acrescente um valor explícito a `AI_PROVIDER`. A revisão humana, os hashes e o
estado `PENDING` continuam obrigatórios.

## Guia Neutro do Cidadão — V2

O segundo pipeline não recebe o texto livre de uma notícia nem pesquisa a Internet. Recebe:

- um perfil genérico com escalão amplo, distrito, número de dependentes e situação profissional;
- factos de impacto previamente verificados, cada um com `fact_id`, resultado determinístico,
  vigência, URL oficial, âncora e ressalvas.

O LLM apenas converte esse material em linguagem simples. Cálculos de IRS, apoios, datas, direitos
e elegibilidade pertencem a regras versionadas e testadas fora do modelo. A API rejeita citações a
IDs que não foram fornecidos e força `requires_human_review=true`.

A instrução de sistema está em `backend/app/services/civic_guide.py`, com versão e SHA-256 próprios.
Ela trata perfil e factos como dados não confiáveis para efeitos de prompt injection, proíbe
inferências de corrupção, intenção, causalidade e preferência política, e exige abstenção quando o
conjunto verificado é insuficiente.

Não se promete ausência absoluta de viés ou precisão absoluta. Avaliações de qualidade devem medir,
por versão e por tema: fidelidade às âncoras, conservação de exceções, citações inválidas, taxa de
abstenção, diferenças entre grupos equivalentes, incidentes e alterações feitas pelo revisor.
