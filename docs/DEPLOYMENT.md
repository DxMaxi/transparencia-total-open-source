# Publicação

## Instalação existente e estado da V5

A instalação deste projeto usa Vercel, API Render e PostgreSQL/Auth Supabase. O `render.yaml`
é uma alternativa para uma instalação nova com PostgreSQL Render; não representa a base existente
e não deve ser aplicado para substituir a ligação Supabase de produção. Fly.io é outra alternativa.
Consulte o [índice documental](README.md) e a [checklist V5](V5_RELEASE_CHECKLIST.md) antes de
anunciar uma versão pública concluída. Um deployment saudável não fecha os requisitos editoriais.

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
   Esta chave serve apenas operações legadas que ainda a aceitem. O painel V5 exige Supabase Auth,
   convite, perfil staff ativo, função autorizada e MFA `aal2`. Configure o URL público e o redirect
   exato de confirmação no Auth; o responsável configura o seu segundo fator diretamente.
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
   - `NEXT_PUBLIC_SUPABASE_URL=…` para o projeto Auth autorizado.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=…` (chave publicável, nunca `service_role` ou segredo).
   - `NEXT_PUBLIC_VAPID_PUBLIC_KEY=…` apenas quando os alertas estiverem ativados; esta é a chave
     pública e não autoriza envios.
   - `NEXT_PUBLIC_CONTACT_EMAIL=contacto@seudominio.pt` apenas depois de a caixa institucional
     estar validada e operacional; sem esta variável, o site não publica um email pessoal.
   - `NEXT_PUBLIC_LEGAL_RESPONSIBLE_NAME=…`
   - `NEXT_PUBLIC_LEGAL_ADDRESS=…` (se aplicável)
   - `NEXT_PUBLIC_LEGAL_TAX_ID=…` (se aplicável)
   - `NEXT_PUBLIC_LEGAL_REGISTRATION=…` (se aplicável)
5. Publique e confirme os cabeçalhos de segurança, `robots.txt`, `sitemap.xml` e páginas legais.
6. Adicione apenas as origens exatas autorizadas ao `CORS_ORIGINS` do backend; não autorize
   indiscriminadamente todos os previews a consultar serviços privados de produção.

### Ordem segura entre API e frontend

Prefira publicar primeiro a API e só depois o frontend. O comando `npm run check:deployment-api` faz
apenas pedidos públicos de leitura. Aceita o contrato completo — capacidades
`global_search_v1`, `parliament_explorer_v1` e `parliament_publication_history_v1` — ou, se a API
não anunciar nenhuma dessas capacidades versionadas durante a transição, confirma
todos os caminhos anteriores que servem as mesmas fotografias revistas. Neste segundo modo a
interface fica deliberadamente limitada à consulta sequencial, sem fingir que a pesquisa avançada
está disponível. O Vercel bloqueia o frontend se nenhum dos dois contratos for seguro. Após a
compilação, `npm run verify:next-artifact` confirma que os estilos críticos da atividade parlamentar
e do contacto chegaram efetivamente ao artefacto.

## Render

Para uma instalação nova baseada em Render, o `render.yaml` define um serviço Python e um
PostgreSQL separado. Preencha variáveis `sync: false` e confirme a topologia antes de criar o
Blueprint. Na instalação existente, preserve a base Supabase e confirme `/api/v1/health/ready`.

O serviço FastAPI não executa migrações no arranque. Para esta produção, use exclusivamente
`.github/workflows/production-schema-migration.yml`, com o SHA exato de `main`, confirmação
`MIGRAR-V5` e o identificador de um ensaio real bem-sucedido com menos de 24 horas. O workflow
verifica o destino Supabase, TLS com CA oficial, provas de migração e segundo restauro V5,
preservação dos dados, checksums, RLS e ausência de privilégios privados do navegador.
As credenciais pertencem aos Secrets do ambiente; não as cole em comandos, documentos ou logs.

Depois, atualize `NEXT_PUBLIC_API_URL` no Vercel. Em planos gratuitos, espere suspensão por
inatividade e retenção reduzida do PostgreSQL; não os trate como arquivo oficial durável.

Para ativar alertas, configure `VAPID_PRIVATE_KEY` apenas como segredo do backend e defina
`VAPID_SUBJECT` com um contacto institucional válido. Nunca copie a chave privada para uma variável
`NEXT_PUBLIC_*`, para o repositório ou para logs. Sem ambas as extremidades configuradas, a
interface apresenta os alertas como indisponíveis. A difusão recebe apenas um `alert_id` e falha
fechada se o registo não estiver publicado, revisto, vigente e ligado a arquivo oficial atestado.
O backend aceita endpoints HTTPS apenas dos serviços push suportados de Google/Chromium, Mozilla,
Apple e Windows; qualquer novo fornecedor exige revisão e teste antes de alargar essa allowlist.

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

No repositório, `.github/workflows/official-index-sync.yml` executa a atualização diária antes de
`.github/workflows/operational-status.yml` verificar a frescura. A atualização escreve apenas
índices e registos operacionais de sincronização; não promove conteúdo editorial. O workflow
`.github/workflows/public-smoke.yml` testa o domínio público após um deployment `Production`
bem-sucedido, diariamente e por execução manual, com repetição enquanto o deployment propaga.
A API também é testada nas execuções diárias e manuais.

## Checklist pós-publicação

- HTTPS e redirecionamento ativo em frontend e API.
- CORS contém apenas origens reais.
- Swagger/ReDoc desativados em produção.
- O service worker só é registado depois de ativar o modo offline ou consentir alertas.
- Consentir alertas não ativa a cache offline; essa escolha continua no rodapé.
- O controlo offline apaga apenas os caches do projeto e conserva o worker se ainda existir uma
  subscrição push ativa.
- Rotas privadas, pedidos autenticados e respostas `private`/`no-store` nunca entram no cache.
- A autorização de notificações só é pedida depois de consentimento informado e ação explícita.
- Preferências e subscrição podem ser alteradas e apagadas no navegador e no backend.
- Uma difusão só pode ser reconstruída a partir de um alerta publicado e de fonte atestada.
- Se houver várias instâncias de backend, existe rate limit partilhado além da proteção local.
- Migrações aplicadas e capacidade real de recuperação descrita sem garantias inexistentes.
- Última cópia B2 cifrada e último ensaio de restauro com execução, SHA-256, RPO e RTO registados.
- URLs oficiais, hashes e datas visíveis nos dados reais.
- Dados de demonstração ausentes do domínio oficial.
- Política de correções e contacto público disponíveis.
- Privacidade, cookies, termos/aviso legal e acessibilidade publicados.
- Workflow `Public smoke` verde para o commit integrado.
- Workflow `Official index sync` e monitor de frescura sem falhas não justificadas.
