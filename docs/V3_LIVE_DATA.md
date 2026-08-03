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

## Estados

```mermaid
stateDiagram-v2
  [*] --> Ingested: coletor
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
python -m scripts.sync_parliament votes --legislature XVII --persist
python -m scripts.sync_base_contracts --year 2026 --output ../data/base-review.json
```

Nas sincronizações parlamentares, inspecione o documento, o hash, as contagens e os avisos em
`source_documents` e `sync_runs`. `scripts.review_publication --confirm-source-reviewed` aplica-se
apenas aos tipos de entidade explicitamente suportados; não existe nesta versão um comando para
aprovar uma fotografia de votações.

Para a fotografia de votações, use `python -m scripts.inspect_parliament_votes --legislature XVII`.
O comando é exclusivamente de leitura e nunca cria uma decisão. Até existir versionamento
append-only, a primeira fotografia usa apenas inserções e uma segunda persistência de votos é
recusada antes de alterar eventos ou posições. Tanto o perfil como o modo Investigador exigem a
última revisão positiva ligada exatamente ao documento-fonte do voto.

O comando BASE produz apenas um JSON privado de pré-visualização/revisão. Nesta versão,
`--persist` é recusado antes de qualquer ligação à base de dados ou criação de `SyncRun`; a
persistência só poderá ser reativada com carga em lote append-only e atestação explícita de
staging. Para BASE, inspecione a fonte, o SHA-256, as contagens e os avisos no próprio JSON.

## Projeções públicas

| Projeção | Porta de publicação |
|---|---|
| Perfis | última `DataPublicationReview(PERSON)` publicável + snapshot oficial |
| Votos no perfil | pessoa por ID, `actorType=PERSON`, votação nominal, escolha conhecida + última revisão positiva da mesma fotografia |
| Promessas | estado verificável + evidência + última `PromiseReview=ACCEPT` |
| Contratos | `verificationStatus=VERIFIED` e `publicationStatus=PUBLISHED` |
| Grafo | aresta e ambos os nós verificados/publicados |
| Comparações | par comparável, verificado, publicado e voto nominal da mesma pessoa |

## Limitação deliberada

A V3 não transforma automaticamente contratos BASE em relações de interesse. A pré-visualização
cria apenas um ficheiro JSON privado; não cria contratos, organizações, nós ou `SyncRun` na base de
dados. Correspondências e arestas exigem prova adicional e revisão editorial. Esta limitação evita
converter coincidências de nomes ou papéis contratuais em acusações.
