# Publicação

## Topologia recomendada

- Vercel: Next.js PWA e CDN.
- Render ou Fly.io: FastAPI.
- PostgreSQL gerido: dados normalizados, auditoria e push.
- Object storage privado e versionado/WORM: documentos brutos; obrigatório antes de produção real.
- Scheduler/worker: sincronizações, resumos e alertas, separado da API pública.

## Preparação

1. Execute todos os testes.
2. Altere o contacto em `OFFICIAL_USER_AGENT`.
3. Gere VAPID e guarde a chave privada num gestor de segredos.
4. Crie `ADMIN_API_KEY` aleatória com pelo menos 32 bytes.
5. Defina backups, retenção e alertas do PostgreSQL.
6. Não ative IA antes de existir fila de revisão.
7. Não ative a V4.1/V4.2 em produção até existir um backend externo de arquivo e todas as fontes
   publicadas estarem atestadas e verificadas.

## Porta de implantação V4.1/V4.2

`RAW_ARCHIVE_ROOT` configura apenas o backend local de desenvolvimento, testes e staging
controlado. Não o aponte para o sistema de ficheiros efémero do Render, Fly.io, Vercel, CI ou para
uma pasta servida pela aplicação. O caminho tem de ser absoluto, privado e exterior ao
repositório.

As projeções públicas recusam qualquer facto cuja fonte não tenha uma atestação coerente. Os
snapshots BASE da V4.2 são adicionalmente privados, append-only e sem promoção pública automática.
Aplicar a migração e publicar o código antes de arquivar as fontes históricas pode, por desenho,
fazer os dados atuais passar para `EMPTY`/`UNAVAILABLE`. Isso é preferível a mostrar prova não
conservada, mas exige um rollout deliberado:

1. implementar o adaptador de object storage privado com versionamento ou retenção WORM;
2. ensaiar a migração e os triggers numa cópia restaurável da base;
3. arquivar cada `SourceDocument` histórico apenas quando os bytes ainda coincidirem exatamente;
4. tratar fontes alteradas como novas versões, nunca como substituições do documento anterior;
5. executar `inspect_source_archive` e reconciliar contagens, hashes e objetos indisponíveis;
6. executar `inspect_base_staging` para cada ano BASE carregado, sem exportar nomes ou HMAC;
7. implementar e rever separadamente a promoção humana BASE antes de expor qualquer contrato;
8. só depois promover a versão da API, mantendo as revisões humanas como circuito independente.

Enquanto estes passos não forem concluídos, a V4.1/V4.2 deve permanecer fora de produção.

## Vercel

1. Importe o repositório GitHub em <https://vercel.com/new>.
2. Escolha Next.js e mantenha a raiz do repositório.
3. O `vercel.json` fixa `npm run build:next`; não use o comando `npm run build`, reservado ao
   adaptador do preview incluído no projeto.
4. Configure:
   - `NEXT_PUBLIC_API_URL=https://api.example.org`
   - `NEXT_PUBLIC_VAPID_PUBLIC_KEY=…`
5. Publique, confirme `/manifest.json`, `/sw.js` e os cabeçalhos do Service Worker.
6. Adicione os domínios de Production e Preview ao `CORS_ORIGINS` do backend.

## Render

O `render.yaml` define um serviço Python e PostgreSQL. Crie um Blueprint, preencha variáveis marcadas
como `sync: false` e aguarde o endpoint de saúde.

O serviço FastAPI não deve executar migrações concorrentes no arranque. Aplique-as uma vez:

```bash
DATABASE_URL='URL externa do Render' npm run db:deploy
```

Depois, atualize `NEXT_PUBLIC_API_URL` no Vercel. Em planos gratuitos, espere suspensão por
inatividade e retenção reduzida do PostgreSQL; não os trate como arquivo oficial durável.

## Fly.io

1. Instale e autentique `flyctl`.
2. Copie `fly.toml.example` para `fly.toml` e escolha nome único.
3. Crie/associe PostgreSQL ou forneça um URL TLS externo.
4. Grave segredos com `fly secrets set`.
5. Execute `fly deploy` a partir da raiz; o Dockerfile copia apenas o backend.
6. Confirme que a aplicação escuta `0.0.0.0:8080` e que o health check passa.

## Sincronização agendada

Não execute scraping pesado num pedido do utilizador. Use cron/worker e um bloqueio distribuído.
Frequência inicial sugerida:

- catálogos AR: uma vez por dia;
- documentos novos DRE: conforme feed oficial, com deduplicação por hash;
- EPT e fontes locais: frequência publicada pelo organismo, nunca agressiva;
- reprocessamento IA: apenas conteúdo novo ou prompt/modelo alterado.

Uma falha deve marcar `SyncRun=FAILED/PARTIAL`, alertar a equipa e manter a última versão válida.

## Checklist pós-publicação

- HTTPS e redirecionamento ativo em frontend e API.
- CORS contém apenas origens reais.
- Swagger/ReDoc desativados em produção.
- PWA instalável em Android e iOS; offline testado.
- Push testado com subscrição, envio e remoção.
- Migrações aplicadas e backups restauráveis testados.
- URLs oficiais, hashes e datas visíveis nos dados reais.
- Dados de demonstração removidos ou mantidos numa rota explicitamente separada.
- Política de correções e contacto público disponíveis.
