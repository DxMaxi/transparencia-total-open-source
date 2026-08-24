# V5.25 — normalização privada de iniciativas parlamentares

## Objetivo

A V5.25 cria o quarto gate do preenchimento histórico parlamentar e o primeiro que interpreta um
recurso arquivado. O âmbito inicial é deliberadamente estreito: um único ficheiro JSON de iniciativas
de uma legislatura. Os bytes têm de existir no arquivo PostgreSQL criado pela V5.24 e toda a cadeia
V5.22 → V5.23 → V5.24 é revalidada antes de qualquer normalização.

Esta entrega acrescenta código e testes. Não executa o comando em staging ou produção, não toca no
Supabase, não cria casos editoriais e não altera a projeção pública.

## Prova dos bytes

O operador fornece os três `snapshot_id` exatos — catálogo, manifesto e arquivo — e o URL integral
do recurso. O repositório exige simultaneamente:

- fotografia V5.24 privada, parlamentar e com versão de parser reconhecida;
- categoria integral que aponta para o manifesto indicado;
- `SourceDocument`, atestação PostgreSQL e objeto content-addressed com o mesmo URL e SHA-256;
- chave de arquivo `sha256/<prefixo>/<sha256>` exata;
- tamanho declarado igual aos bytes realmente lidos;
- manifesto e catálogo pais novamente válidos e atestados.

Não é feita nova chamada à Assembleia da República. A V5.25 interpreta apenas os bytes imutáveis já
arquivados, tornando a execução reprodutível.

## Contrato de normalização

Nesta fase apenas `catalogue=INITIATIVES` e `format=JSON` são aceites. O conteúdo tem de ser JSON
UTF-8 válido e conter um objeto ou lista. Uma iniciativa só entra quando a fonte fornece de forma
explícita:

- identificador oficial da iniciativa;
- número;
- tipo;
- título.

Datas, fase, descrição e ligação são conservadas quando existem. A ligação tem de usar HTTPS e um
anfitrião parlamentar autorizado. Não se procuram nomes semelhantes, não se associa autoria, pessoa,
partido ou tema e não se inventa estado ausente.

Se o mesmo `source_id` aparecer com normalizações divergentes, o lote inteiro é recusado. Repetições
idênticas são deduplicadas. O limite é 50 000 iniciativas por recurso.

## Verificação antes da escrita

Imediatamente antes de persistir, o serviço volta a carregar e a provar os bytes, repete a
normalização e exige igualdade integral com a fotografia proposta em memória. Uma alteração entre
interpretação e escrita, ou uma fotografia construída manualmente que não resulte dos bytes, é
recusada.

A persistência reutiliza a fotografia parlamentar append-only e acrescenta um `SyncRun` com estado
`PARTIAL`, porque apenas um âmbito e um recurso foram observados. O resultado conserva:

- parser `parliament-historical-initiatives-v1`;
- `historical_completeness=NOT_ASSERTED`;
- zero sessões, votações e posições;
- zero casos editoriais;
- zero eventos de publicação;
- `publishable=false`.

Uma correção do parser exige nova versão e nunca substitui a fotografia anterior.

## Porta operacional

O comando exige `ENVIRONMENT=staging`, `DATABASE_URL`, os três identificadores de fotografia, URL e
`--confirm-private-staging`. Produção é recusada. Não existe workflow automático, calendário,
iteração entre ficheiros ou continuação implícita para outra legislatura.

## O que esta entrega não faz

- não cria proposta editorial `PENDING`;
- não aprova, publica ou retira iniciativas;
- não normaliza reuniões, votações, posições ou deputados;
- não atribui iniciativas a pessoas ou partidos;
- não usa fuzzy matching;
- não afirma que o recurso contém todas as iniciativas da legislatura;
- não usa IA.

O gate seguinte está definido em
[V5.26 — normalização privada de votações parlamentares](V5_PARLIAMENT_VOTE_NORMALIZATION.md).
Ele deriva uma fotografia de votações separada dos mesmos bytes, mantendo cada tipo e legislatura
em lotes independentes. Atividades gerais e atividade individual dos deputados continuam por
modelar; não são forçadas para este esquema. Só depois de comparar manifestos e rever a cobertura
poderá ser criada uma proposta editorial privada.

## Critérios de aceitação

- a normalização só lê bytes content-addressed e atestados;
- a cadeia catálogo → manifesto → arquivo é revalidada duas vezes;
- JSON inválido, URLs externos e IDs duplicados divergentes falham fechados;
- todos os registos mantêm URL, data de recolha e SHA-256 da fonte;
- a fotografia é recalculada antes da escrita;
- o `SyncRun` declara cobertura parcial e `NOT_ASSERTED`;
- nenhuma revisão ou publicação é criada;
- testes unitários e PostgreSQL descartável exercitam a cadeia completa.
