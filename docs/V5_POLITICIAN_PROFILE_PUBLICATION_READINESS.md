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
- uma publicação editorial inesperada ou uma revisão pública antiga ainda por reconciliar.

O painel mostra contagens, bloqueios e progresso. Não apresenta um botão de publicação.

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

O projeto conserva pessoas, pertenças e revisões criadas pelo circuito anterior. Uma revisão
`PERSON` positiva ligada à mesma fonte bloqueia esta porta com
`LEGACY_PUBLICATION_REQUIRES_RECONCILIATION`. A V5 não apaga nem ignora esse histórico. Uma futura
adaptação terá de o reconciliar explicitamente, sem duplicar identidades e sem fabricar um evento
editorial retroativo.

## Próxima porta

A publicação efetiva continuará a exigir uma operação separada que:

1. aceite apenas um administrador autenticado com MFA;
2. volte a calcular o `readiness_proof_sha256` dentro da transação;
3. trabalhe sobre a fotografia inteira e por `DepId` oficial exato;
4. não crie mandatos, filiações jurídicas ou relações individuais não provadas;
5. acrescente `DataPublicationReview`, `AuditEvent` e `EditorialPublicationEvent` imutáveis;
6. recue integralmente se qualquer perfil, hash, contagem ou decisão mudar;
7. nunca seja acionada por ingestão, aprovação, migração ou deployment.

Esta entrega não executa migrações, não configura Supabase ou segredos, não recolhe dados reais e
não publica nem retira qualquer registo.
