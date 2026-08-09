# Checklist de fecho da V4

## Princípios obrigatórios

- [x] A fonte oficial precede qualquer conclusão.
- [x] Ausência de dados é apresentada como indisponibilidade, nunca como ausência de factos.
- [x] Ingestão, revisão e publicação são estados separados.
- [x] Bytes oficiais são identificados por SHA-256 antes da normalização.
- [x] Conteúdo bruto privado é excluído de serialização pública.
- [x] Identificadores sensíveis do BASE não são publicados em claro.
- [x] Tabelas de staging DRE e EPT são append-only.
- [x] Fotografias parlamentares, reuniões, iniciativas, votações e posições são append-only.
- [x] A leitura pública parlamentar seleciona uma única fotografia aprovada por âmbito.
- [x] Dados de demonstração estão desativados no build de produção.
- [x] Nenhum novo conector promove dados automaticamente.

- [x] Reprocessar os mesmos bytes com outro parser acrescenta um snapshot versionado; nunca altera o anterior.

## Fontes V4

| Fonte | Gate técnico V4 | Publicação automática |
|---|---|---|
| Assembleia da República | Bytes PostgreSQL, manifesto versionado, associação segura, revisão por hashes/contagens e API fail-closed | Não |
| Portal BASE | Arquivo, staging privado, deduplicação e promoção exata sob revisão | Não |
| Diário da República | Arquivo, snapshot privado, inspector sem texto e testes de imutabilidade | Não |
| Entidade para a Transparência | Índice canónico fail-closed; contingência limitada ao portal oficial, sempre `PARTIAL`, avisada, atestada e privada | Não |
| Tribunal de Contas | Colector mínimo fail-closed do índice oficial | Não |
| Parlamento Europeu | Colector mínimo fail-closed do índice oficial | Não |
| Portal da Transparência do SNS | Colector privado fail-closed como origem inicial | Não |

## Verificação automatizada

O PR só deve ser considerado pronto quando o CI confirmar:

- migrações Prisma em PostgreSQL 17;
- Ruff lint e formatação;
- mypy no backend;
- pytest no backend, incluindo integrações PostgreSQL;
- lint e testes frontend;
- validação e geração Prisma;
- build Next.js.

## Gates operacionais posteriores ao merge

Estes passos não são executados automaticamente pelo código nem pelo PR:

1. ensaio controlado do EPT em ambiente de staging;
2. confirmação jurídica e de proteção de dados antes de qualquer tratamento de declarações;
3. escolha documentada dos recursos concretos do Tribunal de Contas e Parlamento Europeu;
4. definição de cobertura territorial explícita para cada conector Radar;
5. revisão humana positiva antes de criar qualquer projecção pública;
6. deploy separado, autorizado e acompanhado de verificação pós-deploy.
7. primeira cópia cifrada no Backblaze B2 EU e primeiro restauro isolado, seguindo
   [o runbook próprio](BACKUP_BACKBLAZE_B2.md), antes da tag `v0.4.0`.

Para o Parlamento, a sequência obrigatória é: `migrate` → `sync-parliament-deputies` →
`sync-parliament-activity` → `preview-parliament-activity` → revisão humana →
`publish-parliament-activity` → smoke tests. Nenhum destes passos é executado pelo frontend.

## Fora da V4

- painel de administração;
- revisão editorial automatizada;
- correspondência difusa de pessoas ou entidades;
- publicação em massa;
- ingestão de imprensa como fonte probatória;
- cobertura automática de todos os municípios;
- decisões substantivas por IA.
