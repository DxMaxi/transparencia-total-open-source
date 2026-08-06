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

## Trabalho técnico

### 1. Modelos de recolha

Criar contratos Pydantic explícitos para:

- sessão parlamentar;
- iniciativa;
- votação;
- ator de voto;
- ligação entre iniciativa, sessão e votação.

### 2. Coletores

- descobrir os recursos oficiais por legislatura;
- recolher bytes exatos;
- normalizar datas e identificadores;
- deduplicar por identificador oficial;
- manter avisos de cobertura e estrutura.

### 3. Persistência privada

- `SourceDocument` para cada snapshot;
- `SyncRun` por recolha;
- upsert idempotente de sessões, iniciativas e votações;
- histórico de alterações sem apagar versões anteriores;
- registos de voto sem associação automática ambígua.

### 4. Revisão e publicação

- pré-visualização com contagens e diferenças;
- confirmação humana por SHA-256 e contagem;
- publicação separada por conjunto;
- retirada sem apagamento do histórico;
- estado público de cobertura e frescura.

### 5. API para o cidadão

- lista de iniciativas;
- detalhe da iniciativa;
- votações associadas;
- posição nominal ou partidária claramente identificada;
- fonte, data e limitações junto do dado.

## Critérios de conclusão

A Fase 2 só fica concluída quando:

- os coletores passam testes com fixtures oficiais;
- duas execuções iguais não criam duplicados;
- uma alteração oficial cria nova evidência auditável;
- votos partidários e nominais permanecem distintos;
- falhas parciais não publicam dados incompletos;
- a API pública mostra a cobertura real e as limitações;
- o frontend não apresenta inferências como factos.
