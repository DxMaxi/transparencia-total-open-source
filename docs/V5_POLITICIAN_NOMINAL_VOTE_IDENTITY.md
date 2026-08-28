# V5.45 — prova persistida de identidade em votos nominais

## Resultado

A V5.45 fecha a associação entre uma posição nominal e uma pessoa sem usar o nome apresentado na
fonte. O identificador oficial que levou o normalizador a classificar uma posição como `PERSON`
passa a ser guardado em `vote_records.actor_source_id`. A ficha pública só aceita a relação quando
esse valor coincide exatamente com `people.source_id`.

Uma posição coletiva continua a pertencer à consulta parlamentar. Nunca é transformada em voto de
uma pessoa, mesmo quando o rótulo contém o nome de um partido, uma sigla ou um nome semelhante.

## Nova versão, sem backfill

A migração acrescenta uma coluna anulável e índices de prova. Não preenche nem atualiza linhas
anteriores. O trigger append-only já existente em `vote_records` continua a impedir `UPDATE` e
`DELETE`.

As correções usam novas fotografias imutáveis:

- `parliament-activity-v6` para a recolha parlamentar corrente;
- `parliament-historical-votes-v2` para recursos históricos arquivados.

Fotografias de versões anteriores podem conservar valor de arquivo, mas não provam a associação
individual exigida pela V5.45. Têm de ser novamente normalizadas a partir dos mesmos bytes
content-addressed, revistas e publicadas como uma nova versão; nunca são reescritas.

## Validação privada

Durante a persistência, cada posição `PERSON` tem de conservar um `actor_source_id`. Se já existir
uma ligação privada a `people`, o mesmo identificador tem de coincidir exatamente com
`people.source_id`. Uma divergência faz a transação falhar.

O painel editorial passa a separar:

- posições `PERSON` com identificador oficial preservado;
- identificadores oficiais ainda sem pessoa exata disponível;
- posições antigas sem prova persistida;
- ligações privadas cujo identificador diverge.

As duas últimas situações bloqueiam a publicação do âmbito `votes`. A ausência de uma pessoa local
para um identificador oficial não cria uma correspondência: permanece uma lacuna privada até existir
identidade oficial revista.

## Publicação e retirada já existentes

Esta correção não cria uma porta de publicação paralela. A separação entre ingestão, revisão e
publicação já é feita por:

1. proposta `PENDING` do âmbito `votes` na V5.2;
2. aprovação humana explícita;
3. publicação `ADMIN` com MFA e prova transacional na V5.3;
4. retirada append-only de toda a fotografia na V5.4.

A V5.45 fortalece a prova reconstruída por esses gates. Uma ingestão ou a existência da nova coluna
continua sem publicar qualquer voto.

## Projeção pública

A ficha política exige cumulativamente:

1. fotografia `PARLIAMENT_VOTES_SNAPSHOT` com última revisão positiva;
2. fonte parlamentar oficial, arquivo atestado, URL, data de recolha e SHA-256 coincidentes;
3. parser `parliament-activity-v6` ou `parliament-historical-votes-v2`;
4. votação marcada como nominal;
5. posição `PERSON` com sentido conhecido;
6. `vote_records.person_id` igual à pessoa da ficha;
7. `vote_records.actor_source_id = people.source_id`.

O Investigador Cívico e comparações entre declaração e voto usam a mesma igualdade exata. Sem todos
estes elementos, a resposta é `dados indisponíveis`; não se conclui que a pessoa não votou.

## Limites operacionais

- não executa migração em staging ou produção;
- não recolhe nem publica dados reais;
- não cria pessoas ou filiações;
- não usa fuzzy matching, nome, sigla ou grupo como chave de identidade;
- não transforma posição partidária em voto individual;
- não usa IA como fonte nem produz recomendação política;
- não afirma cobertura histórica completa.

O código pode ser integrado antes da migração sem quebrar a consulta pública existente. As leituras
públicas acedem ao novo atributo através da representação JSONB da linha: num esquema anterior o
atributo é simplesmente ausente e nenhuma identidade é projetada. A recolha parlamentar diária
confirma primeiro, apenas por leitura do catálogo PostgreSQL, a coluna, a restrição e o índice da
V5.45. Enquanto essa prova não existir, termina com `SCHEMA_MIGRATION_REQUIRED`, não contacta a
fonte oficial, não cria `SyncRun` e não escreve dados. Depois da migração controlada, a mesma recolha
retoma com `parliament-activity-v6`.

A ordem operacional continua a ser: CI, migração e inspeção em staging, decisão explícita de
promoção do esquema, migração de produção e só depois nova recolha privada. Nenhum destes passos
aprova ou publica uma fotografia.

O ensaio de integração usa PostgreSQL 17 descartável. A fonte oficial, o arquivo, a normalização
histórica e os limites de cobertura permanecem documentados em
[V5.26 — normalização privada de votações históricas](V5_PARLIAMENT_VOTE_NORMALIZATION.md).
