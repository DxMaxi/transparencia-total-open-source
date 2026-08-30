# V5.50 — porta editorial privada dos contratos Portal BASE

A V5.50 liga um contrato de um lote anual privado ao circuito editorial sem criar uma projeção
pública antecipada. A unidade de revisão é um `BaseContractSnapshot` identificado de forma exata;
o resultado da operação é apenas um `EditorialCase` de tipo `PUBLIC_CONTRACT`, origem `INGESTION`
e estado `PENDING`.

## Prova exigida antes da proposta

O servidor reconstrói a prova sem aceitar dados normalizados enviados pelo navegador. Uma proposta
só fica disponível quando todas as condições seguintes coincidem:

- `SourceDocument` com editor `BASE_GOV`, URL HTTPS, data de recolha e SHA-256;
- original anual com atestação de arquivo para o mesmo URL, hash e instante de recolha;
- `SyncRun` terminado (`SUCCEEDED` ou `PARTIAL`), com limitações visíveis e contagens lidas e
  escritas iguais ao lote normalizado materializado;
- número real de contratos e partes igual às contagens imutáveis do lote;
- recurso ZIP do mesmo ano e URL numa fotografia V5.49 completa e arquivada do catálogo oficial;
- tamanho do arquivo igual ao tamanho do recurso catalogado e recolha não anterior à última
  modificação declarada;
- ano marcado `HISTORICAL_CLOSED_YEAR`; o ano corrente provisório é bloqueado;
- identificador oficial do contrato preservado sem aproximação.

Uma recolha explicitamente truncada a uma amostra é bloqueada. Outras limitações — como linhas
sem ligação individual, duplicados equivalentes ou registos excluídos por segurança — permanecem
visíveis, mas não são transformadas numa conclusão sobre um contrato que sobreviveu à
normalização. Esta porta prova esse registo específico e a consistência interna do lote
normalizado; **não afirma cobertura integral de todas as linhas do ZIP anual**.

O SHA-256 do registo normalizado inclui os campos canónicos do contrato e das partes sem HMAC, a
identificação do lote e o seu hash normalizado, a identificação e o SHA-256 da fonte, e os IDs e
hashes canónicos do âmbito e recurso catalogados. Uma alteração num desses campos invalida a
confirmação apresentada pela interface. A atestação do arquivo, a conclusão do `SyncRun` e as
contagens declaradas e materializadas não são presumidas por esse hash: o servidor volta a
reconstruí-las e a validá-las separadamente em cada tentativa de proposta.

## O que nunca é devolvido ou criado

O endpoint privado nunca devolve o HMAC fiscal conservado no staging. Expõe apenas um booleano por
parte para indicar que existe uma referência protegida e uma contagem agregada. A proposta cria
zero linhas em:

- `PublicContract` e `PublicContractParty`;
- `Organisation` e `InterestEntity`;
- `ContractMatchReview`;
- `InterestRelationship`;
- `DataPublicationReview` e `EditorialPublicationEvent`.

A designação literal de uma parte pode ser usada para localizar a observação no painel, mas não é
uma chave de identidade. Não existe similaridade, distância textual, normalização para união ou
fuzzy matching. Cada organização exigirá uma fonte oficial independente e um identificador
inequívoco numa etapa posterior.

## Fecho das portas antigas

As funções V4 `mark_base_batch_publication_eligible` e `propose_base_contract_for_review` falham
agora explicitamente. A revisão genérica também recusa `PUBLIC_CONTRACT`, `INTEREST_ENTITY` e
`INTEREST_RELATIONSHIP`. Isto impede que um estado técnico `DRAFT` ou `PUBLISHED` substitua a prova
editorial específica.

As consultas públicas de contagens, dados abertos e Investigador Cívico exigem ainda que o evento
editorial mais recente do alvo específico seja `PUBLISH`. Portanto, uma linha legada com os estados
`VERIFIED` e `PUBLISHED`, mas sem esse evento, permanece invisível. Uma futura retirada acrescentará
um evento `WITHDRAW`; não apagará o evento de publicação nem a fonte anterior.

## Painel privado

`/admin/revisao/contratos` permite filtrar por ano, identificador oficial, objeto ou designação
literal da fonte. A página mostra:

- valores e datas, com “dados indisponíveis” quando a fonte não os fornece;
- contagens e SHA-256 do lote;
- URL, data, hash e arquivo do ficheiro anual;
- cobertura temporal do catálogo;
- tamanho arquivado e catalogado, partes observadas e limitações do `SyncRun`;
- seis confirmações humanas explícitas antes de criar o processo `PENDING`.

Pesquisar texto não produz qualquer correspondência. Aprovar o processo também não publica nada:
a criação transacional e a retirada imutável de contratos, organizações e relações pertencem à
porta específica seguinte.

## Estado operacional

Esta entrega prepara código, painel e testes. Não executa migrações remotas, não recolhe ZIP, não
altera staging, não cria utilizadores e não escreve em produção. Sem uma execução autorizada e
atestada do catálogo e dos lotes anuais, o resultado correto do painel é “dados indisponíveis”.

Fontes institucionais de enquadramento:

- [dataset oficial de contratos do Portal BASE no dados.gov.pt](https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/);
- [formas oficiais de obter dados descritas pelo Portal BASE](https://www.base.gov.pt/Base4/pt/documentacao/formas-de-obter-dados-sobre-os-contratos-publicos/).
