# V5.30 — publicação transacional da fotografia completa de perfis

## Objetivo

A V5.30 acrescenta a primeira porta de publicação de identidades parlamentares ao circuito iniciado
nas V5.27–V5.29. A unidade publicável não é uma pessoa escolhida isoladamente: é a **fotografia
completa** de deputados que já foi arquivada, normalizada, introduzida na fila editorial e aprovada
perfil a perfil por revisão humana.

Esta entrega prepara e testa o código. Não executa uma publicação real, não aplica migrações, não
configura o Supabase, não cria utilizadores ou segredos e não altera dados de staging ou produção.

## Condições obrigatórias

O servidor só disponibiliza uma prova de publicação quando a V5.29 volta a confirmar, para todos os
registos da fotografia:

- URL HTTPS oficial, data de recolha e SHA-256 dos bytes;
- atestação de arquivo coincidente em URL, data e SHA-256;
- contagens materializadas iguais ao manifesto append-only;
- um `DepId` oficial exato, não vazio e não repetido;
- um caso privado `POLITICIAN_PROFILE` com origem `INGESTION`;
- versão atual integralmente reconstruível a partir da observação oficial;
- última decisão `APPROVE`, sobre essa versão, com fonte confirmada;
- ausência de publicação editorial anterior e de revisão pública V4 por reconciliar;
- ausência de identidade incompatível, inativa ou de uma ligação partidária antiga não provada.

Qualquer falha bloqueia toda a fotografia. Uma lista parcial nunca é apresentada ao cidadão como se
fosse a composição completa.

## Confirmação humana separada

A inspeção `GET` é acessível à equipa com MFA e não escreve dados. A operação `POST` exige uma conta
`ADMIN` com `aal2`, fundamentação interna, resumo público e seis confirmações explícitas:

1. fonte e arquivo revistos novamente;
2. fotografia completa confirmada;
3. identidades ligadas apenas pelo `DepId` oficial exato;
4. nenhuma inferência de mandato;
5. nenhuma inferência de filiação partidária;
6. intenção inequívoca de publicar a fotografia inteira.

Os hashes da fonte, fotografia normalizada, prontidão e prova de publicação, bem como a contagem de
deputados, são enviados como condições otimistas. O servidor recalcula-os antes de qualquer escrita;
um valor desatualizado ou alterado causa conflito e recuo integral.

## Projeção pública mínima

Para cada observação, a transação procura uma `Person` exclusivamente pelo mesmo `DepId` oficial
exato. Não usa nome, sigla, distância de edição, som, semelhança ou qualquer *fuzzy matching*.

- Se a identidade exata ainda não existir, cria uma `Person` ativa com função `DEPUTY` e um *slug*
  determinístico derivado por SHA-256, sem expor o `DepId` no endereço público.
- Se existir uma identidade exata compatível, reutiliza-a sem fundir nomes semelhantes.
- Cria ou reutiliza uma `ParliamentaryMembershipSnapshot` para a mesma fonte e legislatura.
- O círculo é conservado como observação da fotografia, com a respetiva fonte e data.
- A V5.30 não cria `Mandate`, não converte situações observadas em datas de mandato e devolve
  explicitamente `mandates_created=0`.
- Mesmo quando a fonte contém períodos e siglas de grupos parlamentares, esta porta não associa
  qualquer partido. `party_id` permanece `NULL` e `party_links_created=0` até existir um adaptador
  próprio baseado num identificador oficial inequívoco.

Assim, “sem filiação indicada” significa dados indisponíveis nesta projeção; não significa ausência
de filiação, incumprimento ou independência política.

## Uma única transação e histórico imutável

Depois de bloquear a fotografia, a fonte, os casos, as identidades e as observações públicas já
existentes, o servidor adquire também o bloqueio da porta parlamentar anterior para impedir que uma
decisão V4 concorra com esta fotografia. Em seguida, acrescenta numa única transação:

- pessoas e observações parlamentares estritamente necessárias;
- uma `DataPublicationReview` positiva por identidade e uma para a fotografia completa;
- um `AuditEvent` por identidade e um para a fotografia;
- uma decisão editorial `PUBLISH` por caso, preservando todas as decisões anteriores;
- um `EditorialPublicationEvent` por perfil e versão exata.

Antes do *commit*, o servidor confirma que a fonte possui exatamente o número esperado de
observações, que cada uma corresponde a uma pessoa distinta e que existem zero ligações partidárias.
Uma alteração concorrente, divergência, colisão de unicidade ou falha intermédia reverte pessoas,
observações, revisões, decisões, auditorias e eventos em conjunto. A publicação nunca é parcialmente
visível.

## Relação com a consulta pública

O diretório público já exigia uma revisão `PERSON` positiva para todas as observações da mesma fonte.
Como a V5.30 acrescenta essas revisões apenas no fim da mesma transação completa, a consulta passa de
zero perfis para a fotografia integral sem uma fase intermédia incompleta. A API continua a mostrar a
fonte, data de recolha, SHA-256 e limitações de cobertura existentes.

## Limites e próxima porta

A publicação de identidade não prova mandato, presença, autoria, voto nominal, declaração de
interesses, cargo atual ou filiação. Cada domínio continua a exigir identificador e fonte próprios,
revisão específica e uma porta de publicação independente.

A etapa seguinte tem de acrescentar retirada e republicação da fotografia completa, também
append-only e não seletivas. A retirada deverá acrescentar revisão negativa, decisão, auditoria e
evento; nunca apagar pessoas, fontes, versões ou a prova de que a fotografia esteve publicada. Até
essa porta existir, a V5.30 não deve ser ativada num ambiente real.

Ingestão, aprovação, migração e deployment nunca chamam esta operação automaticamente.
