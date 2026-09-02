# V5.51 — publicação e retirada específicas de contratos Portal BASE

## Resultado

A V5.51 acrescenta a primeira projeção pública do Investigador Cívico que pode nascer da porta
editorial BASE. Esta entrega prepara código, migração, painel e testes; não executa a migração em
staging ou produção e não publica contratos reais.

Um contrato só pode avançar depois de o respetivo caso `PUBLIC_CONTRACT`:

1. ter sido criado pela ingestão V5.50 a partir de um snapshot de ano encerrado;
2. ter passado por revisão humana e decisão privada `APPROVE` com a fonte confirmada;
3. voltar a coincidir, no servidor, com o snapshot, o lote, o catálogo, o arquivo e todos os
   SHA-256 que foram aprovados;
4. receber uma nova confirmação de um administrador autenticado com MFA.

A aprovação privada continua sem publicar. A ação pública é um endpoint diferente, usa outro
pedido explícito e acrescenta decisão e evento próprios.

## O que é publicado

A projeção pode conter somente os campos factuais do registo oficial:

- identificador oficial do contrato;
- objeto;
- tipo de procedimento;
- CPV, montantes e moeda quando constam da fonte;
- datas de decisão, assinatura e publicação quando disponíveis;
- prazo de execução quando disponível;
- ligação à fonte anual, data de recolha e SHA-256.

A prova declara `SPECIFIC_SOURCE_RECORD_ONLY`. Não afirma que o ficheiro anual está completo, que
uma ausência significa inexistência de contratos, nem que o ano corrente está encerrado.

## O que esta porta nunca publica ou cria

As partes observadas no ficheiro anual permanecem no staging privado. Nesta operação são sempre
iguais a zero:

- `PublicContractParty` publicados;
- `Organisation` criadas;
- `InterestEntity` criadas;
- `ContractMatchReview` criadas;
- `InterestRelationship` criadas.

Uma designação textual não prova a identidade de uma organização. O HMAC de um identificador
fiscal também não é devolvido ao browser, não entra na fotografia pública e não é usado por esta
porta. Não existe correspondência por nome, normalização aproximada ou fuzzy matching.

Até existir uma porta editorial independente para as partes, a consulta pública devolve
explicitamente `parties=[]` e um trigger PostgreSQL rejeita `INSERT`, `UPDATE` ou `DELETE` de
`PublicContractParty` num contrato que já tenha fotografia V5.51. Esta barreira cobre também uma
escrita concorrente imediatamente posterior à transação de publicação.

Uma futura organização terá de entrar por uma fonte oficial independente com identificador
inequívoco e processo editorial próprio. Uma futura relação terá de provar separadamente ambos os
nós, o tipo, as datas, a fonte e a revisão.

## Fotografia pública imutável

`base_public_contract_publication_snapshots` conserva os campos exatos de cada publicação e liga-os
a:

- `BaseContractSnapshot` privado;
- `EditorialCase`;
- `EditorialVersion`;
- `SourceDocument`;
- `PublicContract` estável.

A tabela tem RLS, privilégios públicos revogados e triggers que proíbem `UPDATE`, `DELETE` e
`TRUNCATE`.
`PublicContract` funciona apenas como projeção de consulta e aponta para a fotografia atual. Um
trigger PostgreSQL impede que os seus campos divirjam dessa fotografia. Se uma recolha oficial
posterior exigir correção, a publicação anterior permanece e uma nova versão só pode suceder a uma
projeção previamente retirada.

Uma republicação exige sempre uma nova fotografia. No `COMMIT`, um trigger diferido confirma ainda
que o último evento público pertence ao mesmo processo e versão da fotografia e que a respetiva
ação `PUBLISH` ou `WITHDRAW` coincide com o estado da projeção.

Cada publicação acrescenta, na mesma transação:

