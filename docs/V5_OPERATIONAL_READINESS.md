# V5.53 — publicação organizacional segura e prontidão operacional

## Estado de referência em 7 de setembro de 2026

A V5.52 e a correção de diagnóstico V5.52.1 estão integradas em `main`. O site público continua
acessível, mas a recolha parlamentar e a ativação editorial remota mantêm os respetivos gates
fail-closed. A existência deste código não prova que as migrações foram aplicadas em staging ou
produção, que existem utilizadores editoriais, nem que qualquer organização real foi publicada.

A migração V5.53 foi aplicada desde zero, juntamente com todas as migrações anteriores, numa base
PostgreSQL 17 local marcada como descartável e com a forma mínima de `auth.users`. Não foi usada
uma ligação remota, não foram alterados segredos e não foi executada qualquer operação sobre dados
reais.

## O que a V5.53 acrescenta

A aprovação de `ORGANISATION_IDENTITY` continua privada. Um segundo processo,
`ORGANISATION_PUBLICATION`, nasce em `PENDING` e referencia a versão, decisão, fonte e observação
privada exatas. Só depois de uma revisão humana própria um `ADMIN` com MFA pode publicar a projeção
mínima autorizada.

A publicação acrescenta, na mesma transação:

- um identificador público aleatório e não fiscal;
- uma fotografia pública imutável;
- uma revisão de necessidade e proporcionalidade;
- um evento de auditoria, uma decisão e um evento de publicação coerentes;
- a projeção pública atual, sem NIPC, HMAC, observação privada, partes de contratos ou relações.

O HMAC serve apenas para serializar internamente operações sobre a mesma identidade exata. Não é
devolvido pelos endpoints, não entra na fotografia, no HTML, na auditoria pública ou nos eventos.
Uma designação, sigla ou referência de ato nunca é usada como correspondência aproximada.

## Consulta pública e retirada

A API disponibiliza lista, ficha e histórico próprios em `/public/organisations`. O frontend usa
`/organizacoes` e `/organizacoes/[public_id]`, sempre sem cache e sem fallback para tabelas antigas.
Quando o esquema ou a ligação não estão disponíveis, a consulta devolve HTTP 503 neutro. Uma ficha
retirada deixa de expor os campos correntes, mas o histórico conserva ação, data, fundamento e
hashes sem reexpor a identidade privada.

O direito de resposta aceita uma organização apenas quando o identificador público e o SHA-256 da
fotografia correspondem a uma fotografia imutável existente. A resposta permanece anexada mesmo
depois de retirada a ficha e, quando publicada, continua consultável no histórico com o hash da
fotografia respondida. A receção nunca publica automaticamente a resposta.

A retirada exige `ADMIN`, MFA, confirmação otimista da prova e um fundamento previsto na
governação. Acrescenta nova revisão, auditoria, decisão e evento; não apaga organização,
fotografia, fonte, processo, decisão anterior ou direito de resposta. Uma republicação exige nova
fonte/identidade revista, nova fotografia e reutiliza o identificador público apenas quando o HMAC
privado é exatamente igual.

## Barreiras na base de dados

- O preflight recusa conversão silenciosa de organizações `VERIFIED` legadas.
- Triggers reconstroem a projeção a partir da fonte IRN arquivada e das duas aprovações humanas.
- Projeção, fotografia, decisão, revisão, auditoria e evento têm de ficar coerentes no commit.
- Fotografias, auditorias, revisões e eventos não admitem eliminação ou `TRUNCATE` por esta via.
- A publicação não pode criar `InterestEntity`, parte contratual, correspondência ou relação.
- A tabela de fotografias tem RLS e nenhum privilégio para `PUBLIC`, `anon` ou `authenticated`.
- Concorrência e falhas tardias recuam a transação inteira.

## Evidência de validação local

Em 7 de setembro de 2026, a fotografia candidata foi validada sem ligações remotas nem dados
reais:

- 32 migrações aplicadas desde zero em PostgreSQL 17 descartável;
- 717 testes de backend aprovados;
- 156 testes de frontend e contratos aprovados;
- `ruff`, formatação Python, `mypy` estrito, TypeScript e ESLint aprovados;
- esquema Prisma, sincronização de dependências e política Python 3.13.15 aprovados;
- build de produção do frontend e verificação dos artefactos aprovadas.

Estas verificações provam a consistência do candidato local. Não substituem o inventário, a
migração, o ensaio sintético nem a autorização próprios de staging.

## O que continua por provar fora do código

- aplicar primeiro o inventário e as migrações no projeto de staging correto;
- configurar autenticação editorial e MFA sem reutilizar produção;
- configurar e provar um pepper HMAC estável fora do repositório;
- executar um ensaio sintético completo em staging, incluindo publicação e retirada;
- obter a avaliação jurídica/AIPD aplicável antes de usar identificadores protegidos reais;
- executar backup cifrado e restauro isolado após a futura migração autorizada;
- só depois decidir e executar a ativação em produção.

## Próximo desenvolvimento: V5.54

A associação de uma parte de contrato a uma organização não é autorizada pela V5.53. A próxima
porta deve exigir o identificador oficial exato/HMAC privado, duas publicações ativas e as provas
das duas fontes. O resultado tem de nascer como candidato privado `PENDING_REVIEW`; não pode usar
nomes, fuzzy matching ou criar uma relação pública. Só uma entrega posterior, com fonte e revisão
próprias, poderá materializar uma ligação factual no grafo.

Metodologia detalhada: [V5.52 — identidade organizacional privada](V5_BASE_ORGANISATION_IDENTITY.md)
e [V5.53 — publicação e retirada de organizações](V5_BASE_ORGANISATION_PUBLICATION.md).
