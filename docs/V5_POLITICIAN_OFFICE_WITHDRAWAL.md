# V5.38 — retirada transacional e imutável de um cargo parlamentar

## Objetivo

A V5.38 fecha o ciclo específico iniciado nas V5.36 e V5.37. Um cargo parlamentar publicado pode
deixar de integrar a consulta ativa apenas por uma decisão humana explícita, ligada à mesma fonte oficial,
à mesma data de recolha, ao mesmo SHA-256, ao mesmo `DepId`, ao mesmo `CarId`, ao mesmo
círculo, ao mesmo período e à prova da publicação original.

O cargo não é apagado nem alterado. A retirada acrescenta uma revisão negativa; a leitura pública
fail-closed deixa de selecionar essa linha, mas preserva a fonte, a versão, a revisão positiva, a
publicação, a auditoria e todas as decisões anteriores. Um cargo continua separado de um mandato e
a operação não cria nem altera filiação partidária.

As fontes de origem continuam a ser a
[atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx) e o
[catálogo de dados abertos da Assembleia da República](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx).
A IA não participa nesta decisão e nunca é tratada como fonte.

## Preview privado sem escrita

`GET /api/v1/editorial/parliament/office-cases/{case_id}/withdrawal` exige staff autenticado com
MFA e reconstrói, no servidor:

- o processo `PUBLISHED`, a versão atual e a última decisão `PUBLISH`;
- a observação, o `DepId`, o `CarId`, o círculo e o período oficiais exatos, sem correspondência
  aproximada de nomes;
- a identidade e a fotografia parlamentar ligadas à mesma fonte;
- a revisão pública `PARLIAMENT_OFFICE` positiva mais recente;
- o `AuditEvent(PARLIAMENT_OFFICE, PUBLISHED)` e o evento editorial de publicação;
- os hashes da publicação original e o efeito público previsto da retirada;
- a URL oficial, a data de recolha, o SHA-256 do documento e a atestação do arquivo.

O preview calcula `withdrawal_proof_sha256` e `public_effect_sha256`. Não altera a base de dados e
declara que serão eliminados zero cargos, zero pessoas e zero fotografias de pertença parlamentar.

## Transação ADMIN com MFA

`POST /api/v1/editorial/parliament/office-cases/{case_id}/withdrawal` exige uma categoria fechada
da governação, fundamentação privada, fundamentação pública factual e seis confirmações explícitas.
Depois de repetir toda a prova sob bloqueio transacional, acrescenta em conjunto:

1. uma `DataPublicationReview(PARLIAMENT_OFFICE)` negativa;
2. um `AuditEvent(PARLIAMENT_OFFICE, WITHDRAWN)` com o antes, o depois e os hashes confirmados;
3. uma decisão editorial `WITHDRAW`, de `PUBLISHED` para `WITHDRAWN`;
4. um `EditorialPublicationEvent(WITHDRAW)` para o mesmo cargo;
5. apenas o novo estado e a nova revisão do processo editorial.

Antes do commit, confirma que `parliamentary_office_periods` conserva a linha e que a projeção
pública já não a aceita. Qualquer divergência reverte tudo. Uma segunda retirada da mesma versão é
recusada pelo estado e pela unicidade do evento.

## Imutabilidade, efeito público e correções

Não existe `UPDATE` nem `DELETE` sobre `parliamentary_office_periods` ou
`data_publication_reviews`. Os triggers da V5.37 recusam também essas mutações diretamente no
PostgreSQL. `AuditEvent`, versões, decisões e eventos editoriais são append-only.

A identidade, os mandatos e os outros cargos não mudam. Se não restar outro cargo público, a área
correspondente apresenta dados indisponíveis; essa ausência não prova inexistência, irregularidade
ou incumprimento. Uma correção publicável exige nova fonte arquivada, nova observação ou período,
nova versão e nova revisão humana; nunca reescreve a linha anterior.

Esta entrega prepara e testa o circuito numa base PostgreSQL descartável. Não executa operações
sobre dados reais, não migra staging ou produção, não altera segredos e não retira qualquer
publicação real. Deploy, migração, aprovação editorial, publicação e retirada continuam ações
separadas e nunca são encadeadas automaticamente.
