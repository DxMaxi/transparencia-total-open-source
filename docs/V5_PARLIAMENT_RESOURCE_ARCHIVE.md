# V5.24 — arquivo privado de um recurso parlamentar

## Objetivo

A V5.24 cria o terceiro gate do preenchimento histórico parlamentar. Parte de um único recurso
`PENDING_DOWNLOAD` inventariado pela V5.23, prova novamente a cadeia completa e só então obtém e
arquiva os bytes oficiais. O recurso fica privado e explicitamente não interpretado.

Esta entrega acrescenta código e testes. Não executa o comando em staging ou produção, não toca no
Supabase, não normaliza atividade parlamentar e não altera a matriz pública.

## Cadeia de prova obrigatória

Antes de qualquer pedido HTTP, o operador tem de indicar exatamente:

1. tipo de catálogo e legislatura;
2. formato inventariado (`XML` ou `JSON`);
3. `snapshot_id` do catálogo V5.22;
4. `snapshot_id` do manifesto V5.23;
5. URL integral do recurso.

O repositório exige uma linha com o mesmo manifesto e URL. Confirma `publisher=PARLIAMENT`,
`publishable=false`, o nome versionado do manifesto, a categoria privada integral com o catálogo
pai, a versão do parser V5.23 e uma atestação que repete URL e SHA-256 do HTML arquivado. Depois
revalida também a pasta exata dentro do catálogo V5.22 e a respetiva atestação.

Não existe procura pelo título, nome semelhante, URL parcial, fotografia mais recente ou formato
inferido de outro campo. Uma divergência termina a operação antes do descarregamento.

## Arquivo limitado

O cliente oficial mantém HTTPS, anfitriões parlamentares autorizados, porta padrão, ritmo de
pedidos, timeout e limite de bytes. A operação V5.24 usa o limite parlamentar configurado, atualmente
100 MB por omissão. O URL efetivo tem de continuar exatamente igual ao recurso do manifesto.

Uma resposta HTML é recusada para não guardar uma página de erro como se fosse o ficheiro. O
conteúdo não é analisado: a indicação XML/JSON continua a ser apenas o formato inequívoco do link
oficial. Os bytes não vazios, data UTC, tipo MIME e SHA-256 são preservados no arquivo
content-addressed, no `SourceDocument` e na atestação append-only.

## Estado persistido

O recurso arquivado fica com:

- `ARCHIVED_UNPARSED`;
- `historical_completeness=NOT_ASSERTED`;
- `publishable=false`;
- referência ao `snapshot_id` do manifesto pai;
- zero registos normalizados;
- zero casos editoriais;
- zero publicações ou retiradas.

Repetir exatamente os mesmos bytes e versão valida o snapshot existente; bytes diferentes no mesmo
URL criam uma nova fonte e fotografia, sem substituir o histórico anterior.

## Porta operacional

O comando processa um único URL por execução e exige `ENVIRONMENT=staging`, `DATABASE_URL` e
`--confirm-private-staging`. A prova é feita antes da chamada oficial e repetida imediatamente antes
da persistência. Produção é recusada pela camada de serviço.

Não existe workflow automático, calendário, iteração sobre legislaturas, seleção da versão mais
recente ou continuação silenciosa para outro recurso.

## O que esta entrega não faz

- não interpreta XML ou JSON;
- não conta reuniões, iniciativas, votações, posições ou deputados;
- não associa pessoas, partidos ou temas;
- não compara nomes nem usa correspondência aproximada;
- não cria propostas `PENDING`, revisões ou decisões;
- não publica nem retira dados;
- não afirma completude histórica;
- não usa IA.

Esse gate seguinte está implementado em
[V5.25 — normalização privada de iniciativas parlamentares](V5_PARLIAMENT_RESOURCE_NORMALIZATION.md):
valida o JSON de um único recurso arquivado e produz uma fotografia privada e rejeitável. Qualquer
associação a entidades continua a exigir identificadores oficiais inequívocos; campos sem prova
permanecem como dados indisponíveis.

## Critérios de aceitação

- nenhum pedido ao recurso ocorre sem catálogo e manifesto pais exatos e atestados;
- o URL e o formato têm correspondência exata com a linha privada do manifesto;
- a descarga tem limite e recusa redirecionamentos ou HTML inesperado;
- bytes, URL, data, MIME e SHA-256 ficam preservados de forma append-only;
- o estado é `ARCHIVED_UNPARSED`, `NOT_ASSERTED` e `publishable=false`;
- zero registos são normalizados e zero casos editoriais são criados;
- testes unitários e PostgreSQL descartável exercitam toda a cadeia.
