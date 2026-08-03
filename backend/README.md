# API Transparência Total / Fator Cívico — V4.1 em desenvolvimento

Serviço FastAPI responsável por descobrir, descarregar, preservar e normalizar fontes oficiais.
Inclui ingestão persistente do Parlamento e pré-visualização BASE JSON/XML/ZIP para JSON privado,
estado de sincronização, projeções públicas, cruzamento exato protegido, resumos DRE, Guia do
Cidadão, direito de resposta e exportações Open Data. A API pública nunca trata uma correspondência
automática, notícia ou resumo de IA como prova.

`sync_parliament.py` dispõe de um circuito próprio de persistência em staging. Na V4.1, a operação
exige `RAW_ARCHIVE_ROOT`: conserva e verifica os bytes exatos antes de abrir a ligação à base de
dados; a transação acrescenta depois `SourceDocument`, `SourceArchiveAttestation`, `AuditEvent` e os
registos normalizados. O recibo de arquivo nunca equivale a revisão ou publicação.
`sync_base_contracts.py` produz apenas o ficheiro JSON privado para revisão e recusa `--persist`
antes de qualquer ligação à base de dados ou criação de `SyncRun`. A persistência BASE só poderá ser
reativada com carga em lote append-only e atestação explícita de staging. A entrada de atores aceita
apenas HMAC e tanto a entrada como a saída privada têm de ficar fora do repositório. Para dados elegíveis,
`review_publication.py` é a fronteira humana explícita: valida dependências, acrescenta revisão e
auditoria e só então torna o registo elegível para `/api/v1/public/*`. Mesmo uma revisão positiva
fica bloqueada se a fonte associada não tiver uma atestação de arquivo exatamente coerente.

## Arquivo privado V4.1

Configure um caminho absoluto fora do repositório apenas num ambiente privado de desenvolvimento,
teste ou staging:

```powershell
$env:ENVIRONMENT = 'staging'
$env:RAW_ARCHIVE_ROOT = 'D:\transparencia-total-private\raw-evidence'
```

Recolher e persistir uma fotografia parlamentar:

```powershell
python -m scripts.sync_parliament votes --legislature XVII --persist
```

Verificar o objeto associado a uma fonte, sem escrever dados:

```powershell
python -m scripts.inspect_source_archive --source-document-id SOURCE_ID
```

Atestar um `SourceDocument` histórico só é permitido em `ENVIRONMENT=staging`, quando o URL efetivo
e os bytes atuais ainda correspondem exatamente ao URL e SHA-256 guardados:

```powershell
python -m scripts.archive_source_document --source-document-id SOURCE_ID --actor operador-auditavel --persist-attestation --confirm-staging
```

O backend local não substitui object storage versionado/WORM em produção. Consulte
[`docs/V4_RAW_EVIDENCE.md`](../docs/V4_RAW_EVIDENCE.md) antes de qualquer operação persistente.

## Rever a fotografia parlamentar em lote

Execute primeiro a pré-visualização, a partir da pasta `backend`:

```powershell
python -m scripts.review_parliament_snapshot --legislature XVII --output ..\data\revisao-deputados-xvii.json
```

Confirme no ficheiro a fonte oficial, o SHA-256, a contagem e a lista de pessoas. A publicação exige
repetir exatamente o SHA-256 e a contagem apresentados na pré-visualização:

```powershell
python -m scripts.review_parliament_snapshot --legislature XVII --publish --source-sha256 SHA256_AQUI --expected-count CONTAGEM_AQUI --reviewer REVISOR_AQUI --rationale "Fonte oficial e identidades verificadas manualmente." --confirm-source-reviewed
```

A operação é transacional e idempotente: cria uma revisão e um evento de auditoria por pessoa ainda
pendente. A aprovação fica vinculada ao documento-fonte exato; uma nova fotografia exige nova
revisão antes de aparecer na API pública.

Consulte o `README.md` da raiz para instalação, configuração e publicação.
