# V5.32 — republicação por nova fotografia imutável

## Objetivo

A V5.32 fecha o ciclo de vida da primeira projeção pública de perfis políticos. Uma fotografia
retirada pela V5.31 nunca volta ao estado ativo. A única republicação permitida parte de outro
documento oficial arquivado, outra fotografia normalizada, outros processos editoriais e uma nova
decisão humana integral.

Esta entrega formaliza e testa o comportamento já deliberadamente suportado pelas portas V5.28 a
V5.31. Não acrescenta um atalho de reativação, não executa operações reais e não altera staging,
produção, Supabase, segredos ou utilizadores.

## Novo ciclo obrigatório

A fotografia posterior percorre novamente todas as etapas:

1. recolha privada de novos bytes oficiais;
2. `SourceDocument` com URL oficial, data de recolha e SHA-256;
3. atestação de arquivo coincidente em URL, data e SHA-256;
4. nova `ParliamentDeputySnapshot` e novas observações imutáveis;
5. um processo `POLITICIAN_PROFILE` novo por observação;
6. revisão humana `PENDING → IN_REVIEW → APPROVED` da versão exata;
7. nova inspeção integral de prontidão;
8. publicação administrativa com MFA numa única transação.

Nem a ingestão nem a aprovação chamam automaticamente a publicação.

## Identidade sem aproximações

Quando a nova fotografia contém o mesmo `DepId` oficial inequívoco, a pessoa existente é
reutilizada. Não há comparação aproximada de nomes, siglas ou grafias. Uma função incompatível ou
uma identidade inativa bloqueia toda a fotografia.

A nova observação cria uma `ParliamentaryMembershipSnapshot` ligada à nova fonte. A pertença
anterior permanece intacta e auditável. A publicação continua a criar zero mandatos e zero ligações
partidárias, porque esses factos exigem fontes e identificadores próprios.

## Prova PostgreSQL descartável

O teste de integração executa o ciclo completo:

- publica a primeira fotografia;
- confirma que uma prova errada não deixa qualquer escrita parcial;
- retira a fotografia integralmente;
- confirma que pessoas, pertenças, versões e eventos anteriores permanecem;
- ingere uma segunda fonte oficial com outro SHA-256;
- cria e aprova novos processos para a segunda fotografia;
- reutiliza a pessoa apenas pelo mesmo `DepId` exato;
- publica a nova fotografia sem criar uma pessoa duplicada;
- confirma que a consulta pública usa apenas a nova fonte;
- confirma que o processo antigo continua `WITHDRAWN` com eventos `PUBLISH` e `WITHDRAW`;
- confirma que o processo novo fica `PUBLISHED` com um novo evento `PUBLISH`;
- rejeita uma tentativa posterior de publicar novamente a versão antiga.

O CI aplica esta prova apenas numa base PostgreSQL 17 descartável criada para o job.

## Estado público e histórico

Depois da retirada e antes da nova publicação, a consulta apresenta **dados indisponíveis** quando
não existe outra fotografia integralmente aprovada. Depois da nova publicação, o diretório escolhe
a nova fonte completa. A fotografia retirada, a fonte anterior e todos os seus hashes continuam no
histórico privado e nos eventos imutáveis; não são apagados nem sobrescritos.

## Limite operacional

V5.32 é código, documentação e prova automatizada. Não declara que uma fotografia real foi
republicada. Deployment, migração, ingestão e revisão nunca executam a operação por si próprios.
Uma futura ativação em staging continuará a exigir destino segregado, inventário read-only,
utilizadores por convite, MFA e confirmação humana explícita.
