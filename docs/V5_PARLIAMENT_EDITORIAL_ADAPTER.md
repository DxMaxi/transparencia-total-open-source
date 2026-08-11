# V5.2 — adaptação parlamentar ao circuito editorial

## Estado desta entrega

Esta fatia liga as fotografias parlamentares imutáveis da V4 à fila privada da V5. Não altera a
projeção pública, não substitui as decisões V4 existentes e não acrescenta qualquer endpoint de
publicação. O resultado de uma importação é sempre um `EditorialCase` em `PENDING`.

## Percurso implementado

1. Um revisor autenticado com MFA consulta fotografias da Assembleia da República já arquivadas e
   atestadas.
2. O backend volta a contar reuniões observadas, iniciativas, votações e posições e compara esses
   valores com o manifesto imutável do snapshot.
3. Quando existe uma fotografia anterior atestada da mesma legislatura, o backend compara registos
   apenas pelo `source_id` oficial exato e apresenta totais adicionados, removidos, alterados e
   inalterados.
4. O painel mostra separadamente cobertura nominal, ligações inequívocas a pessoas/partidos,
   posições `UNKNOWN`, sentidos `UNKNOWN` e votações sem posições normalizadas.
5. O revisor escolhe um único âmbito: `activity` ou `votes`. O browser envia apenas o identificador
   do snapshot, o âmbito e duas confirmações explícitas; não pode fornecer nem alterar o JSON
   normalizado.
6. O backend reconstrói a proposta a partir das tabelas append-only e cria uma versão de origem
   `INGESTION`. `created_by_id` permanece nulo; a decisão `SUBMIT` é atribuída ao membro da equipa
   que autorizou a entrada na fila.
7. Repetir a mesma importação devolve o processo existente sem criar outra versão ou decisão.

## Prova e bloqueios

Uma fotografia só aparece como candidata quando:

- pertence ao publicador `PARLIAMENT`;
- tem URL HTTPS;
- não é classificada como notícia;
- URL, data de recolha e SHA-256 coincidem com uma `SourceArchiveAttestation`;
- existe como `ParliamentActivitySnapshot` imutável.

A criação da proposta falha fechada se as quatro contagens materializadas divergirem do manifesto.
A atestação escolhida é a primeira atestação válida da fonte, por ordem de arquivo, para manter a
âncora da proposta estável caso o mesmo objeto seja copiado posteriormente para outro arquivo.

## Neutralidade e correspondências

- A diferença entre snapshots usa igualdade exata de `source_id`; não existe *fuzzy matching*.
- Uma posição de grupo parlamentar nunca é apresentada como voto individual.
- Um registo `PERSON` só conta como ligado quando já possui `person_id` persistido pelo circuito
  oficial; o adaptador não procura nomes nem cria ligações.
- Rótulos individuais ou coletivos não são copiados para o resumo editorial agregado.
- Campos ausentes, atores desconhecidos e sentidos desconhecidos permanecem explícitos.
- Nenhuma contagem de ausência é interpretada como incumprimento, intenção ou juízo político.

## Endpoints privados

- `GET /api/v1/editorial/parliament/snapshots`
- `POST /api/v1/editorial/parliament/proposals`

Ambos exigem JWT Supabase válido, conta `staff_profiles` ativa e `aal2`. As tabelas editoriais
continuam sem privilégios para `PUBLIC`, `anon` e `authenticated`; o browser só comunica com a API
privada.

## Dados normalizados da proposta

Cada versão guarda:

- versão do contrato `parliament-editorial-v1` e âmbito proposto para revisão;
- legislatura, SHA-256 de referência do snapshot, parser e SHA-256 normalizado;
- URL oficial, data de recolha, SHA-256 da fonte e SHA-256 da atestação;
- quatro contagens do manifesto e métricas agregadas de cobertura;
- diferenças agregadas face à fotografia anterior, quando ela existe;
- limitações aplicáveis;
- estado explícito `PRIVATE_PENDING_REVIEW`, publicação automática desativada e revisão humana
  obrigatória.

Os identificadores exatos do snapshot e do documento-fonte permanecem nas colunas relacionais do
processo editorial. O JSON normalizado não os duplica: guarda os respetivos SHA-256 de referência,
evitando que uma sequência numérica fortuita dentro de um identificador técnico seja confundida
com um NIF/NIPC em claro sem enfraquecer a validação de dados protegidos.

## Fora do âmbito

Esta entrega não:

- aplica migrações remotas nem configura o Supabase;
- cria administradores ou revisores;
- publica, retira ou altera fotografias públicas;
- converte uma aprovação privada numa decisão V4 de `DataPublicationReview`;
- cria explicadores por IA;
- liga votos a pessoas ou partidos;
- reorganiza ainda a página pública de atividade parlamentar.

O passo seguinte deverá criar o adaptador de publicação específico por âmbito. Só poderá operar
sobre um processo `APPROVED`, exigirá função `ADMIN`, nova confirmação da fonte e acrescentará no
mesmo commit transacional a decisão `PUBLISH`, um `EditorialPublicationEvent` e a projeção pública
correspondente. Essa operação continua separada desta V5.2.
