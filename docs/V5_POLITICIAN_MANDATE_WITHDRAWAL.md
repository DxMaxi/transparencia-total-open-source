# V5.35 — retirada transacional e imutável de um mandato

## Objetivo

A V5.35 fecha o ciclo específico iniciado nas V5.33 e V5.34. Um mandato publicado pode deixar de
integrar a consulta ativa apenas por uma decisão humana explícita, ligada à mesma fonte oficial, à
mesma data de recolha, ao mesmo SHA-256, ao mesmo intervalo e à prova da publicação original.

O mandato não é apagado nem alterado. A retirada acrescenta uma revisão negativa; por isso, a
leitura pública fail-closed deixa de selecionar a linha, mas a fonte, a versão, a publicação, a
auditoria e todas as decisões anteriores continuam disponíveis no histórico.

As fontes de origem continuam a ser a
[atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx) e o
[catálogo de dados abertos da Assembleia da República](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx).
A IA não participa nesta decisão e nunca é tratada como fonte.

## Preview privado sem escrita

`GET /api/v1/editorial/parliament/mandate-cases/{case_id}/withdrawal` exige staff autenticado com
MFA e reconstrói, no servidor:

- o processo `PUBLISHED`, a versão atual e a última decisão `PUBLISH`;
- a observação e o `DepId` oficiais exatos, sem pesquisa aproximada de nomes;
- o intervalo, a posição, as datas observadas e o seu SHA-256;
- a pessoa e o círculo ligados à mesma fonte, sem inferir partido;
- a revisão pública `MANDATE` positiva mais recente;
- o `AuditEvent(MANDATE, PUBLISHED)` e o evento editorial de publicação;
- os hashes da publicação original e o efeito público previsto da retirada;
- a URL oficial, a data de recolha, o SHA-256 do documento e a atestação do arquivo.

O preview calcula `withdrawal_proof_sha256` e `public_effect_sha256`. Não altera a base de dados e
declara expressamente que serão eliminados zero mandatos, zero pessoas e zero fotografias de
pertença parlamentar.

## Transação ADMIN com MFA

`POST /api/v1/editorial/parliament/mandate-cases/{case_id}/withdrawal` exige uma categoria fechada
da governação, fundamentação privada, fundamentação pública factual e seis confirmações explícitas.
Depois de repetir toda a prova sob bloqueio transacional, acrescenta em conjunto:

1. uma `DataPublicationReview(MANDATE)` negativa;
2. um `AuditEvent(MANDATE, WITHDRAWN)` com o antes, o depois e os hashes confirmados;
3. uma decisão editorial `WITHDRAW`, de `PUBLISHED` para `WITHDRAWN`;
4. um `EditorialPublicationEvent(WITHDRAW)` para o mesmo mandato;
5. apenas o novo estado e a nova revisão do processo editorial.

Antes do commit, confirma que a linha `Mandate` continua presente e que a seleção pública já não a
aceita. Qualquer divergência reverte tudo. Uma segunda retirada da mesma versão é recusada pelo
estado e pela unicidade do evento.

## Imutabilidade e correções

Não existe `UPDATE` nem `DELETE` sobre `mandates` ou `data_publication_reviews`. Os triggers já
instalados pela V5.34 também recusam essas mutações diretamente no PostgreSQL. `AuditEvent`, versões,
decisões e eventos editoriais são igualmente append-only.

Se a fonte oficial corrigir o facto, a retirada preserva a publicação antiga. Uma eventual correção
publicável exigirá uma nova fonte arquivada, uma nova observação ou prova de período, uma nova versão
e nova revisão humana; nunca reescreve a linha anterior.

## Efeito público e limites

A identidade e os outros mandatos não mudam. O perfil continua sujeito à sua própria porta de
publicação. Se não restar outro mandato público, a área correspondente apresenta dados
indisponíveis; essa ausência não prova inexistência nem incumprimento.

Esta entrega prepara e testa o circuito numa base PostgreSQL descartável. Não executa operações
sobre dados reais, não migra staging ou produção, não altera segredos e não retira qualquer
publicação real. Deploy, migração, aprovação editorial, publicação e retirada continuam ações
separadas e nunca são encadeadas automaticamente.
