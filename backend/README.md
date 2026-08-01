# API Transparência Total / Fator Cívico — V3

Serviço FastAPI responsável por descobrir, descarregar, preservar e normalizar fontes oficiais.
Inclui ingestão persistente de Parlamento e BASE JSON/XML/ZIP, estado de sincronização, projeções
públicas, cruzamento exato protegido, resumos DRE, Guia do Cidadão, direito de resposta e
exportações Open Data. A API pública nunca trata uma correspondência automática, notícia ou resumo
de IA como prova.

Os scripts `sync_parliament.py` e `sync_base_contracts.py` aceitam `--persist`, mas escrevem apenas
em staging. `review_publication.py` é a fronteira humana explícita: valida dependências, acrescenta
revisão e auditoria e só então torna o registo elegível para `/api/v1/public/*`.

Consulte o `README.md` da raiz para instalação, configuração e publicação.
