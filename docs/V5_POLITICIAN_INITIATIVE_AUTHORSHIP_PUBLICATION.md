# V5.43 — publicação transacional de autoria individual de iniciativas

## Resultado

A V5.43 fecha a porta pública que sucede à recolha e proposta privada da V5.42. Uma autoria só pode
entrar na ficha de uma pessoa quando o servidor reconstrói e confirma simultaneamente:

1. a versão editorial atual está `APPROVED` e a aprovação confirmou a fonte;
2. a observação privada continua a declarar literalmente `AUTHOR`;
3. o `idCadastro` coincide exatamente com `people.source_id` de uma pessoa ativa e revista;
4. o `IniId` coincide exatamente com uma iniciativa pertencente a uma fotografia de atividade com
   revisão pública positiva;
5. os bytes das fontes de autoria e de atividade continuam arquivados e atestados;
6. os SHA-256 da versão, relação, fotografia e documentos continuam a coincidir;
7. um administrador autenticado com MFA confirma expressamente o efeito público.

Nome parlamentar, nome civil e sigla partidária continuam a ser apenas texto de apresentação. Não
existe fuzzy matching, comparação aproximada ou associação por partido.

## Projeção append-only

A tabela `politician_initiative_authorships` conserva apenas a ligação mínima necessária:

- pessoa já existente;
- iniciativa já existente e já revista no âmbito de atividade;
- observação privada exata;
- relação literal `AUTHOR`;
- documento que prova a autoria;
- SHA-256 do registo original.

A tabela rejeita `UPDATE` e `DELETE`, tem RLS ativa e não concede acesso direto a `anon` ou
`authenticated`. A API pública lê-a apenas através da projeção fail-closed do backend.

## Transação de publicação

Uma única transação PostgreSQL acrescenta:

1. uma linha de autoria pública;
2. uma `DataPublicationReview(POLITICIAN_INITIATIVE_AUTHORSHIP)` positiva;
3. um `AuditEvent(PUBLISHED)`;
4. uma decisão editorial `PUBLISH`;
5. um `EditorialPublicationEvent(PUBLISH)`.

Antes do commit, uma consulta independente volta a provar pessoa, iniciativa, observação, relação,
arquivos e últimas revisões positivas. Se um identificador, revisão ou hash divergir, toda a operação
é revertida. Uma tentativa com prova desatualizada não deixa linha, revisão, auditoria, decisão ou
evento parcial.

## Efeito na ficha pública

A ficha mostra a iniciativa apenas enquanto permanecem positivas:

- a revisão atual da identidade;
- a revisão da fotografia de atividade que contém a iniciativa;
- a revisão específica da autoria.

Cada item conserva a fonte oficial que declara a autoria, data de recolha e SHA-256. A mensagem de
cobertura esclarece que autoria não demonstra sentido de voto, apoio futuro, mérito da iniciativa ou
posição coletiva do partido. Quando não existe uma relação publicada, a interface apresenta dados
indisponíveis; nunca conclui que a pessoa não foi autora.

## Limites desta etapa

- não cria pessoas, iniciativas, mandatos, cargos ou filiações;
- não publica propostas apenas aprovadas;
- não transforma autoria em voto ou recomendação política;
- não executa migrações nem operações sobre staging ou produção;
- não inclui ainda a retirada específica, que pertence à V5.44;
- não afirma cobertura histórica completa dos ficheiros da Assembleia da República.

Esta entrega prepara código, migração, painel e testes. A ativação real continua dependente dos gates
operacionais, jurídicos, de backup e de restauro da release V5.

## Evidência verificável

O ensaio PostgreSQL descartável cobre publicação válida, rollback de uma prova incorreta,
idempotência, bloqueio de mutações e aparecimento na ficha pública. As validações locais e o CI usam
PostgreSQL 17 descartável; nenhuma base de dados real é necessária ou autorizada por esta etapa.

A fonte oficial da relação continua documentada na
[V5.42](V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md), incluindo URL oficial, data de verificação e
SHA-256 do documento observado.
