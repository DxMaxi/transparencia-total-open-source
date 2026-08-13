# V5.9 — diretório político paginado e auditável

## Objetivo e limite

A V5.9 torna o diretório público de políticos consultável por páginas pequenas, com pesquisa
partilhável e um total exato quando a API o consegue provar. A consulta trabalha apenas sobre
identidades já publicadas: não cria pessoas, não liga fontes, não altera revisões e não transforma
uma coincidência textual numa associação factual.

Esta entrega é exclusivamente de código e validação local. Não publica nem altera dados reais,
não aplica migrações, não configura o Supabase, não cria utilizadores, não altera segredos e não
executa operações em staging ou produção.

## Contrato público V5

O endpoint `GET /api/v1/public/politicians/explore` recebe:

- `q`, para limitar a lista já publicada por texto visível;
- `party_short`, para limitar pelo grupo indicado na fonte;
- `limit`, entre 1 e 100, com 24 registos por omissão;
- `cursor`, opaco, limitado a 512 caracteres e ligado aos filtros usados para o criar.

A resposta inclui os perfis da página, total exato do conjunto filtrado, grupos disponíveis com
contagens, limite e cursor seguinte. O endpoint antigo `GET /api/v1/public/politicians` permanece
inalterado para compatibilidade durante a transição entre frontend e backend.

## Paginação progressiva

A ordenação usa o nome público e o `slug` público como desempate estável. A página seguinte é
selecionada por cursor, não por `OFFSET`, evitando que páginas profundas obriguem a base a percorrer
todos os registos anteriores. O cursor contém apenas estes valores de apresentação e uma impressão
dos filtros; não contém email, NIF, UUID de autenticação, nota editorial ou segredo.

O cursor é recusado quando:

- não é Base64 URL-safe e JSON válidos;
- tem uma versão ou estrutura desconhecida;
- excede os limites definidos;
- foi criado para outra pesquisa ou outro grupo.

Não existe uma opção para ignorar estas validações.

## Pesquisa não é correspondência

A pesquisa textual serve exclusivamente para uma pessoa encontrar cartões que já pertencem à
projeção pública aprovada. Não existe fuzzy matching, trigramas, distância de Levenshtein, inferência
de identidade ou promoção de candidatos. Um resultado de pesquisa não é uma nova conclusão e não
altera a fonte, a revisão ou o âmbito de cobertura de qualquer perfil.

Cada cartão continua a conservar:

- URL oficial;
- data de recolha;
- SHA-256 do documento;
- data de observação;
- data da revisão humana.

A lista continua a exigir uma revisão positiva ligada à mesma fonte parlamentar e uma atestação
válida do arquivo. Recolher uma pessoa não basta para a publicar.

## Compatibilidade fail-closed

Enquanto a API em produção não disponibilizar o novo endpoint, o frontend pode consultar o contrato
anterior, com um máximo de 500 perfis. O total só é apresentado como exato se a contagem pública e o
número de perfis devolvidos coincidirem. Se essa igualdade não existir, a interface declara a
consulta parcial e mostra “total ainda não confirmado”.

Não são usados dados de demonstração, listas incorporadas no frontend nem fotografias antigas como
substituição. Se nenhuma API responder, a página apresenta “diretório temporariamente indisponível”.

O sitemap tenta percorrer todas as páginas do contrato V5. Se não conseguir provar que recebeu o
total completo, só usa o contrato anterior quando a respetiva contagem também confirma completude;
caso contrário conserva apenas as rotas estáticas.

## Medida e orçamento público

- página pública por omissão: 24 perfis;
- máximo por pedido V5: 100 perfis;
- máximo temporário do contrato anterior: 500 perfis;
- máximo de cursor: 512 caracteres;
- máximo de pesquisa: 120 caracteres;
- máximo do identificador de grupo usado no filtro: 50 caracteres.

Estas medidas evitam enviar todos os cartões para o navegador e deixam a API preparada para crescer.
Uma futura alteração dos limites exige nova revisão e testes; não pode transformar um total parcial
em exato.

## Garantias mantidas

- ingestão, revisão e publicação continuam separadas;
- apenas a projeção aprovada é pesquisável;
- nomes e siglas não são usados para associar identidades;
- posições coletivas não entram num histórico individual;
- ausência de informação permanece “dados indisponíveis”;
- a IA não participa na pesquisa, ordenação ou ligação dos perfis;
- correções, retiradas e direitos de resposta continuam append-only.
