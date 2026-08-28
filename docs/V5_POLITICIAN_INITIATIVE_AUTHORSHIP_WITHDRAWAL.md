# V5.44 — retirada imutável de autoria individual de iniciativas

## Resultado

A V5.44 fecha o ciclo iniciado pela recolha privada V5.42 e pela publicação específica V5.43. Uma
autoria publicada pode sair da consulta ativa, mas a ligação `AUTHOR`, as fontes, os bytes
arquivados, os SHA-256, a versão aprovada, a auditoria e o evento de publicação nunca são apagados
nem alterados.

A retirada exige uma nova ação `ADMIN` com MFA e uma categoria pública fechada. Conveniência
política, pressão externa ou mudança editorial sem prova não são categorias válidas.

## Preview read-only e prova de retirada

`GET /api/v1/editorial/parliament/initiative-authorship-cases/{case_id}/withdrawal` volta a
reconstruir, sem escrever:

1. o processo `PUBLISHED` e a última decisão `PUBLISH`;
2. a versão editorial e a relação privada original;
3. `IniId`, `idCadastro` e relação literal `AUTHOR`;
4. a pessoa e a iniciativa já publicadas por identificadores oficiais exatos;
5. os arquivos das fontes de autoria e de atividade;
6. as últimas revisões positivas da identidade, fotografia de atividade e autoria;
7. o evento e a auditoria imutáveis da publicação V5.43;
8. o efeito público exato, incluindo quantas outras autorias permanecem visíveis para a pessoa.

O servidor calcula `withdrawal_proof_sha256` e `public_effect_sha256`. Se qualquer fonte, revisão,
identificador, relação, versão ou hash divergir, o preview fica bloqueado e não oferece uma prova
utilizável ao formulário.

## Transação append-only

`POST /api/v1/editorial/parliament/initiative-authorship-cases/{case_id}/withdrawal` exige a mesma
revisão, versão, alvo, fontes, provas e efeito observados no preview. Uma única transação acrescenta:

1. uma `DataPublicationReview(POLITICIAN_INITIATIVE_AUTHORSHIP)` negativa;
2. um `AuditEvent(WITHDRAWN)` com categoria e efeito público;
3. uma decisão editorial `WITHDRAW`;
4. um `EditorialPublicationEvent(WITHDRAW)`.

Antes do commit, o servidor confirma que a linha de autoria continua presente, que a última revisão
já a exclui da consulta ativa e que o efeito público calculado não mudou. Uma prova desatualizada
reverte tudo: não fica revisão, auditoria, decisão ou evento parcial.

## O que permanece imutável

A retirada cria zero eliminações e zero alterações em:

- `politician_initiative_authorships`;
- pessoa e `idCadastro` oficial;
- iniciativa e `IniId` oficial;
- fontes, arquivos e hashes;
- versão e aprovação editoriais;
- evento e auditoria de publicação;
- filiações partidárias, votos, mandatos, cargos ou outras autorias.

A interface pública deixa apenas de incluir a ligação cuja última revisão é negativa. “Não está na
consulta ativa” não significa “nunca foi autora”, “não apoia a iniciativa” ou qualquer juízo sobre a
pessoa ou o partido.

## Correção e republicação

Uma relação retirada não é reativada por alterar a linha ou a revisão anterior. Uma correção exige
nova fonte oficial arquivada, nova fotografia privada, novo processo/versão, nova revisão humana e
nova decisão de publicação. O histórico anterior permanece consultável para auditoria e para o
direito de resposta.

## Limites operacionais

- não executa uma retirada real em staging ou produção;
- não migra nem configura Supabase;
- não cria ou altera utilizadores, funções ou segredos;
- não associa pessoas por nome ou partido e não usa fuzzy matching;
- não usa IA como fonte e não infere voto, apoio, mérito ou posição coletiva;
- não afirma cobertura histórica completa quando a fonte ainda não foi recolhida e revista.

## Evidência de teste

O ensaio PostgreSQL descartável cobre preview, prova incorreta com rollback, retirada válida,
segunda tentativa recusada, revisão negativa mais recente, preservação append-only da ligação e
desaparecimento da autoria apenas da ficha pública ativa. O CI usa PostgreSQL 17 descartável e não
precisa de acesso a dados reais.

A prova oficial da estrutura `iniAutorDeputados`, com URL, data e SHA-256 dos bytes verificados,
permanece documentada em
[V5.42 — autoria individual de iniciativas](V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md).
