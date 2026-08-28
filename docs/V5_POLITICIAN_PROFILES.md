# V5.6 — perfis políticos completos e auditáveis

## Objetivo

A V5.6 substitui a antiga ficha agregada por um contrato público que separa explicitamente:

- identidade observada;
- fotografias de pertença parlamentar;
- períodos de mandato com datas oficiais;
- presenças individuais;
- iniciativas com autoria individual;
- votos nominais;
- metadados de declarações juridicamente autorizados.

Cada área declara `AVAILABLE`, `PARTIAL` ou `UNAVAILABLE`, a contagem publicável, o período
observado, uma explicação e a respetiva fonte quando existe. Uma lacuna nunca é convertida em
ausência, incumprimento, intenção política ou ocultação.

Esta entrega é preparada e verificada localmente. **Não publica nem retira dados reais**, não aplica
migrações remotas, não configura o Supabase, não cria utilizadores, não altera segredos e não faz
deploy.

## Contrato público V5.6

`GET /api/v1/public/politicians/{slug}` mantém os campos antigos necessários à transição e
acrescenta:

- `contract_version=v5.6`;
- `membership_observations`;
- `mandates`;
- `attendance` com contagens e intervalo observado;
- `initiatives`;
- `declarations`, com a linha temporal completa dos metadados aprovados;
- `declaration`, apenas quando existe prova individual publicável;
- `declaration_lookup_source`, que é apenas uma porta de pesquisa institucional;
- `coverage`, com uma decisão de disponibilidade independente para cada área.

O diretório acrescenta `observed_at`. `observed_at` é a data em que a pessoa foi vista numa
fotografia oficial; `verified_at` é a data da revisão humana. Nenhuma das duas é apresentada como
início de mandato.

## Portas de publicação independentes

| Área | Condição mínima para leitura pública |
|---|---|
| Identidade | última revisão `PERSON` positiva, ligada à mesma fonte parlamentar arquivada |
| Observações parlamentares | fotografia integral em que todas as pessoas têm revisão positiva ligada à mesma fonte |
| Mandatos | última revisão `MANDATE` positiva, fonte oficial não noticiosa e atestação do arquivo |
| Presenças | fotografia `PARLIAMENT_ACTIVITY_SNAPSHOT` publicada e mandato da pessoa revisto e arquivado |
| Iniciativas | relação individual por identificador oficial; sem essa relação, `UNAVAILABLE` |
| Votos nominais | fotografia `PARLIAMENT_VOTES_SNAPSHOT` publicada, parser exato V5.45, `actor_type=PERSON` e `actor_source_id = people.source_id` |
| Declarações | última revisão `ASSET_DECLARATION` positiva, fonte da Entidade para a Transparência, arquivo e confirmação jurídica explícita |

A ingestão não satisfaz nenhuma destas condições. Uma retirada posterior torna a respetiva área
indisponível sem apagar a fonte, a revisão anterior ou o evento de auditoria.

## Mandatos e fotografias de pertença

`ParliamentaryMembershipSnapshot.observed_at` conserva uma observação factual e pode formar uma
linha temporal de fotografias oficiais. Não permite calcular o começo, o fim ou a continuidade de
um mandato.

Um período só entra em `mandates` quando o modelo `Mandate` contém datas fornecidas por fonte
oficial e esse registo recebeu revisão própria. Assim, uma pessoa pode ter observações parlamentares
publicadas e, ao mesmo tempo, `mandates=UNAVAILABLE`; essa combinação é deliberada e honesta.

## Associação individual sem aproximações

Os votos do perfil ficam limitados às fotografias `parliament-activity-v6` e
`parliament-historical-votes-v2`, documentadas na
[V5.45](V5_POLITICIAN_NOMINAL_VOTE_IDENTITY.md). A consulta
exige simultaneamente:

1. votação nominal;
2. posição com `actor_type=PERSON`;
3. `actor_source_id` individual preservado na posição;
4. `person_id` associado apenas quando `actor_source_id = people.source_id`;
5. mesma fotografia e mesmo documento-fonte entre posição e votação;
6. última revisão positiva do âmbito de votos e original atestado.

Nomes parlamentares, nomes civis e siglas servem apenas para apresentação. Não são chaves de
associação. A interface deixou também de sugerir uma secção de “posições do grupo” dentro da ficha
individual: uma posição coletiva pertence à consulta parlamentar, não ao histórico pessoal.

