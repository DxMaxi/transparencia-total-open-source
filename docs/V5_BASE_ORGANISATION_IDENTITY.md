# V5.52 — identidade organizacional privada com fonte própria

## Resultado e limite

A V5.52 prepara a entrada de prova de identidade de uma organização no circuito editorial do
Investigador Cívico. A observação tem fonte oficial independente do contrato BASE, arquivo
atestado, data e SHA-256. O resultado é um processo privado
`ORGANISATION_IDENTITY/PENDING`, com origem `INGESTION`.

Esta entrega não publica organizações nem liga partes de contratos. Aprovar a identidade é uma
decisão privada: não cria `Organisation`, `InterestEntity`, `PublicContractParty`,
`ContractMatchReview`, `InterestRelationship`, `DataPublicationReview` ou
`EditorialPublicationEvent`. Uma fonte que apenas designa a parte de um contrato não substitui a
prova de identidade. Um nome, por si só, não estabelece uma correspondência.

O código não equivale a uma operação real. Não foram executadas migrações, recolhas, propostas,
revisões ou publicações deste domínio em staging ou produção. Os resultados das validações do
candidato têm de acompanhar a respetiva PR; não se herdam contagens de testes de outra versão.

## Fonte independente e cobertura

O [serviço de Publicações do IRN](https://registo.justica.gov.pt/Empresas/Publicacoes) permite
consultar atos de registo de empresas e outras pessoas coletivas. A
[ajuda oficial do portal](https://publicacoes.mj.pt/Ajuda.aspx) distingue a pesquisa da consulta
do conteúdo de cada publicação e identifica também publicações em PDF.

A política inicial é deliberadamente restrita:

- editor `JUSTICE_REGISTRY` e tipo documental `ORGANISATION_REGISTRY`;
- documento individual em `https://publicacoes.mj.pt/DetalhePublicacao.aspx`, sem parâmetros,
  fragmento, credenciais ou porta alternativa;
- referência oficial do ato, não fiscal, igual ao `official_identifier` do documento;
- denominação e tipo da organização retirados da fonte e confirmados na revisão humana;
- URL, data e SHA-256 coincidentes entre documento e atestação de arquivo.

A página de pesquisa, o índice, a descrição do serviço, um contrato BASE ou a existência de um
domínio oficial não provam individualmente a identidade. Uma referência indisponível não é
inventada a partir do NIPC, do nome ou de uma posição na lista.

O endereço de detalhe pode depender do contexto da navegação no portal. Por isso, o URL não é
tratado como identificador único de uma organização: a prova depende também dos bytes arquivados,
do SHA-256, da referência não fiscal do ato e da revisão humana. A V5.52 não faz recolha automática
do portal nem afirma que essa ligação abre sempre o mesmo ato fora da sessão original.

A política não representa cobertura nacional integral, atualidade de todos os registos nem
autorização para republicar o conteúdo integral. Outros portais, formatos e fontes exigem uma
política e validação próprias. Documentos de registo podem incluir dados pessoais; o âmbito de
arquivo, acesso e reutilização exige avaliação jurídica antes de qualquer tratamento real.

## Identificador fiscal: fronteira privada

O NIPC é introduzido apenas no pedido interativo protegido da ferramenta de staging. Não existe
campo de NIPC no painel, parâmetro de linha de comandos, endpoint HTTP de ingestão fiscal ou
exemplo documental com identificadores reais.

O `PROTECTED_IDENTIFIER_PEPPER` tem de existir antes de abrir a ligação ou executar consultas.
Não é gerado automaticamente nem substituído por valor temporário. A entrada é convertida em
HMAC-SHA-256; o digest permanece exclusivamente na tabela privada de observações. O valor
introduzido não é persistido na observação nem integra argumentos, resultados ou mensagens de
erro. Esta garantia não declara que os documentos brutos do IRN estejam livres de dados
pessoais: o respetivo arquivo exige avaliação própria antes de qualquer operação real.

O HMAC não aparece em respostas da API, HTML, campos ocultos, JSON editorial, auditorias ou
mensagens emitidas pela aplicação. A infraestrutura pode registar parâmetros SQL ou URLs
introduzidos fora deste painel; antes de dados reais é obrigatório verificar a configuração e o
acesso aos logs. A aplicação não apaga nem controla esses registos externos. O hash interno da
observação também não é uma chave de consulta pública.
O `source_record_sha256` descreve apenas os campos não fiscais da observação; o
`proposal_confirmation_sha256` está ligado ao contexto exato da proposta, sem expor um
identificador estável derivado do NIPC.

A introdução de valores em campos de texto não contorna esta fronteira: referência, denominação,
título e pesquisa são validados para rejeitar identificadores fiscais e valores protegidos. A
pesquisa por denominação serve apenas para localizar observações, nunca para associar entidades.

## Observação e proposta editorial

`BaseOrganisationIdentityObservation` conserva a referência, denominação, tipo, fonte, instante
observado, hashes, versão do parser, versão da política e alias de criação. O seu âmbito é fixo:

- `identity_scope=ORGANISATION_IDENTITY_ONLY`;
- `link_status=UNLINKED_PRIVATE`;
- `publication_eligible=false`.

A observação é append-only. Atualizar, apagar ou truncar a tabela é proibido. Uma nova prova
oficial acrescenta outra observação; não corrige silenciosamente a anterior. A repetição da mesma
prova é idempotente, enquanto conteúdo divergente para a mesma identidade de observação é recusado.
Os metadados de fonte IRN são imutáveis desde a criação do documento, mesmo antes de uma
observação. Assim, a proteção não depende de consultar outra tabela num snapshot concorrente.

A área `/admin/revisao/organizacoes` usa apenas endpoints privados com autenticação editorial e
MFA. O browser envia o identificador da observação, hashes de contexto e confirmações fechadas.
O servidor reconstrói a prova e volta a verificar fonte e arquivo na transação antes de criar o
caso. Uma confirmação antiga ou incoerente é rejeitada sem deixar decisões ou casos parciais.

A revisão humana deve verificar o conteúdo arquivado e a correspondência exata entre a
organização declarada e a fonte. A existência de uma linha na tabela não certifica, por si só, a
extração. A aprovação mantém o processo privado. A criação manual genérica e a correção genérica
por JSON não são vias alternativas para este tipo: uma correção exige nova observação com prova.
As fontes IRN não aparecem na pesquisa genérica de fontes nem permitem propostas de outro tipo.
Os erros de validação de todo o espaço editorial são sanitizados, incluindo criação e correção
genéricas, para nunca repetir o conteúdo de entradas fiscais acidentais.

## Proteções de base de dados e legado

A nova tabela tem RLS e privilégios revogados a `PUBLIC`, `anon` e `authenticated`; não recebe uma
política de leitura direta pelo browser. As funções de trigger não são novas funções públicas de
aplicação. A base rejeita estados `PUBLISHED`/`WITHDRAWN` e eventos públicos para este tipo de caso.

A coluna legada `organisations.public_nipc` só pode ser removida quando está integralmente vazia.
O preflight tem de manter o bloqueio da tabela até à remoção para não perder uma escrita
concorrente. Se existir qualquer valor, a migração para e exige uma decisão própria, sem copiar,
converter, publicar ou apagar automaticamente os dados.

O valor histórico PostgreSQL `NORMALISED_NAME` permanece legível, com nome Prisma
`LEGACY_NORMALISED_NAME`. Novas correspondências não podem nascer de nomes normalizados; os
candidatos históricos não são apagados nem reescritos por esta entrega. Uma correspondência exata
continua a exigir identificador oficial protegido e revisão própria e nunca constitui uma
acusação ou conclusão automática.

## Verificações e passagem para operação

Validação local do candidato em 2 de setembro de 2026:

- 31 migrações aplicadas de raiz numa base PostgreSQL 17.11 descartável neste computador.
- 680 testes backend aprovados, incluindo a integração V5.52, concorrência, rollback, ACL das
  funções/tabela, rejeição de SQL incompatível, preflight legado e privacidade de erros.
- 152 testes de contrato frontend aprovados; ESLint, TypeScript, Ruff e mypy aprovados.
- Compilação Next.js e verificação do artefacto aprovadas; API pública não configurada na build
  local, sem substituir dados indisponíveis por fixtures.
- O runtime local de testes é Python 3.12.13/Node 26.1.0; a decisão de integração exige também o
  CI do projeto em Python 3.13.15/Node 24, não presume paridade pela execução local.

A comparação global Prisma por introspeção encontra a FK intencional de `public.staff_profiles`
para `auth.users`, gerida fora do modelo Prisma. Não se alterou `auth` para contornar esse limite.
O novo esquema foi validado pelo Prisma, pelos testes PostgreSQL e pela revisão dos índices/FK.

O candidato deve provar, com fixtures sintéticas e PostgreSQL descartável:

1. ausência de ligação à base sem pepper e ausência de NIPC/HMAC em qualquer saída;
2. recusa de fonte genérica, contrato BASE, arquivo incoerente e metadados fiscais;
3. idempotência, confirmações obsoletas, concorrência e rollback integral;
4. revisão e aprovação sem alterar tabelas públicas;
5. impossibilidade de criar ou corrigir o caso pela via genérica;
6. RLS, privilégios, imutabilidade e recusa de publicação na base de dados;
7. preservação do legado e interrupção segura da migração perante `public_nipc` preenchido;
8. painel sem campos fiscais, sem HMAC em campos ocultos e sem ações públicas.

Antes de usar dados reais continuam obrigatórios: destino de staging inequívoco e separado de
produção; autorização operacional; migração validada; pepper estável guardado fora do repositório;
avaliação jurídica e de privacidade; arquivo adequado; utilizadores editoriais e MFA; ensaio
isolado e evidência de auditoria sanitizada.

Em 2 de setembro de 2026, a inspeção read-only do GitHub encontrou os ambientes `Preview`,
`Production` e `recovery`, mas nenhum ambiente `staging` configurado. Não se reutilizam os
destinos ou segredos de produção para ultrapassar esse bloqueio. Nenhum workflow de staging foi
executado nesta entrega.

A publicação e retirada de organizações, a associação exata às partes dos contratos e as relações
auditáveis são portas posteriores, independentes e ainda por concluir. Esta fundação não fecha a
V5 nem a checklist operacional do Investigador Cívico.
