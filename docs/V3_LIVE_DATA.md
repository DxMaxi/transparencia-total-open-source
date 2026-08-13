# V3 — circuito de dados reais

## Invariantes

1. Recolher não publica.
2. “Observado em” não significa “mandato iniciado em”.
3. Um voto só é nominal quando a fonte fornece identificador individual e este corresponde
   exatamente a uma pessoa recolhida.
4. Uma relação só é pública quando os dois nós e a aresta estão verificados e publicados.
5. Retirar um registo acrescenta uma decisão; não apaga a decisão anterior.
6. Se a API falhar, a PWA muda para `UNAVAILABLE`; não conserva silenciosamente a aparência de
   atualização em tempo real.
7. Na V4.1, nenhuma fonte derivada é publicável sem objeto bruto atestado com o mesmo URL e
   SHA-256; arquivo não equivale a revisão.

## Estados

```mermaid
stateDiagram-v2
  [*] --> Archived: bytes exatos + SHA-256
  Archived --> Ingested: atestação + normalização
  Ingested --> UnderReview: staging
  UnderReview --> Published: revisão humana
  UnderReview --> Rejected: prova insuficiente
  Published --> Withdrawn: nova decisão
  Withdrawn --> Published: nova revisão
```

Os nomes exatos variam por modelo, mas a fronteira é a mesma. `PERSON` e `PROMISE` são filtrados
pela última revisão; contratos, entidades e relações exigem também `VERIFIED` + `PUBLISHED`.

## Operação mínima

```bash
cd backend
python -m scripts.sync_parliament deputies --legislature XVII --persist
python -m scripts.sync_parliament_activity --legislature XVII
python -m scripts.sync_base_contracts \
  --year 2026 --output /caminho/privado/base-review.json
```

O exemplo BASE acima é apenas uma pré-visualização. Uma persistência autorizada exige um destino
privado fora do repositório, `ENVIRONMENT=staging`, `RAW_ARCHIVE_ROOT`, `--persist` e
`--confirm-staging`; consulte `V4_BASE_STAGING.md` antes da operação.

Nas sincronizações parlamentares, confirme primeiro o destino de `DATABASE_URL`. A V4 guarda os
bytes novos no arquivo PostgreSQL. Inspecione o documento, a atestação, os dois hashes, contagens e
avisos com `scripts.review_parliament_activity`; esse mesmo comando publica ou retira atividade e
votos com confirmação explícita.

Use `python -m scripts.inspect_source_archive --source-document-id SOURCE_ID` para verificar
metadados, tamanho e SHA-256 sem ler o conteúdo para a saída e sem escrever na base de dados.

`inspect_parliament_votes` permanece apenas para fotografias legadas. O caminho V4 é versionado,
idempotente e append-only. Tanto o perfil como o modo Investigador exigem a última revisão positiva
ligada exatamente ao manifesto da fotografia do voto.

O comando BASE produz sempre um JSON privado de pré-visualização/revisão. Na V4.2, `--persist` só é
aceite com confirmação explícita de staging, snapshot completo e arquivo prévio. A carga cria
`BaseStagingBatch`, `BaseContractSnapshot` e `BaseContractPartySnapshot`, todos append-only, mas não
cria entidades ou contratos públicos. Use `python -m scripts.inspect_base_staging --year 2026`
para verificar a fonte, o SHA-256, as contagens e os avisos sem devolver nomes ou HMAC.

## Projeções públicas

| Projeção | Porta de publicação |
|---|---|
| Identidade do perfil | fonte arquivada + última `DataPublicationReview(PERSON)` publicável + fotografia oficial |
| Mandatos no perfil | fonte oficial não noticiosa arquivada + última `DataPublicationReview(MANDATE)` positiva |
| Presenças no perfil | fotografia de atividade publicada + mandato individual revisto e arquivado |
| Votos no perfil | fonte arquivada + normalizador V5 + pessoa por ID oficial, `actorType=PERSON`, votação nominal, escolha conhecida + última revisão positiva da mesma fotografia |
| Declarações no perfil | metadado individual EPT arquivado + revisão jurídica confirmada + última `DataPublicationReview(ASSET_DECLARATION)` positiva |
| Promessas | fontes do programa/evidência arquivadas + estado verificável + última `PromiseReview=ACCEPT` |
| Contratos | fonte arquivada + `verificationStatus=VERIFIED` e `publicationStatus=PUBLISHED` |
| Grafo | fonte arquivada + aresta e ambos os nós verificados/publicados |
| Comparações | fontes arquivadas + par comparável, verificado, publicado e voto nominal da mesma pessoa |

## Limitação deliberada

A V4.2 não transforma automaticamente snapshots BASE em relações de interesse. A persistência cria
apenas um lote privado e o respetivo `SyncRun`; não cria `PublicContract`, organizações, nós,
candidatos ou arestas. Correspondências e relações exigem prova adicional e revisão editorial.
Esta limitação evita converter coincidências de nomes ou papéis contratuais em acusações.
