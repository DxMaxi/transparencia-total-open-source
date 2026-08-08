# Fase 2 — Pipeline parlamentar da V4

## Objetivo público

Transformar os dados oficiais da Assembleia da República em informação útil para o cidadão,
sem inventar factos, sem atribuir votos coletivos a pessoas e sem publicar registos ainda não
revistos.

## Âmbito

A Fase 2 fecha quatro circuitos:

1. deputados e fotografias de pertença parlamentar;
2. sessões e reuniões;
3. iniciativas legislativas;
4. votações e respetivos atores.

## Regras obrigatórias

- Cada registo conserva URL oficial, data de recolha e SHA-256.
- Uma posição de grupo parlamentar nunca é convertida em voto nominal.
- Votos nominais só ligam a uma pessoa quando a fonte fornece identificação inequívoca.
- A ingestão é append-only e nunca equivale a publicação.
- Mudanças de estrutura ou quedas anormais de contagem bloqueiam a promoção.
- Campos ausentes são apresentados como indisponíveis, não preenchidos por inferência.

## Implementação entregue

### 1. Modelos e manifesto

Os contratos Pydantic explícitos cobrem:

- sessão parlamentar;
- iniciativa;
- votação;
- ator de voto;
- ligação segura entre iniciativa, reunião observada e votação;
- `ParliamentActivityDataset`, vinculado a uma legislatura, documento e versão de parser;
- `ParliamentActivitySnapshot`, com SHA-256 normalizado e quatro contagens de controlo.

### 2. Recolha e normalização

- o coletor descobre o JSON oficial por legislatura ou usa `PARLAMENTO_VOTES_URL` explícito;
- cada resposta é descarregada uma vez e os bytes exatos são preservados antes da normalização;
- iniciativas herdam apenas as suas próprias chaves oficiais;
- votações repetidas em várias iniciativas não são ligadas arbitrariamente a uma delas;
- “reunião” é uma observação derivada do número, tipo e data publicados no evento de votação; não
  representa a agenda parlamentar completa;
- posições textuais sem identificador individual permanecem `UNKNOWN`.

### 3. Persistência privada append-only

- `raw_source_objects` conserva os bytes por SHA-256;
- `SourceDocument` e `SourceArchiveAttestation` ancoram URL e hash;
- `SyncRun` regista resultado, contagens, avisos e versão do código;
- sessões, iniciativas, votações e posições usam `INSERT … ON CONFLICT DO NOTHING` dentro de uma
  fotografia identificada por documento, legislatura e parser;
- triggers PostgreSQL recusam `UPDATE` e `DELETE` nas tabelas parlamentares factuais;
- repetir a mesma recolha é idempotente; uma correção exige nova versão do parser.

### 4. Revisão e publicação

- `review_parliament_activity` pré-visualiza URL, dois hashes, arquivo e quatro contagens;
- publicar ou retirar exige repetir todos esses valores, pseudónimo e fundamentação;
- `activity` e `votes` têm decisões separadas e append-only;
- uma decisão negativa mais recente revoga a positiva para a mesma fotografia;
- a leitura pública escolhe uma única fotografia aprovada por âmbito e legislatura.

### 5. API e PWA

- `/api/v1/public/parliament/sessions`, `/initiatives` e `/votes` são paginados e fail-closed;
- `/atividade-parlamentar` mostra reuniões observadas, iniciativas, votações, fonte e SHA-256;
- falhas parciais da API são distinguidas de conjuntos aprovados vazios;
- a produção não apresenta dados demonstrativos quando a API está ausente.

## Critérios de conclusão

A implementação é considerada tecnicamente concluída quando:

- [x] os coletores passam testes com formas documentadas pela fonte oficial;
- [x] duas execuções iguais não criam duplicados;
- [x] uma alteração de parser cria nova evidência auditável;
- [x] posições coletivas, desconhecidas e nominais permanecem distintas;
- [x] falhas parciais não são apresentadas como conjuntos vazios confirmados;
- [x] a API pública mostra proveniência e apenas uma fotografia aprovada;
- [x] o frontend não apresenta inferências como factos;
- [ ] a migração, a recolha real, a revisão editorial e os smoke tests foram executados no ambiente
  de produção autorizado.

O último item é um gate operacional e não é cumprido por merge ou deploy automático. Consulte
`V4_PRODUCTION_OPERATIONS.md` e `V4_TO_V5_RELEASE_GATE.md`.
