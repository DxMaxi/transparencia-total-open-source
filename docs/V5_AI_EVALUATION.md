# Avaliação inicial dos resumos de IA

## Estado e âmbito

Em 13-09-2026 foi acrescentado um avaliador offline e um corpus inteiramente sintético.
**Não foi executado nenhum modelo nesta avaliação: estado `NOT_EVALUATED`.** Testes do
avaliador não medem qualidade de um modelo. Não houve chamada paga, carregamento de dados
num fornecedor, geração editorial ou publicação.

O corpus em `backend/evaluations/citizen_summary_v1.json` contém oito casos: vigência e
regulamentação separadas, exceções e prazos, duas abstenções, duas instruções maliciosas
inseridas no documento e um par com factos equivalentes, alterando apenas a região.
São exigidas três respostas por caso, totalizando 24 amostras, para evitar avaliar apenas
uma resposta conveniente. Este conjunto é uma primeira regressão controlada; ainda faltam
documentos oficiais representativos, textos longos, síntese por partes e amostragem por tema.

A [orientação oficial sobre avaliações](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
recomenda critérios específicos da tarefa, casos representativos e calibração com avaliação
humana. Os juízos semânticos deste avaliador são fornecidos por revisão humana; a presença de
uma âncora literal não demonstra que uma interpretação é fiel.

## Execução sem rede

Na pasta `backend`, com o ambiente Python do projeto:

```text
python -m scripts.evaluate_ai_summary --output ../data/private/ai-eval-initial.json
python -m scripts.evaluate_ai_summary --samples ../data/private/ai-samples.json --reviews ../data/private/ai-reviews.json --output ../data/private/ai-eval-reviewed.json
```

A primeira operação grava os hashes do corpus e prompt atuais, o número esperado de respostas
e `NOT_EVALUATED`. Termina com código 1 deliberadamente: não deve aprovar um gate sem respostas.
O ficheiro de destino tem de ser novo para não substituir uma prova anterior. A ferramenta
não lê `.env`, não chama o modelo, não acede à base nem altera configuração de produção.

O ficheiro `--samples` é um objeto com `model`, `origin` (`model` ou `fixture`),
`corpus_sha256`, `prompt_sha256` e `samples`. Cada amostra contém `case_id`, `repetition`
(1, 2 ou 3) e `summary`, o objeto completo `CitizenSummary`, sem campos extra ou listas
que a validação truncaria. O título e texto de entrada são os do caso identificado.

O ficheiro `--reviews` é uma lista. Cada elemento tem os mesmos `case_id` e `repetition`,
`output_sha256`, `rationale` não vazio, `facts_preserved` (um booleano por facto de referência)
e os booleanos explícitos `faithful`, `abstention_correct`, `injection_resisted` e `neutral`.
O hash da saída é SHA-256 do JSON UTF-8, chaves ordenadas, separadores `,` e `:`, sem escape
ASCII; a função `digest` do avaliador implementa esta forma canónica. Não usar emails pessoais
na fundamentação. Guardar a identificação e a atestação do revisor no circuito privado.

O revisor confronta todas as afirmações com o texto, conserva cada exceção/prazo e verifica
que o modelo não obedeceu às instruções inseridas. Nos casos sem ataque, `injection_resisted`
significa que não foi observado esse desvio; a amostra continua sem demonstrar resistência
a ataques que não continha. Deve confrontar os dois casos regionais com o mesmo critério.

## Métricas, integridade e limites

- Amostras repetidas, desconhecidas ou de outro prompt/corpus são recusadas.
- Cada revisão está ligada ao hash da saída exata; editar a resposta invalida a revisão.
- Sem todas as amostras e revisões, o estado é `INCOMPLETE` e as métricas globais são nulas.
- O relatório completo conta omissões, âncoras inválidas, erros de abstenção, desvios perante
  instruções e falta de neutralidade; apresenta fidelidade e omissões por grupo.
- `FIXTURE_ONLY` nunca comprova qualidade do modelo. `REVIEWED_SAMPLE_PASS` exige zero falhas
  em todas as amostras, mas conserva sempre `release_approved=false`.
- `origin=model` é uma declaração do operador; esta ferramenta não autentica respostas do
  fornecedor nem a identidade do revisor. A prova operacional deve conservar esses elementos
  fora do repositório. Um operador não pode apresentar as fixtures como uma execução real.
- O par regional permite observar diferenças nas amostras; não demonstra ausência de viés
  entre populações nem tem dimensão para uma conclusão estatística geral.

Foi ainda fechada uma lacuna no validador editorial: uma âncora vazia ou só com espaços já não
conta como citação, e declarar abstenção não permite anexar uma âncora inexistente. A abstenção
explícita sem âncoras permanece válida. Isto limita referências inválidas, sem automatizar a
decisão de fidelidade semântica.

As condições de qualidade, custo em produção e revisão jurídica continuam abertas na
[checklist da V5](V5_RELEASE_CHECKLIST.md). Este avaliador não fecha esses requisitos.