1. fotografia pública append-only;
2. projeção `PublicContract` verificada e publicada;
3. `DataPublicationReview` positiva;
4. `AuditEvent`;
5. `EditorialDecision(PUBLISH)`;
6. `EditorialPublicationEvent(PUBLISH)` com SHA-256.

Qualquer divergência reverte a transação inteira.

## Retirada

A retirada é uma operação `ADMIN` + MFA diferente. Só fica disponível quando a publicação, a
fotografia, a revisão, a auditoria, o evento e os hashes continuam a coincidir. A categoria do
fundamento pertence ao vocabulário fechado da governação anti-interferência.

A retirada:

- muda apenas a projeção ativa para `WITHDRAWN`;
- acrescenta revisão pública negativa, auditoria, decisão e evento `WITHDRAW`;
- não apaga o contrato;
- não apaga a fotografia publicada;
- não apaga a versão ou decisões editoriais;
- não apaga fontes ou hashes;
- não apaga direitos de resposta.

Enquanto organizações e relações ainda não tiverem um circuito coordenado, a retirada do contrato
fica bloqueada se forem detetadas partes públicas, candidatos de correspondência ou relações
dependentes. Isto impede deixar um grafo órfão ou ocultar apenas uma parte do histórico.

## Direito de resposta

O alvo público estável usa `target_type=PUBLIC_CONTRACT` e o identificador interno de
`PublicContract`. Uma resposta é anexada com timestamp e hashes pelo circuito já existente. A
retirada não a modifica nem elimina. A V5.51 inclui um teste de integração que submete uma resposta,
retira o contrato e confirma que contrato, fotografia, eventos e resposta continuam presentes.

## Endpoints privados

| Método | Endpoint | Autoridade | Efeito |
|---|---|---|---|
| `GET` | `/api/v1/editorial/base/cases/{case_id}/publication` | staff + MFA | Pré-visualização read-only |
| `POST` | `/api/v1/editorial/base/cases/{case_id}/publication` | `ADMIN` + MFA | Publicação transacional exata |
| `GET` | `/api/v1/editorial/base/cases/{case_id}/withdrawal` | staff + MFA | Efeito e provas read-only |
| `POST` | `/api/v1/editorial/base/cases/{case_id}/withdrawal` | `ADMIN` + MFA | Retirada append-only |

O painel do processo mostra todos os hashes e exige as confirmações explícitas. Uma pessoa com
papel `REVIEWER` pode inspecionar a prova, mas não confirmar a publicação ou a retirada.

## Validação e ativação

A migração falha de forma fechada se encontrar um contrato legado já marcado
como publicado, retirado ou verificado sem uma fotografia V5.51. Não converte,
apaga nem legitima automaticamente essa linha: a equipa tem de investigar a
origem e documentar a resolução antes de repetir a migração.

O teste de integração escreve apenas numa base PostgreSQL descartável cujo nome termina em `_test`
e que contém o marcador de segurança esperado. Exercita a sequência completa: proposta privada,
revisão, aprovação, rejeição de prova adulterada, falhas tardias com rollback integral na publicação
e na retirada, consulta pública, direito de resposta e retirada efetiva. O mesmo teste tenta ainda
alterar ou apagar a fotografia, divergir ou apagar a projeção, anexar uma parte depois do `COMMIT`
e mudar o estado sem o evento correspondente; todas essas escritas têm de falhar.

Antes de qualquer ativação real continuam obrigatórios:

- CI integral verde com PostgreSQL 17 e Python 3.13.15;
- migração e inspeção exclusivamente em staging;
- inventário read-only antes e depois da migração;
- confirmação de que não existem projeções BASE legadas sem evento específico;
- conta administrativa de staging com MFA;
- ensaio de publicação apenas com fixture ou registo explicitamente autorizado;
- revisão da AIPD e das bases jurídicas aplicáveis;
- backup e restauro isolado após o conjunto final de migrações da V5.

Esta entrega não autoriza ingestão, revisão, publicação ou retirada de dados reais.
