# V5.40 — publicação transacional de uma reunião integral de presenças

## Objetivo e limite

A V5.40 acrescenta a porta pública específica que a V5.39 deixou deliberadamente ausente. Uma
reunião plenária só pode ser publicada por inteiro, depois de uma pessoa a aprovar e de um
administrador com MFA confirmar novamente a fonte e o efeito público. A operação não permite
escolher deputados, não cria identidades, mandatos ou filiações e não transforma uma falta em
incumprimento, culpa ou juízo de mérito.

Esta entrega não publica dados reais. Prepara código, migração, painel, contratos e testes num
PostgreSQL descartável; não executa migração em staging ou produção, não revê dados reais e não
altera utilizadores, segredos ou configuração remota.

## Prova reconstruída no servidor

`GET /api/v1/editorial/parliament/attendance-cases/{case_id}/publication` é read-only. A resposta
só fica elegível quando o servidor volta a provar, sem confiar em conteúdo enviado pelo browser:

- processo `POLITICIAN_PROFILE` com `subject_type=PARLIAMENT_ATTENDANCE_SNAPSHOT` e última decisão
  `APPROVE` sobre a versão atual;
- URL oficial HTTPS da Assembleia da República, data de recolha, SHA-256 do documento e atestação
  dos mesmos bytes no arquivo privado;
- SHA-256 normalizado, versão do parser e contagens do manifesto iguais às linhas materializadas;
- zero estados `UNKNOWN`;
- uma identidade pública ativa por cada BID oficial exato, com revisão positiva e fonte arquivada;
- exatamente um mandato a cobrir a data por identidade, também com revisão positiva e fonte
  arquivada;
- versão editorial igual à proposta integral reconstruída a partir das observações append-only;
- inexistência de sessão, presença, revisão ou evento público anterior para a fotografia.

O `mapping_sha256` cobre, em ordem canónica, as referências SHA-256 da observação, BID, pessoa e
mandato, o hash do registo, o estado literal e a projeção booleana. IDs pessoais em claro não são
devolvidos nesta prova. O `publication_proof_sha256` liga esse mapa ao processo, versão, fonte,
fotografia, data, contagens e efeito público esperado.

## Publicação tudo-ou-nada

`POST /api/v1/editorial/parliament/attendance-cases/{case_id}/publication` exige papel `ADMIN`,
autenticação `aal2`, todas as confirmações explícitas e repetição exata dos hashes da
pré-visualização. Um bloqueio transacional impede concorrência sobre o mesmo processo. Na mesma
transação são acrescentados:

1. uma `ParliamentarySession` ligada à fotografia privada por `attendance_snapshot_id`;
2. todas as `AttendanceRecord`, cada uma ligada à observação e ao SHA-256 de origem;
3. uma revisão positiva `PARLIAMENT_ATTENDANCE_SNAPSHOT` para a reunião integral;
4. um `AuditEvent` agregado, sem publicar BID ou IDs internos;
5. a decisão editorial `PUBLISH` e a mudança para `PUBLISHED`;
6. um `EditorialPublicationEvent` imutável da fotografia completa.

Se uma identidade, mandato, contagem, estado, hash, arquivo ou projeção pública divergir, a
transação recua por inteiro. O teste de integração confirma que uma prova alterada cria zero
sessões e que a repetição da publicação é recusada.

## Histórico e consulta pública

As novas ligações tornam cada presença derivável da observação oficial exata. As linhas
`attendance_records` passam a rejeitar `UPDATE` e `DELETE`; as sessões já eram append-only. As
chaves estrangeiras novas usam `ON DELETE RESTRICT`. Linhas históricas anteriores permanecem
compatíveis, mas não entram nesta porta sem o conjunto completo de prova.

A ficha pública agrega apenas reuniões cuja revisão integral mais recente é positiva e volta a
exigir pessoa, BID, mandato, fonte e arquivo. O total não é atribuído enganadoramente a um único
documento: cada reunião visível leva o seu URL oficial, data de recolha, SHA-256 da fonte, data de
revisão e SHA-256 do registo individual. A interface explica que a cobertura corresponde apenas às
reuniões efetivamente publicadas e que uma falta reproduz o estado da fonte nessa data.

## Limites e etapa seguinte

- uma reunião publicada não representa, por si só, a totalidade do trabalho parlamentar;
- uma reunião ainda não recolhida ou não revista aparece como **dados indisponíveis**;
- IA não interpreta estados, não preenche ausências e não participa na decisão de publicação;
- não existe correspondência por nome, sigla, semelhança ou fuzzy matching;
- a V5.40 não ativa esta porta em staging ou produção.

Antes de uma ativação real, a retirada imutável V5.41 da reunião inteira tem de ser acrescentada
e provada. Essa retirada deverá criar uma revisão negativa, auditoria, decisão e evento próprios,
preservando sessão, linhas, fonte, versão e publicação original.
