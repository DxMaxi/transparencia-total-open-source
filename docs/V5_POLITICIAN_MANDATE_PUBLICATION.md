# V5.34 — publicação transacional de mandatos parlamentares

## Objetivo

A V5.34 acrescenta uma porta de publicação específica ao circuito privado da V5.33. Um mandato só
pode ser acrescentado depois de a situação oficial ter sido revista e aprovada por uma pessoa. A
publicação volta a reconstruir a prova no servidor e exige uma conta `ADMIN` com MFA.

O ponto de partida permanece a
[página oficial de atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx),
o recurso identificado no
[catálogo de dados abertos da Assembleia da República](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx)
e os bytes arquivados com data de recolha e SHA-256.

## Prova relacional exata

Cada novo `Mandate` guarda, além da pessoa, fonte, legislatura, círculo e datas:

- `source_observation_id`, ligado por chave estrangeira à observação privada imutável;
- `source_period_ordinal`, que identifica a posição exata em `DepSituacao`;
- `source_period_sha256`, calculado sobre a representação canónica do intervalo.

As três colunas formam um conjunto inseparável. Um índice único impede que a mesma situação da
mesma observação seja publicada duas vezes. As linhas históricas anteriores à V5.34 continuam
compatíveis, mas não satisfazem esta nova porta sem uma recolha e revisão próprias.

## Preview privado e confirmação

`GET /api/v1/editorial/parliament/mandate-cases/{case_id}/publication` exige staff autenticado com
MFA e não escreve na base. O servidor volta a verificar:

- processo `PARLIAMENT_MANDATE_SITUATION` em `APPROVED`;
- última decisão `APPROVE`, ligada à versão atual e com fonte confirmada;
- igualdade integral entre a versão aprovada e a prova reconstruída;
- `DepId` oficial exato, identidade pública e revisão `PERSON` positiva da mesma fonte;
- círculo, datas, manifesto, URL, data de recolha, SHA-256 e atestação de arquivo;
- inexistência de mandato para o mesmo intervalo ou para a mesma pessoa, cargo e início;
- ausência de filiação partidária nesta porta.

O browser recebe um novo `publication_proof_sha256`. Não envia nomes, datas ou conteúdo
normalizado como autoridade.

## Transação ADMIN com MFA

`POST /api/v1/editorial/parliament/mandate-cases/{case_id}/publication` exige seis confirmações,
fundamentação privada e fundamentação pública factual. Sob bloqueio transacional, volta a calcular
toda a prova e acrescenta, ou então reverte tudo:

1. um `Mandate` com a referência exata ao intervalo;
2. uma `DataPublicationReview(MANDATE)` positiva;
3. um `AuditEvent(MANDATE, PUBLISHED)`;
4. uma decisão editorial `PUBLISH`;
5. um `EditorialPublicationEvent` com alvo `MANDATE`;
6. a projeção do processo em `PUBLISHED`.

Não cria pessoas, partidos, filiações, cargos adicionais ou datas em falta. A consulta pública já
exige a última revisão `MANDATE` positiva, fonte oficial não noticiosa e arquivo atestado; a própria
transação confirma essa porta antes do commit. A ficha pública mostra a ligação oficial, a data de
recolha, o SHA-256 da fonte, o SHA-256 do intervalo e a data de revisão. Linhas históricas sem a
nova prova específica permanecem identificadas como `dados indisponíveis` nesse campo.

## Histórico imutável

A migração torna `mandates` e `data_publication_reviews` append-only na base de dados. `UPDATE` e
`DELETE` são rejeitados mesmo que uma chamada de aplicação tente executá-los. Uma correção terá de
usar nova fonte, nova observação e nova linha; uma retirada acrescentará uma revisão negativa,
auditoria, decisão e evento sem apagar o mandato original.

## Limite operacional

Esta entrega prepara e testa a capacidade. Não migra staging ou produção, não cria utilizadores,
não altera segredos e não publica dados reais. A ativação real continua bloqueada até a V5.35
implementar e provar a retirada imutável específica do mandato.

Integrar código, executar uma migração ou aprovar um processo nunca chama automaticamente a
operação de publicação.
