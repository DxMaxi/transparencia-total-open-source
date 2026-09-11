# Protocolo de neutralidade

Neutralidade não é ausência de método. É a aplicação pública, simétrica e reproduzível das mesmas
regras a todos os partidos, pessoas, governos e períodos.

## Hierarquia de evidência

1. Documento oficial original com identificador estável.
2. Dataset aberto publicado pelo órgão competente.
3. Diário, transcrição, vídeo ou relatório oficial.
4. Comunicação oficial usada apenas para contexto ou para confirmar abandono declarado.

Notícias, redes sociais, verificações de terceiros e declarações partidárias podem apontar uma
pista de pesquisa, mas não fundamentam sozinhas um facto publicado.

## Estados do Promessómetro

Antes de revisão, a base de dados usa `UNVERIFIED`; esse estado impede classificação prematura.

| Estado técnico | Estado público | Critério mínimo |
|---|---|---|
| `UNVERIFIED` | Por verificar | Ainda não existe decisão editorial sobre a execução |
| `NOT_STARTED` | Não iniciada | Revisão humana fundamentada no período e nas fontes declaradas; ausência de dados não basta |
| `IN_PROGRESS` | Em curso | Existem atos oficiais verificáveis em curso, sem prova de conclusão |
| `PARTIAL` | Parcialmente cumprida | As provas revistas satisfazem parte dos critérios públicos |
| `FULFILLED` | Cumprida | As provas revistas satisfazem integralmente os critérios públicos |

Aplica-se o [vocabulário V5.20](V5_PROMESSOMETRO_VOCABULARY.md). Os valores legados
`BROKEN` e `ABANDONED` permanecem apenas no histórico físico e são recusados nas projeções
públicas; não existe reclassificação automática.

Uma percentagem de execução só pode resultar de subcritérios publicados, ponderação explícita e
evidência para cada parcela. Não deve ser estimada por um modelo de IA.

Regras adicionais:

- uma lei publicada não prova execução material quando a promessa exige resultados;
- financiamento anunciado não prova despesa executada;
- um projeto-piloto não prova cobertura nacional;
- mudança de redação deve ser comparada pelo resultado verificável, não por palavras isoladas;
- a passagem do tempo não determina o estado; sem prova suficiente, mantém-se a incerteza e
  não se infere execução, conclusão ou incumprimento.

## Assiduidade

Publicar numerador, denominador, sessões incluídas, período, faltas justificadas e alterações de
mandato. Não misturar plenário, comissão e votação sem etiquetas. Se a fonte não publicar chamada
nominal suficiente, mostrar “dados indisponíveis” e não zero.

## Declarações de património e interesses

Mostrar apenas informação legalmente pública e necessária. Preferir ligação ao registo oficial e
metadados de existência/período. Não republicar moradas, identificadores fiscais, assinaturas ou
outros dados excessivos. Pedidos de correção devem encaminhar também o utilizador para a entidade
de origem quando o erro está no documento oficial.

## Comparação discurso/voto

Uma comparação só é elegível quando:

- a declaração tem gravação ou transcrição oficial e âncora temporal;
- o voto é nominal e pertence à mesma pessoa;
- ambos tratam o mesmo objeto normativo e dimensão material;
- a janela temporal e eventuais mudanças de texto estão explícitas.

Resultados possíveis: `CONSISTENTE`, `INCONSISTENTE`, `INCONCLUSIVO` e `NÃO COMPARÁVEL`. A IA pode
sugerir pares; dois revisores devem confirmar qualquer conclusão de consistência.

## Correções e conflitos

Uma correção inclui valor anterior, novo valor, fonte, motivo, autor/revisor e data. Conflitos entre
fontes oficiais são publicados como conflito, com ambas as ligações, até resolução. Nunca escolher
silenciosamente a versão mais favorável ou desfavorável a um ator.
