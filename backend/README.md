# API Transparência Total / Fator Cívico — V3

Serviço FastAPI responsável por descobrir, descarregar, preservar e normalizar fontes oficiais.
Inclui ingestão persistente do Parlamento e pré-visualização BASE JSON/XML/ZIP para JSON privado,
estado de sincronização, projeções públicas, cruzamento exato protegido, resumos DRE, Guia do
Cidadão, direito de resposta e exportações Open Data. A API pública nunca trata uma correspondência
automática, notícia ou resumo de IA como prova.

`sync_parliament.py` dispõe de um circuito próprio de persistência em staging.
`sync_base_contracts.py` produz apenas o ficheiro JSON privado para revisão e recusa `--persist`
antes de qualquer ligação à base de dados ou criação de `SyncRun`. A persistência BASE só poderá ser
reativada com carga em lote append-only e atestação explícita de staging. A entrada de atores aceita
apenas HMAC e tanto a entrada como a saída privada têm de ficar fora do repositório. Para dados elegíveis,
`review_publication.py` é a fronteira humana explícita: valida dependências, acrescenta revisão e
auditoria e só então torna o registo elegível para `/api/v1/public/*`.

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
