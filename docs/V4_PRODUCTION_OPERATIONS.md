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
- timeout máximo de 45 minutos;
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
mas o job termina com erro visível para obrigar a análise humana.

Recolha não significa publicação.

### `bootstrap-parliament-publication`

Executa:

```bash
cd backend
python -m scripts.bootstrap_v4_public
```

Só publica a fotografia parlamentar previamente auditada quando coincidem SHA-256, URL oficial,
contagem esperada e atestação do arquivo. Qualquer divergência bloqueia a publicação.

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
3. Executar `refresh-official-indexes`.
4. Rever hashes, contagens, avisos e falhas.
5. Executar uma publicação apenas quando existir revisão humana concluída.
6. Confirmar `/api/v1/public/data-status` e as páginas públicas afetadas.

## O que nunca deve acontecer

- publicar durante o arranque da API;
- aplicar migrações dentro de um pedido HTTP;
- esconder uma falha de fonte;
- tratar recolha como aprovação editorial;
- substituir dados indisponíveis por dados fictícios sem indicação clara;
- atribuir conclusões políticas ou jurídicas por inferência automática.
