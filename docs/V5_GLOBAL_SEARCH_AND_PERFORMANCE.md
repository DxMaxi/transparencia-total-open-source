# V5.18 — pesquisa global publicada e orçamento móvel

## Objetivo

Esta etapa cria uma entrada simples para consultar a informação que já atravessou as portas
públicas do projeto e torna o desempenho móvel uma condição repetível do CI. Não cria um índice
paralelo, não consulta staging e não converte uma pesquisa numa decisão editorial.

## Pesquisa federada, não um ranking

`GET /api/v1/public/search` recebe uma expressão entre 2 e 120 caracteres, a legislatura
parlamentar e um limite por secção. A resposta mantém seis universos separados:

- políticos;
- reuniões parlamentares;
- iniciativas parlamentares;
- votações parlamentares;
- compromissos do Promessómetro;
- explicações de IA publicadas.

As contagens são exatas dentro de cada projeção disponível. Não existe uma pontuação de relevância
comum porque uma pessoa, uma votação e um compromisso não são entidades comparáveis. A soma
apresentada serve apenas para indicar quantos registos publicados corresponderam à expressão nas
secções consultadas.

Cada resultado exige:

- tipo de registo;
- endereço público interno;
- fonte oficial;
- data de recolha;
- SHA-256 da fonte;
- data da decisão ou revisão que abriu a projeção pública;
- nota de cobertura e limitação.

## Portas reutilizadas

A pesquisa não define uma nova regra de publicação:

- políticos reutilizam a fotografia de identidades integralmente revista e atestada;
- parlamento reutiliza a fotografia mais recente aprovada por legislatura e âmbito;
- promessas exigem a decisão humana `ACCEPT`, programa arquivado e prova arquivada para qualquer
  estado além de `UNVERIFIED`;
- explicações de IA voltam a validar fonte DRE, versão, hashes, decisão humana e evento de
  publicação.

Os filtros textuais usam correspondência literal parametrizada. Não existe fuzzy matching,
semelhança, associação de identidades ou transformação de uma sigla coletiva em atividade
individual. A pesquisa também não gera explicações, previsões, notícias ou cenários.

## Falhas e cobertura

As secções são consultadas de forma independente. Se, por exemplo, o esquema editorial de IA ainda
não estiver ativo, essa área fica `UNAVAILABLE`, com total desconhecido e sem exemplos de
substituição; políticos e parlamento podem continuar disponíveis. Se nenhuma projeção responder, a
API devolve `503` com mensagem pública controlada.

A capacidade `global_search_v1` é anunciada em `/api/v1/health`. O preflight do deployment exige a
capacidade e exerce a rota antes de promover o frontend. Uma API V5 que anuncie apenas capacidades
anteriores não é tratada como compatibilidade suficiente.

## Experiência pública

`/pesquisa` agrupa os resultados por área e mostra fonte, recolha, revisão, hash e cobertura no
próprio cartão. Uma expressão ausente não executa qualquer consulta; uma expressão demasiado curta
é recusada. A página não mantém um fallback local.

O cabeçalho torna a pesquisa acessível em desktop e telemóvel. O sitemap inclui apenas a rota sem
parâmetros. O modo offline pode guardar essa página introdutória depois de consentimento, mas o
service worker recusa guardar qualquer URL com uma expressão de pesquisa.

O Promessómetro passa a aceitar a expressão recebida da pesquisa global, filtra apenas o catálogo
que já carregou da projeção pública e expõe uma âncora estável por compromisso. A contagem de
cobertura distingue o catálogo publicado da seleção editorial usada apenas em fallback.

## Orçamento móvel repetível

O comando `npm run performance:mobile` mede `/`, `/atividade-parlamentar` e `/pesquisa` no artefacto
Next.js de produção. Usa a simulação móvel predefinida do Lighthouse e a mediana de três execuções
por rota. O relatório completo e o resumo ficam em `.sites-runtime/lighthouse/`, fora do Git.

O CI falha quando a mediana de qualquer rota ultrapassa:

| Métrica | Limite |
|---|---:|
| Pontuação Lighthouse Performance | pelo menos 0,90 |
| First Contentful Paint | 2 500 ms |
| Largest Contentful Paint | 3 500 ms |
| Total Blocking Time | 350 ms |
| Cumulative Layout Shift | 0,10 |
| Time to Interactive | 4 500 ms |
| Bytes transferidos | 400 000 |

O ensaio local de 20 de agosto de 2026, antes do CI, obteve pontuação 0,98 nas três rotas, LCP entre
2 219 e 2 274 ms, TBT entre 70 e 85 ms, CLS 0 e 207 506 a 212 015 bytes. Estes valores são uma
linha de base local, não uma garantia da experiência de cada cidadão; a passagem no runtime Node
24 do CI e a observação de produção continuam separadas.

O Lighthouse explica que a simulação móvel predefinida aproxima uma ligação móvel limitada e um
dispositivo de gama média. A documentação do Lighthouse CI recomenda várias execuções para reduzir
variação. Por isso, o gate usa medidas factuais e medianas, sem apresentar uma pontuação isolada
como prova absoluta de desempenho:

- <https://github.com/GoogleChrome/lighthouse/blob/main/docs/throttling.md>
- <https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/configuration.md>

## Limites preservados

Esta etapa não altera dados, revisão, publicação, retiradas, histórico, direito de resposta,
segredos, Supabase ou produção. Não prova cobertura histórica completa e não resolve as fontes ou
módulos ainda listados como pendentes no plano da V5.
