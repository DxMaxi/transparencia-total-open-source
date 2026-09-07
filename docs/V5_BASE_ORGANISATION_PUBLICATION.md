# V5.53 — publicação e retirada específicas de organizações

## Objetivo

Esta entrega permite publicar uma identificação organizacional mínima depois de a identidade
privada V5.52 ter sido aprovada. Não publica o identificador fiscal, não associa contratos e não
cria um grafo. `ORGANISATION_IDENTITY` e `ORGANISATION_PUBLICATION` são processos distintos com
revisões humanas distintas.

## Sequência obrigatória

1. Uma observação IRN conserva o identificador apenas como HMAC-SHA-256 com pepper privado.
2. Um caso `ORGANISATION_IDENTITY` confirma em privado fonte, arquivo e dados normalizados.
3. A aprovação dessa identidade não altera qualquer tabela pública.
4. Uma proposta `ORGANISATION_PUBLICATION/PENDING` copia apenas os campos autorizados e liga-se à
   versão e decisão privadas exatas.
5. Uma revisão humana específica compara a fonte e decide aprovar ou rejeitar a proposta pública.
6. Só `ADMIN` com sessão `aal2` pode confirmar a publicação ou retirada específica.

Cada transição valida identificadores, revisão, SHA-256 e uma prova derivada pelo servidor. Uma
pré-visualização antiga é recusada e não deixa efeitos parciais.

## Fotografia pública mínima

A fotografia conserva apenas:

- identificador aleatório `base_public_org_<hex>`;
- designação e categoria tal como revistas na fonte;
- referência pública não fiscal do ato;
- URL oficial IRN;
- SHA-256 do registo-fonte, da confirmação de publicação e da fotografia pública;
- referências internas protegidas por ACL às versões e decisões que justificam a publicação;
- alias público e data da decisão.

As referências editoriais internas existem na tabela protegida para auditoria, mas não pertencem
ao modelo da API. A projeção pública não contém NIPC, HMAC, hash da observação privada, morada,
pessoa, parte contratual, correspondência ou relação.

## Identidade exata sem inferência

O sistema não considera uma referência de ato como identificador universal da entidade. Também
não funde designações iguais. Para preservar estabilidade entre retirada e republicação, compara
internamente apenas o HMAC fiscal exato já existente; o valor e o digest nunca saem do backend.
Qualquer divergência ou duplicidade produz bloqueio e revisão, nunca uma fusão automática.

## Publicação transacional

A publicação exige duas aprovações atuais, a mesma fonte IRN arquivada, metadados fechados e uma
fotografia ainda não publicada. A transação acrescenta revisão pública, auditoria, decisão e evento
com o mesmo alvo, versão, ator e instante. Constraints diferidas recusam commits incompletos.

Triggers independentes impedem:

- editar ou apagar a fotografia;
- projetar campos diferentes da fotografia;
- publicar sem evento final coerente;
- ligar o novo identificador a `interest_entities`;
- truncar a fotografia ou os históricos probatórios;
- conceder acesso browser à tabela privada de snapshots.

## Retirada, republicação e direito de resposta

A retirada não elimina nada. Muda apenas a disponibilidade ativa depois de acrescentar revisão,
auditoria, decisão e evento `WITHDRAW`. A página pública deixa de mostrar os campos correntes e
mantém um histórico mínimo com os hashes da fotografia retirada.

Um direito de resposta é aceite apenas contra um par exato de identificador público e SHA-256 de
uma fotografia existente. É guardado com timestamp e hashes próprios, aguarda verificação humana e
permanece depois da retirada. O histórico público volta a apresentar apenas respostas publicadas e
liga cada uma ao SHA-256 exato da fotografia respondida. Uma futura republicação cria outra
fotografia; respostas à versão anterior não são atribuídas automaticamente à nova versão.

## Consulta pública

- `GET /api/v1/public/organisations`
- `GET /api/v1/public/organisations/{public_id}`
- `GET /api/v1/public/organisations/{public_id}/publication-history`
- páginas `/organizacoes` e `/organizacoes/{public_id}`

As respostas usam `Cache-Control: no-store, max-age=0, must-revalidate`. Só entram organizações no
namespace V5.53 com fotografia atual, estado `PUBLISHED`, revisão `VERIFIED` e evento específico.
Não existe fallback para dados legados. Ausência é descrita como dados indisponíveis, nunca como
inexistência, incumprimento ou irregularidade.

## Limites desta entrega

O código e a migração local não ativam staging ou produção. Não criam organizações reais, partes de
contratos, candidatos de correspondência ou relações. O uso operacional continua dependente de
inventário read-only, migração autorizada, autenticação/MFA, pepper estável, revisão jurídica,
backup e ensaio de restauro. A porta seguinte deve tratar associações exatas apenas como candidatos
privados, mantendo o grafo público fechado.
