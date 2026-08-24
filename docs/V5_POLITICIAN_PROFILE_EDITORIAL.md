# V5.28 — observações de deputados no circuito editorial de perfis

## Objetivo

A V5.28 liga a fotografia privada criada na V5.27 à fila editorial V5 sem transformar recolha em
identidade pública. Um revisor com MFA pode comparar uma observação já separada pelo `DepId`
oficial exato, confirmar a proveniência e criar um processo `POLITICIAN_PROFILE` em `PENDING`.

Esta entrega não recolhe nem publica dados reais, não configura o Supabase, não aplica migrações
remotas e não cria utilizadores. Também não cria `Person`, `Mandate`, filiação partidária,
`DataPublicationReview` ou `EditorialPublicationEvent`.

## Comparador privado

`GET /api/v1/editorial/parliament/deputies` exige uma conta editorial ativa, sessão `aal2` e mostra:

- `DepId` e, quando disponível, o identificador de candidatura exatamente como vieram da fonte;
- nome parlamentar e nome completo observados;
- círculo, grupos, situações e cargos, com os períodos declarados pela Assembleia da República;
- URL oficial, data de recolha, SHA-256 dos bytes, atestação de arquivo e SHA-256 normalizado;
- contagens do manifesto e contagens novamente materializadas;
- anomalias, campos indisponíveis e o processo editorial já existente, quando houver.

A pesquisa limita apenas linhas que já estão separadas pelo `DepId`. Um resultado pelo nome serve
para navegar no painel; não cria, confirma ou aproxima identidades. Não existe correspondência
aproximada, comparação fonética, distância de edição ou associação por sigla.

## Proposta reconstruída no servidor

`POST /api/v1/editorial/parliament/deputy-proposals` recebe apenas:

- o identificador interno da observação;
- confirmação de que a proposta permanece privada;
- confirmação de que só o `DepId` oficial exato pode ancorar a identidade;
- confirmação de que uma observação não prova início, fim ou continuidade de mandato.

Nomes, períodos, fonte, hashes e limitações não vêm do browser. O servidor volta a consultar a
observação append-only, a fotografia, o manifesto, o documento-fonte e a atestação exatos. Depois
reconstrói deterministicamente a versão `politician-profile-editorial-v1`.

Os identificadores técnicos e oficiais são representados nessa versão por SHA-256 de referência.
O valor exato permanece na tabela privada V5.27 e no comparador autenticado, permitindo confirmar a
prova sem confundir um número oficial arbitrário com NIF/NIPC nem duplicar identificadores em JSON
editorial. NIF/NIPC em claro continua proibido; a regra HMAC com pepper não é alterada.

## Intervalos e ausência de dados

Os intervalos oficiais são conservados literalmente. Se o fim for anterior ao início, a V5.28:

1. mantém as duas datas visíveis ao revisor;
2. acrescenta uma anomalia explícita;
3. mantém `mandate_inference_allowed=false`;
4. nunca corrige, troca ou omite silenciosamente uma data.

Um grupo, cargo, círculo ou identificador ausente é apresentado como **dados indisponíveis**. A
ausência não prova que a pessoa não exerceu uma função, não teve mandato ou incumpriu uma obrigação.

## Idempotência e histórico

A chave editorial é a combinação de tipo `POLITICIAN_PROFILE`, assunto
`PARLIAMENT_DEPUTY_OBSERVATION`, observação e documento-fonte. Repetir a mesma proposta e o mesmo
conteúdo é um *no-op*: devolve o caso existente sem acrescentar versão ou decisão. Uma divergência
para a mesma chave é recusada e exige investigar a prova ou introduzir uma nova versão do parser.

A submissão tem origem `INGESTION`, mas a decisão `SUBMIT` identifica o revisor autenticado que a
pediu. As transições posteriores continuam append-only. Mesmo um processo `APPROVED` permanece
privado: aprovação não é publicação e não existe nesta entrega um adaptador de publicação de
perfis.

## Próxima porta

Uma futura publicação de identidade terá de ser implementada como operação de domínio separada e
exigir novamente:

- administrador com MFA;
- fonte e arquivo ainda válidos;
- versão editorial aprovada e hashes coincidentes;
- reconstrução do efeito público antes da escrita;
- criação versionada de identidade/observação sem inferir mandato;
- `DataPublicationReview`, `AuditEvent` e evento editorial imutável na mesma transação;
- confirmação explícita de que não existe publicação automática.

Mandatos, filiações, presenças, iniciativas, votos nominais e declarações mantêm portas próprias.
Nenhum deles pode ser criado apenas porque um perfil foi revisto.
