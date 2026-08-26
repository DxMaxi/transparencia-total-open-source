# V5.37 — publicação transacional de cargos parlamentares

## Resultado

A V5.37 acrescenta a porta pública específica para um período de cargo proveniente de
`DepCargo`. Um cargo publicado é uma linha própria em `parliamentary_office_periods`: **não é um
mandato**, não cria filiação partidária e não afirma competências fora do intervalo que a fonte
oficial fornece.

Esta entrega prepara código, esquema, interface e testes. **Não publica dados reais**, não executa
migrações em staging ou produção e não altera segredos ou contas. A retirada imutável é uma porta
separada planeada para a V5.38 e continua obrigatória antes de qualquer ativação real.

## Prova exigida

Antes de apresentar uma prova de publicação, o servidor reconstrói o candidato a partir dos bytes
já arquivados e volta a confirmar:

- `DepId` e `CarId` oficiais exatos, sem fuzzy matching ou associação pelo nome;
- observação, posição do período e SHA-256 do período;
- título, início, fim, legislatura, círculo e identificador oficial do círculo;
- identidade publicada pela mesma fotografia e pelo mesmo `DepId`;
- URL oficial, data de recolha, SHA-256 da fonte e atestação do arquivo;
- contagens materializadas iguais ao manifesto imutável;
- versão editorial atual reconstruída no servidor e última decisão `APPROVE` com fonte confirmada.

Um elemento em falta ou contraditório bloqueia a publicação e aparece como dados indisponíveis ou
prova insuficiente. A ausência não é tratada como ausência do cargo.

## Transação e autorização

O `POST /editorial/parliament/office-cases/{case_id}/publication` exige `ADMIN` e MFA (`aal2`). Uma
única transação PostgreSQL, protegida também por advisory lock, acrescenta:

1. o período de cargo;
2. uma revisão positiva `PARLIAMENT_OFFICE`;
3. um `AuditEvent` com a prova anterior e posterior;
4. uma decisão editorial `PUBLISH`;
5. um `EditorialPublicationEvent` dirigido ao cargo.

Qualquer divergência, prova do cliente desatualizada ou falha do gate público faz rollback integral.
A operação cria zero pessoas, zero mandatos e zero ligações partidárias.

## Histórico e acesso

`parliamentary_office_periods` tem constraints de período e SHA-256, chave única por observação e
posição, RLS sem política pública e privilégios revogados para `PUBLIC`, `anon` e `authenticated`.
Um trigger rejeita `UPDATE` e `DELETE`; correções futuras acrescentam nova fonte e novo processo.

A API pública só devolve o cargo quando a última revisão específica é positiva, a identidade da
pessoa continua publicada, a observação corresponde ao `DepId`, o período corresponde ao `CarId`,
o círculo coincide e o documento oficial permanece atestado. A ficha mostra título, datas, CarId,
fonte, data de recolha e SHA-256, numa secção separada dos mandatos.

## Verificação

O teste PostgreSQL descartável prova a sequência privada → revista → aprovada → publicada, um
pedido com prova errada sem qualquer escrita, idempotência por conflito, o trigger append-only,
zero mandatos criados e a projeção pública exata. Os contratos frontend verificam autenticação,
confirmações, RLS, prova e apresentação separada.
