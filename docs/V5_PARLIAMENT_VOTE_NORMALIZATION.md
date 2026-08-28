# V5.26 — normalização privada de votações parlamentares históricas

## Objetivo

A V5.26 acrescenta uma segunda interpretação privada dos bytes arquivados pela V5.24. O âmbito é
um único recurso JSON de iniciativas de uma legislatura, porque é nesse recurso oficial que a
Assembleia da República inclui as votações ligadas ao percurso das iniciativas. O resultado é uma
fotografia separada, apenas de votações e posições, sem caso editorial e sem projeção pública.

Esta entrega acrescenta código, testes e documentação. Não executa o comando em staging ou
produção, não descarrega novamente a fonte e não altera dados reais.

## Âmbito factual

O [catálogo oficial de Atividades](https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx)
contém categorias heterogéneas — por exemplo, audições, audiências, debates, deslocações e eventos.
A V5.26 não converte essas categorias em reuniões ou votações. Esse conjunto exigirá um modelo
próprio antes de qualquer normalização. As votações deste gate são lidas exclusivamente de um
recurso já provado pelo
[catálogo de Iniciativas](https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx).

Para esta fase são aceites apenas:

- catálogo pai `INITIATIVES`;
- recurso `JSON`;
- legislatura exata suportada;
- URL HTTPS num anfitrião parlamentar autorizado;
- cadeia V5.22 → V5.23 → V5.24 integralmente atestada em PostgreSQL.

O HTML vivo e a disponibilidade atual da fonte servem apenas para orientar o desenho. A prova da
execução continua a ser composta pelos bytes content-addressed, URL efetivo, instante de recolha e
SHA-256 guardados no arquivo privado.

## Identidade e conflitos

Uma votação só entra quando a fonte fornece um identificador oficial inequívoco e pelo menos um
facto de votação, como resultado, detalhe ou data. O número e o título da iniciativa ascendente são
conservados apenas quando pertencem ao mesmo ramo exato do JSON.

O mesmo ID pode aparecer em mais de uma iniciativa numa votação conjunta. Isso não é tratado como
correspondência de nomes e não cria uma ligação individual. Datas incompatíveis, resultados
incompatíveis ou sentidos incompatíveis para o mesmo ator e ID fazem o lote falhar por inteiro.
Detalhe adicional não contraditório pode completar uma observação repetida.

Não existe fuzzy matching, classificação ideológica, inferência de tema, efeito jurídico ou impacto
material.

## Pessoas, partidos e posições desconhecidas

- Uma posição só conserva tipo `PERSON` quando a própria estrutura fornece um identificador oficial
  individual.
- Texto livre, siglas e nomes sem identificador ficam como `UNKNOWN`.
- Uma sigla nunca é transformada automaticamente numa entidade partidária.
- Uma posição coletiva nunca é convertida num voto individual.
- A persistência privada pode ligar `PERSON` apenas a um `people.source_id` exatamente igual; a
  ausência dessa pessoa deixa a relação vazia.
- Nenhuma destas observações autoriza publicação ou inclusão num perfil político.

Votações sem posições são conservadas quando existe um ID e outro facto oficial. A limitação fica
num aviso explícito; não se inventam atores. O lote está limitado a 50 000 votações e 250 000
posições.

## Revalidação e persistência

Antes da escrita, o serviço volta a provar catálogo, manifesto, arquivo, `SourceDocument`,
atestação, objeto PostgreSQL, URL, tamanho e SHA-256. Depois repete toda a normalização e exige
igualdade integral com a fotografia proposta.

A fotografia corrigida usa o parser `parliament-historical-votes-v2`, contém zero sessões e zero iniciativas,
e acrescenta um `SyncRun` `PARTIAL` com `historical_completeness=NOT_ASSERTED`. O histórico recebe
apenas o evento normal de ingestão append-only. O resultado declara explicitamente:

- zero casos editoriais;
- zero eventos de publicação;
- `publication_performed=false`;
- `publishable=false`.

Uma correção futura exige uma nova versão de parser e conserva a fotografia anterior.

A V5.45 introduziu a versão `v2` para persistir o `actor_source_id` de cada posição individual. Não
existe backfill: fotografias `v1` permanecem no arquivo, mas não satisfazem a prova individual da
ficha pública.

## Porta operacional

O comando `scripts.sync_parliament_resource_vote_normalization` exige `ENVIRONMENT=staging`, uma
`DATABASE_URL` de staging, os três identificadores exatos da cadeia, o URL integral do recurso e
`--confirm-private-staging`. Produção é recusada pela camada de serviço. Não existe workflow
automático, calendário, iteração por legislaturas ou continuação para revisão.

## O que esta entrega não faz

- não recolhe nem arquiva novos bytes;
- não normaliza o catálogo de atividades gerais;
- não cria reuniões a partir de eventos heterogéneos;
- não cria propostas `PENDING`;
- não aprova, publica ou retira votações;
- não altera a matriz pública de cobertura;
- não associa texto livre a pessoas ou partidos;
- não usa IA;
- não afirma cobertura histórica completa.

## Critérios de aceitação

- os mesmos bytes V5.24 podem originar fotografias privadas separadas de iniciativas e votações;
- todos os eventos mantêm fonte, data de recolha e SHA-256;
- IDs repetidos com factos contraditórios falham fechados;
- posições individuais exigem identificador oficial; as restantes ficam `UNKNOWN`;
- limites de eventos e posições impedem lotes inesperados;
- a fotografia é recalculada imediatamente antes da escrita;
- PostgreSQL descartável prova contagens, relações vazias e ausência de publicação;
- nenhuma operação remota é executada por esta entrega.
