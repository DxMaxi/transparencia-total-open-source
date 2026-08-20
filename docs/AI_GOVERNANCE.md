# Governação do pipeline de IA

## Estado de implementação

`AI_PROVIDER=disabled` mantém a IA desligada por omissão e o website não apresenta resumos gerados
por IA. Os endpoints de resumo e guia são contratos técnicos experimentais: exigem uma identidade
editorial ativa com MFA, validam a saída estruturada e devolvem metadados do modelo e do prompt, mas
ainda não persistem uma proposta `PENDING`, não criam uma fila de revisão e não publicam conteúdo
aprovado. O script de resumo DRE apenas escreve o resultado no terminal.

Ativar o fornecedor em produção antes de completar esse circuito não é uma forma válida de lançar a
funcionalidade. A autenticação impede geração pública anónima, mas não transforma a resposta
experimental em conteúdo publicável. A fase seguinte deve carregar os factos verificados no
servidor, arquivar cada proposta de forma privada, limitar a geração, registar aprovação ou rejeição
humana e publicar somente uma nova versão imutável aprovada com ligações às fontes oficiais.

## Papel permitido

O modelo transforma linguagem jurídica em uma proposta de leitura simples. Não determina verdade,
constitucionalidade, mérito, intenção, impacto económico ou cumprimento do programa do Governo.

## Configuração

`AI_PROVIDER=disabled` é o valor seguro por omissão. `AI_PROVIDER=openai` ativa
`OpenAISummarizer`, que usa a Responses API e valida a saída diretamente contra `CitizenSummary`.
O modelo é configurável por `OPENAI_MODEL`; a chave existe apenas no backend.

O prompt versionado exige português de Portugal, proíbe conhecimento externo, distingue entrada em
vigor de execução e pede âncoras internas. `PROMPT_SHA256` permite saber exatamente quais regras
produziram cada proposta.

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
coberto; o revisor vê o tamanho e as partes processadas.

## Revisão antes de publicação

1. Confirmar título, identificador, hash e URL.
2. Comparar cada afirmação com a âncora indicada.
3. Verificar datas, exceções, âmbito territorial e normas transitórias.
4. Remover inferências e assinalar conteúdo não extraído.
5. Aprovar, rejeitar ou pedir nova geração.
6. Registar revisor, data, modelo, prompt e decisão.

Conteúdo `PENDING` não entra em boletins públicos. Uma nova versão do diploma torna o resumo anterior
obsoleto, sem o apagar.

## Boletins

O gerador de boletins deve receber apenas resumos `APPROVED`, ordenar por publicação e agrupar por
tema através de taxonomia editorial versionada. Cada boletim inclui período, critérios, lista de
diplomas, exclusões e links individuais. O balanço de mandato não converte número de diplomas em
avaliação de desempenho.

## Privacidade, segurança e custo

- Enviar apenas texto de documentos públicos, nunca dados de utilizadores ou chaves.
- Usar `OPENAI_STORE=false` salvo decisão de governação documentada.
- Aplicar limite de tamanho, orçamento diário e cache por `contentSha256 + model + promptSha256`.
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
