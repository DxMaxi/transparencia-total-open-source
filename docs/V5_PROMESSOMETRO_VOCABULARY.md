# V5.20 — vocabulário editorial seguro do Promessómetro

## Problema corrigido

O plano público da V5 define cinco estados: `UNVERIFIED`, `NOT_STARTED`, `IN_PROGRESS`,
`PARTIAL` e `FULFILLED`. O contrato antigo ainda apresentava `BROKEN` e `ABANDONED`, palavras que
podiam transformar uma classificação editorial numa conclusão acusatória e não correspondiam ao
vocabulário aprovado.

A V5.20 alinha a API, a pesquisa global e a interface pública com os cinco estados aprovados. Não
altera qualquer compromisso, não promove dados e não executa migrações remotas.

## Significado dos estados

| Estado técnico | Texto público | Regra mínima |
|---|---|---|
| `UNVERIFIED` | Por verificar | O compromisso foi localizado no programa, mas a execução ainda não tem decisão editorial. |
| `NOT_STARTED` | Não iniciada | Uma revisão humana fundamentada concluiu este estado dentro do período e das fontes declaradas. Nunca nasce apenas da ausência de dados. |
| `IN_PROGRESS` | Em curso | Existem atos oficiais verificáveis em curso, sem prova de conclusão do compromisso. |
| `PARTIAL` | Parcialmente cumprida | As provas revistas satisfazem apenas parte dos critérios públicos do compromisso. |
| `FULFILLED` | Cumprida | As provas revistas satisfazem integralmente os critérios públicos do compromisso. |

Uma lei, anúncio, verba orçamentada ou entrada em vigor não prova automaticamente execução
material. São tipos de prova diferentes e devem permanecer separados. A percentagem de progresso é
um campo editorial de compatibilidade; nunca calcula nem escolhe o estado.

## Compatibilidade e histórico

A migração acrescenta `NOT_STARTED` e `PARTIAL` ao enum PostgreSQL. Mantém os valores legados
`BROKEN` e `ABANDONED` no tipo físico para não reescrever decisões antigas, mas todas as projeções
públicas os recusam. Se existir um registo legado, permanece fora do site até uma nova revisão
humana append-only decidir um estado válido.

Isto preserva simultaneamente:

- histórico imutável;
- ausência de reclassificação automática;
- publicação fail-closed;
- compatibilidade com uma base ainda sem a migração V5.20;
- separação entre aplicar esquema, rever e publicar.

## Portas de publicação

Um compromisso público continua a exigir:

1. programa oficial arquivado e atestado por URL, recolha e SHA-256;
2. decisão humana `ACCEPT` mais recente;
3. prova oficial adicional arquivada para qualquer estado diferente de `UNVERIFIED`;
4. estado pertencente ao vocabulário V5.20;
5. fundamentação e data de revisão visíveis.

O frontend volta a validar o vocabulário recebido. Um valor desconhecido ou legado faz recusar a
projeção inteira e mostrar apenas a base editorial identificada, em vez de receber um rótulo
inventado ou produzir uma contagem parcial silenciosa.

## Trabalho que permanece aberto

Esta correção fecha o vocabulário, não o catálogo integral. Permanecem na V5:

- catalogar todos os compromissos individualizáveis do Programa do XXV Governo;
- publicar critérios editoriais por compromisso;
- separar provas legislativas, orçamentais, regulamentares e de execução;
- criar uma linha temporal append-only para cada mudança;
- concluir filtros por ministério, área, estado e data;
- ensaiar o circuito completo em staging isolado antes de qualquer operação de produção.
