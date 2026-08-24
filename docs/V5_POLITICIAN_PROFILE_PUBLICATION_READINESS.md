# V5.29 — prontidão de publicação dos perfis por fotografia completa

## Objetivo

A V5.29 acrescenta uma porta privada e estritamente *read-only* entre a aprovação editorial de
cada observação de deputado e uma futura publicação de identidades. A porta responde a uma
pergunta limitada: **todos os registos da mesma fotografia oficial estão íntegros, aprovados e
ligados à prova exata?**

Uma resposta positiva não publica nada. Não cria ou altera `Person`, `Mandate`, pertenças
parlamentares, revisões públicas, decisões ou eventos. A aprovação individual continua privada.

## Porque a fotografia inteira é obrigatória

Uma lista parcial pode ser tecnicamente verdadeira e, ainda assim, induzir o cidadão a pensar que
está perante a composição completa. Por isso, a prontidão fica bloqueada quando existir pelo menos:

- uma observação em falta face ao manifesto imutável;
- um processo `POLITICIAN_PROFILE` inexistente ou ainda não `APPROVED`;
- uma versão cujo JSON não coincide com o próprio SHA-256;
- uma aprovação que não pertence à versão atual ou não confirma a fonte;
- uma versão que diverge da reconstrução determinística da observação oficial;
- um arquivo que não coincide simultaneamente em URL, data de recolha e SHA-256;
- um `DepId` vazio ou repetido;
- uma publicação editorial inesperada ou uma decisão pública antiga ainda por reconciliar;
- uma identidade inativa ou uma ligação partidária antiga sem identificador oficial verificável.

Na entrega V5.29, o painel mostrava apenas contagens, bloqueios e progresso. A V5.30 conserva esta
inspeção read-only e acrescenta, numa secção separada, a ação explícita que só aparece quando a
fotografia inteira está pronta e a sessão pertence a um administrador com MFA.

## Identidade exata e ausência de inferências

As observações já foram separadas pelo `DepId` fornecido pela Assembleia da República. A V5.29
apenas verifica esse conjunto e procura uma `Person` existente pelo mesmo identificador oficial
exato. Nomes, siglas, cargos e círculos nunca são usados para ligar identidades. O circuito opera
sem correspondência aproximada, fonética ou por distância de edição.

Uma observação continua sem provar início, fim ou continuidade de mandato. A porta devolve
`mandate_inference_allowed=false` e não escreve em `mandates`. Campos ausentes ou fotografias
inexistentes aparecem como **dados indisponíveis**, nunca como incumprimento ou ocultação.

## Reconstrução e prova de prontidão

Para cada observação, o servidor volta a construir o contrato
`politician-profile-editorial-v1` a partir das tabelas append-only V5.27. A versão atual só conta
como pronta quando coincide integralmente com essa reconstrução, incluindo:

- referências SHA-256 da observação, fotografia, documento e `DepId`;
- URL oficial, data de recolha, SHA-256 dos bytes e atestação de arquivo;
- SHA-256 normalizado e versão do parser;
- contagens do manifesto e materializadas;
- regra `EXACT_AR_DEP_ID_ONLY` e proibição explícita de inferir mandato.

Quando não existe qualquer bloqueio, o servidor deriva um `readiness_proof_sha256` do conjunto
ordenado de versões aprovadas, dos hashes da fonte e da fotografia, das contagens e da projeção de
identidades exatas. O hash é apenas uma prova privada para a porta seguinte; não é uma decisão de
publicação.

## Reconciliação com a V4

O projeto conserva pessoas, pertenças e revisões criadas pelo circuito anterior. Qualquer decisão
`PERSON` ligada à mesma fonte bloqueia esta porta com
`LEGACY_PUBLICATION_REQUIRES_RECONCILIATION`. A V5 não apaga nem ignora esse histórico. Uma futura
adaptação terá de o reconciliar explicitamente, sem duplicar identidades e sem fabricar um evento
editorial retroativo.

## Porta seguinte implementada na V5.30

A publicação efetiva foi implementada numa operação separada que:

1. aceite apenas um administrador autenticado com MFA;
2. volte a calcular o `readiness_proof_sha256` antes das escritas da transação;
3. trabalhe sobre a fotografia inteira e por `DepId` oficial exato;
4. não crie mandatos, filiações jurídicas ou relações individuais não provadas;
5. acrescente `DataPublicationReview`, `AuditEvent` e `EditorialPublicationEvent` imutáveis;
6. recue integralmente se qualquer perfil, hash, contagem ou decisão mudar;
7. nunca seja acionada por ingestão, aprovação, migração ou deployment.

O desenho, os efeitos mínimos e os limites dessa operação estão documentados em
[V5.30 — publicação transacional da fotografia completa](V5_POLITICIAN_PROFILE_SNAPSHOT_PUBLICATION.md).

Esta entrega não executa migrações, não configura Supabase ou segredos, não recolhe dados reais e
não publica nem retira qualquer registo.