A V5.42 acrescenta uma fotografia **privada** de autoria individual por `IniId + idCadastro`
oficiais e uma proposta editorial `PENDING`, documentadas em
[V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md](V5_POLITICIAN_INITIATIVE_AUTHORSHIP.md). A
[V5.43](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION.md) acrescenta a publicação específica,
transacional e append-only: a ficha só mostra relações `AUTHOR` quando identidade, iniciativa,
fontes e revisões continuam válidas. Sem relações publicadas, a cobertura permanece
`UNAVAILABLE`; nunca tenta descobrir autores no título, na descrição, no nome ou na sigla
partidária. A [V5.44](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL.md) acrescenta uma revisão
negativa, auditoria, decisão e evento de retirada, sem apagar a relação ou alterar pessoa,
iniciativa, partido, fontes ou publicação original.

## Declarações: prova individual versus portal de pesquisa

Uma ligação geral à Entidade para a Transparência não prova que uma pessoa tem ou não tem uma
declaração, nem prova o seu conteúdo ou estado. Por essa razão:

- `declaration` só recebe metadados de um registo individual, arquivado e aprovado;
- a fonte tem de ser a Entidade para a Transparência e não pode ser uma notícia;
- publicar exige confirmação adicional de que a base legal e o âmbito foram revistos;
- `declaration_lookup_source` não inclui data de recolha nem SHA-256 e é rotulado como pesquisa
  institucional, nunca como prova desta pessoa;
- conteúdos integrais, áreas autenticadas e identificadores pessoais continuam fora do perfil.

O controlo técnico não substitui uma AIPD, o encarregado de proteção de dados ou aconselhamento
jurídico português independente.

## Revisão local e futura operação autorizada

O comando genérico passa a reconhecer `MANDATE` e `ASSET_DECLARATION`. Uma futura decisão sobre um
mandato exige a confirmação normal da fonte:

```bash
python -m scripts.review_publication MANDATE mandate_id \
  --publish --reviewer revisor-01 \
  --rationale "Cargo e datas confirmados no original oficial arquivado." \
  --confirm-source-reviewed
```

Uma declaração exige ainda a confirmação jurídica separada:

```bash
python -m scripts.review_publication ASSET_DECLARATION declaration_id \
  --publish --reviewer revisor-legal-01 \
  --rationale "Fonte, necessidade, proporcionalidade e base legal confirmadas." \
  --confirm-source-reviewed --confirm-legal-basis-reviewed
```

Estes exemplos documentam o contrato; não autorizam a execução sobre qualquer ambiente ou registo
real. Tanto a publicação como a retirada acrescentam `DataPublicationReview` e `AuditEvent`.

## Compatibilidade e interface

Enquanto o frontend V5.6 comunicar com uma API anterior, adapta a resposta sem inventar dados:

- a ficha continua acessível;
- mostra um aviso de transição;
- mantém a identidade e os votos já publicáveis;
- marca como parciais as métricas cujo período ou porta específica não são expostos;
- trata a antiga fonte geral de declarações apenas como ligação de pesquisa;
- não usa listas de demonstração nem dados antigos alternativos.

A página pública apresenta primeiro a matriz de cobertura e só depois os detalhes. As listas
históricas ficam agrupadas, as contagens distinguem a fotografia total dos 50 votos recentes
mostrados e a terminologia passa a “grupo indicado na fonte”, evitando atribuir uma identidade
partidária oficial que o dataset não prova de ponta a ponta.

## Alterações de esquema e dados

A V5.6 reutiliza os modelos append-only e as revisões existentes. Não cria migração nem altera o
esquema. Também não recolhe, corrige, revê, publica ou retira dados reais nesta entrega.

## Garantias mantidas

- fonte, data de recolha e SHA-256 acompanham cada facto publicado;
- revisão, publicação e retirada permanecem separadas da ingestão;
- a última decisão negativa revoga uma decisão positiva anterior sem a apagar;
- ausência de dados permanece `UNAVAILABLE` ou `PARTIAL`;
- não existe correspondência aproximada;
- atividade coletiva nunca é atribuída a uma pessoa;
- IA não é usada para preencher mandatos, autoria, presenças, votos ou declarações;
- histórico e direito de resposta permanecem imutáveis.
