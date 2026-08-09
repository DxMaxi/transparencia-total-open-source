# Operações de produção da V4

## Princípio

A API pública nunca executa migrações, recolhas ou publicações durante o arranque. Reiniciar o
serviço não altera dados públicos nem contacta fontes oficiais.

Esta separação protege o cidadão contra alterações silenciosas: cada operação fica registada,
exige confirmação explícita e pode ser auditada no histórico do GitHub Actions.

## Workflow protegido

As operações sensíveis são executadas por
`.github/workflows/production-operations.yml` através de `workflow_dispatch`.

O workflow usa:

- ambiente GitHub `production`;
- confirmação textual `PRODUCAO`;
- concorrência exclusiva, sem cancelamento de uma operação em curso;
- timeout máximo de 90 minutos;
- segredos próprios de produção;
- código exatamente correspondente ao commit escolhido.

## Operações disponíveis

### `migrate`

Aplica todas as migrações versionadas com:

```bash
npm ci
npm run db:deploy
```

Não recolhe fontes e não publica dados.

### `refresh-official-indexes`

Executa:

```bash
cd backend
python -m scripts.refresh_v4_indexes
```

Atualiza separadamente os índices oficiais da V4. O relatório final distingue `SUCCEEDED`,
`PARTIAL` e as fontes que falharam. Se uma fonte falhar, as restantes continuam a ser tentadas,
mas o job termina com erro visível para obrigar a análise humana. A tentativa falhada fica registada
como `SyncRun=FAILED`, mesmo quando a falha ocorre antes de existirem bytes para arquivar.

Recolha não significa publicação.

### `sync-parliament-deputies` e `sync-parliament-activity`

Executam, separadamente:

```bash
cd backend
python -m scripts.sync_parliament deputies --legislature XVII --persist
python -m scripts.sync_parliament_activity --legislature XVII
```

Ambas escrevem apenas dados privados. A segunda operação guarda os bytes em PostgreSQL, cria o
manifesto imutável e recusa cobertura vazia. O workflow diário `parliament-sync.yml` executa estas
duas recolhas sem publicar.

### `preview-parliament-activity`

Executa `review_parliament_activity` sem ação. O resultado contém a URL, SHA-256 dos bytes,
SHA-256 normalizado, atestação, parser e contagens de reuniões, iniciativas, votações e posições.
Não cria `DataPublicationReview` nem `AuditEvent`.

### `publish-parliament-activity` e `withdraw-parliament-activity`

Exigem âmbito, os dois hashes, as quatro contagens, pseudónimo e fundamentação. O repositório volta
a ler e bloquear a fotografia mais recente antes de acrescentar uma decisão e evento de auditoria
por âmbito. `activity` controla reuniões/iniciativas; `votes` controla votações. Retirar não apaga
dados nem decisões anteriores.

### `verify-archive-integrity`

Executa:

```bash
cd backend
python -m scripts.verify_v4_archive
```

Verifica todos os objetos privados sem os alterar:

- a chave `sha256/...` tem de corresponder ao hash registado;
- o SHA-256 calculado dos bytes tem de coincidir com o esperado;
- o tamanho real tem de coincidir com o tamanho persistido.

Qualquer divergência termina a operação com erro e identifica o objeto afetado. O sistema nunca
corrige, apaga ou substitui prova automaticamente.

O workflow `.github/workflows/archive-integrity.yml` repete esta verificação semanalmente e pode
também ser iniciado manualmente.

### `bootstrap-parliament-publication` (diretório inicial)

Executa:

```bash
cd backend
python -m scripts.bootstrap_v4_public
```

Só publica o diretório inicial de deputados previamente auditado quando coincidem SHA-256, URL
oficial, contagem esperada e atestação do arquivo. Não publica reuniões, iniciativas ou votações;
essas usam as operações de atividade descritas acima. Qualquer divergência bloqueia a publicação.

## Segredos necessários

O ambiente GitHub `production` deve conter:

- `PRODUCTION_DATABASE_URL`;
- `PRODUCTION_ADMIN_API_KEY`;
- `PRODUCTION_OFFICIAL_USER_AGENT`;
- `PRODUCTION_IDENTIFIER_PEPPER`, quando a operação tratar identificadores protegidos.

O ambiente deve exigir aprovação manual antes da execução.

## Ordem recomendada

1. Executar `migrate`.
2. Confirmar `/api/v1/health/ready`.
3. Executar `verify-archive-integrity`.
4. Executar `refresh-official-indexes`.
5. Executar `sync-parliament-deputies` e `sync-parliament-activity`.
6. Executar `preview-parliament-activity` e rever hashes, contagens, avisos e atores desconhecidos.
7. Executar `publish-parliament-activity` apenas nos âmbitos aprovados.
8. Confirmar `/api/v1/public/data-status`, os três endpoints parlamentares e as páginas públicas.

## O que nunca deve acontecer

- publicar durante o arranque da API;
- aplicar migrações dentro de um pedido HTTP;
- esconder uma falha de fonte;
- tratar recolha como aprovação editorial;
- substituir dados indisponíveis por dados fictícios sem indicação clara;
- atribuir conclusões políticas ou jurídicas por inferência automática;
- aceitar como íntegra uma prova cujo hash ou tamanho não coincida.
