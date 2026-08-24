# V5.31 — retirada imutável da fotografia completa de perfis

## Objetivo

A V5.31 completa a saída segura da primeira fotografia de perfis publicada pela V5.30. A unidade
de decisão continua a ser a **fotografia completa**: não existe retirada de uma pessoa escolhida,
nem um administrador pode enviar uma lista parcial de alvos.

Esta entrega prepara e testa o código. Não executa qualquer retirada real, não aplica migrações,
não configura o Supabase, não cria utilizadores ou segredos e não altera staging ou produção.

## Pré-visualização sem escrita

`GET /api/v1/editorial/parliament/deputy-snapshots/{snapshot_id}/withdrawal` exige uma sessão da
equipa com MFA, mas não escreve. O servidor volta a confirmar:

- fonte parlamentar HTTPS, data de recolha e SHA-256 dos bytes;
- atestação de arquivo coincidente em URL, data e SHA-256;
- manifesto e contagens materializadas da fotografia inteira;
- identidade `DEPUTY` ligada apenas pelo mesmo `DepId` oficial exato;
- uma observação pública sem filiação partidária inferida para cada perfil;
- processo `POLITICIAN_PROFILE` com origem `INGESTION`, estado `PUBLISHED` e versão íntegra;
- revisão pública positiva mais recente por pessoa e para a fotografia;
- auditorias `PUBLISHED` que provam zero mandatos e zero filiações criados;
- um único evento `PUBLISH` da versão e da pessoa exatas, com SHA-256 novamente calculado;
- ausência de qualquer evento `WITHDRAW` para a mesma versão.

As revisões, auditorias e eventos individuais têm de pertencer ao mesmo instante e alias da
publicação integral. Uma divergência bloqueia toda a retirada.

## Efeito público calculado

A pré-visualização usa a mesma regra fail-closed do diretório público: uma fonte parlamentar só é
selecionável quando todas as observações dessa legislatura têm uma revisão `PERSON` positiva mais
recente e arquivo atestado.

Antes da confirmação, o servidor exclui a fonte que será retirada e calcula um de dois efeitos:

- `FALLBACK_TO_PREVIOUS_SNAPSHOT`: regressa à fonte anterior ainda integralmente aprovada;
- `DATA_UNAVAILABLE`: não existe outra fotografia completa aprovada e a interface deve apresentar
  **dados indisponíveis**.

O efeito inteiro tem um SHA-256 próprio e é uma condição otimista do pedido. O administrador não
pode confirmar um efeito diferente daquele que o servidor acabou de calcular.

## Confirmação administrativa

`POST /api/v1/editorial/parliament/deputy-snapshots/{snapshot_id}/withdrawal` exige `ADMIN` com
`aal2`, categoria fechada prevista na governação, fundamentação privada, resumo público e cinco
confirmações explícitas:

1. a decisão abrange a fotografia completa;
2. nenhuma pessoa foi selecionada ou omitida individualmente;
3. o recuo ou a indisponibilidade pública foram revistos;
4. pessoas, fontes, versões e histórico serão preservados;
5. existe intenção inequívoca de retirar a fotografia.

O browser envia a contagem e os SHA-256 da fonte, fotografia, publicação original, prova integral
de retirada e efeito público. Dentro dos mesmos bloqueios usados pela publicação, o servidor
recalcula tudo antes da primeira escrita.

## Uma transação, apenas acrescentos

Para cada perfil, a retirada acrescenta:

- uma `DataPublicationReview` negativa para a mesma pessoa e fonte;
- um `AuditEvent` público `WITHDRAWN`, sem a fundamentação privada;
- uma `EditorialDecision` privada `WITHDRAW`, ligada à versão publicada;
- um `EditorialPublicationEvent` privado `WITHDRAW`, com SHA-256 próprio;
- a passagem do processo de `PUBLISHED` para `WITHDRAWN`.

No fim, acrescenta ainda a revisão negativa e o `AuditEvent` da fotografia completa. Antes do
commit, confirma que a fonte retirada deixou de satisfazer a seleção pública. Qualquer conflito,
prova desatualizada, falha intermédia ou incoerência reverte a operação inteira.

Não existe `DELETE` de `Person`, `ParliamentaryMembershipSnapshot`, fonte, arquivo,
`EditorialVersion`, decisão ou evento. A pessoa pode continuar publicamente visível através de uma
fotografia anterior ou posterior que tenha a sua própria prova positiva; o que deixa de estar ativo
é apenas a fotografia retirada.

## Republicação

A versão retirada não pode ser reativada. O índice único de eventos continua a permitir no máximo
um `PUBLISH` e um `WITHDRAW` por caso, versão, ação e alvo. Uma republicação exige uma **nova
fotografia imutável**, nova prova oficial, novos processos ou versões e um novo ciclo
`PENDING → IN_REVIEW → APPROVED → PUBLISHED`.

A V5.31 garante a retirada e preserva esta regra. A porta seguinte deve provar em PostgreSQL
descartável o ciclo de republicação a partir de uma fotografia posterior, incluindo o recuo público
e a substituição pela nova fotografia, sem reativar a versão antiga.

Ingestão, aprovação, migração e deployment nunca chamam esta operação automaticamente.
