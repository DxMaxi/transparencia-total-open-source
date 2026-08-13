# Publicação

## Topologia recomendada

- Vercel: Next.js e CDN.
- Render ou Fly.io: FastAPI.
- Supabase/PostgreSQL gerido: dados normalizados, auditoria e arquivo dos bytes oficiais.
- Object storage versionado: opção futura quando o volume ultrapassar a capacidade PostgreSQL.
- Scheduler/worker: sincronizações, resumos e alertas, separado da API pública.

## Preparação

1. Execute todos os testes.
2. Altere o contacto em `OFFICIAL_USER_AGENT`.
3. Identifique o responsável real nas variáveis legais públicas; não publique placeholders.
4. Crie `ADMIN_API_KEY` aleatória com pelo menos 32 bytes.
5. Documente retenção, capacidade de recuperação e alertas do PostgreSQL. Se o plano não tiver
   backup, registe expressamente esse risco e não anuncie recuperação garantida. Siga o
   [runbook de recuperação](DATABASE_RECOVERY.md) e a
   [configuração Backblaze B2 EU](BACKUP_BACKBLAZE_B2.md); não feche o gate V4 antes de um restauro
   isolado ter sido testado.
6. Não ative IA antes de existir fila de revisão.

## Vercel

1. Importe o repositório GitHub em <https://vercel.com/new>.
2. Escolha Next.js e mantenha a raiz do repositório.
3. O `vercel.json` confirma primeiro a compatibilidade da API pública, compila com
   `npm run build:next` e valida o CSS gerado; não use o comando `npm run build`, reservado ao
   adaptador do preview incluído no projeto.
4. Configure:
   - `NEXT_PUBLIC_API_URL=https://api.example.org`
   - `NEXT_PUBLIC_CONTACT_EMAIL=contacto@seudominio.pt` apenas depois de a caixa institucional
     estar validada e operacional; sem esta variável, o site não publica um email pessoal.
   - `NEXT_PUBLIC_LEGAL_RESPONSIBLE_NAME=…`
   - `NEXT_PUBLIC_LEGAL_ADDRESS=…` (se aplicável)
   - `NEXT_PUBLIC_LEGAL_TAX_ID=…` (se aplicável)
   - `NEXT_PUBLIC_LEGAL_REGISTRATION=…` (se aplicável)
5. Publique e confirme os cabeçalhos de segurança, `robots.txt`, `sitemap.xml` e páginas legais.
6. Adicione os domínios de Production e Preview ao `CORS_ORIGINS` do backend.

### Ordem segura entre API e frontend

Prefira publicar primeiro a API e só depois o frontend. O comando `npm run check:deployment-api` faz
apenas pedidos públicos de leitura. Aceita o contrato completo — capacidades
`parliament_explorer_v1` e `parliament_publication_history_v1` — ou, durante a transição, confirma
todos os caminhos anteriores que servem as mesmas fotografias revistas. Neste segundo modo a
interface fica deliberadamente limitada à consulta sequencial, sem fingir que a pesquisa avançada
está disponível. O Vercel bloqueia o frontend se nenhum dos dois contratos for seguro. Após a
compilação, `npm run verify:next-artifact` confirma que os estilos críticos da atividade parlamentar
e do contacto chegaram efetivamente ao artefacto.

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
- Não existe registo de Service Worker, pedido de notificações ou armazenamento não essencial.
- Registos e caches PWA de versões anteriores são removidos de forma restrita ao projeto.
- Migrações aplicadas e capacidade real de recuperação descrita sem garantias inexistentes.
- Última cópia B2 cifrada e último ensaio de restauro com execução, SHA-256, RPO e RTO registados.
- URLs oficiais, hashes e datas visíveis nos dados reais.
- Dados de demonstração ausentes do domínio oficial.
- Política de correções e contacto público disponíveis.
- Privacidade, cookies, termos/aviso legal e acessibilidade publicados.
