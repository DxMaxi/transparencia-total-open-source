# V5.21 — matriz de cobertura parlamentar e plano de preenchimento histórico

## Objetivo

A V5.21 torna visível o que a plataforma publicou realmente, em vez de apresentar uma soma de
registos como se representasse toda a história parlamentar portuguesa. A alteração não recolhe,
aprova, publica, retira ou reclassifica dados. Acrescenta uma consulta pública derivada das últimas
fotografias parlamentares que já passaram pela porta editorial existente.

Existem três estados que não podem ser confundidos:

1. **Publicado no portal:** fotografia arquivada, atestada, revista e atualmente publicável.
2. **Candidato existente numa fonte oficial:** recurso que ainda tem de ser recolhido, arquivado,
   normalizado e revisto; não conta como cobertura do portal.
3. **Dados indisponíveis:** não existe prova publicável para o âmbito pedido. Isto não significa
   ausência de atividade nem incumprimento.

## Contrato da matriz pública

`GET /api/v1/public/parliament/coverage` devolve duas linhas por âmbito publicado:

- `activity`: reuniões observadas e iniciativas;
- `votes`: votações e posições registadas.

Cada linha conserva:

- legislatura, âmbito e tipo de registo;
- contagem exata **dentro da fotografia indicada**;
- primeiro e último dia observados quando a fotografia os contém;
- data da recolha e data da revisão humana;
- URL oficial, data de obtenção e SHA-256 dos bytes da fonte;
- SHA-256 da fotografia normalizada;
- limitação específica e `historical_completeness=NOT_ASSERTED`.

A consulta escolhe a revisão mais recente de cada fotografia. Uma retirada posterior impede que
uma aprovação antiga volte a aparecer. A fotografia só é elegível se a fonte for da Assembleia da
República e existir uma atestação com o mesmo documento, URL e SHA-256. O período é calculado por
`snapshot_id` e `source_document_id` exatos; não existe correspondência aproximada. As quatro
contagens são recalculadas e comparadas com o manifesto antes da resposta. Qualquer divergência
torna esse âmbito indisponível, em vez de publicar uma contagem potencialmente corrompida.

Se o endpoint faltar, falhar ou devolver um contrato inválido, o frontend recusa a matriz inteira.
Mostra “temporariamente indisponível”, nunca uma contagem zero, dados antigos ou dados de exemplo.

## Limites que acompanham as contagens

- As “reuniões” são observações presentes nos eventos de votação da fotografia; não equivalem à
  agenda integral da Assembleia da República.
- Uma iniciativa ou votação não prova, por si só, entrada em vigor, execução orçamental ou impacto
  material.
- As posições incluem `UNKNOWN` quando a fonte não permite normalização mais precisa.
- Uma posição coletiva não é convertida em voto individual.
- Uma pessoa ou grupo só é associado através de identificador oficial inequívoco.
- A ausência de uma legislatura na matriz significa apenas que não existe fotografia publicável
  para esse âmbito.

## Inventário inicial de fontes-candidatas

O [catálogo geral de dados abertos](https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx),
o [catálogo de iniciativas](https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx) e o
[catálogo de atividades](https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx) foram
confirmados como pontos de partida oficiais em 24 de agosto de 2026. O catálogo geral declara que
os recursos são organizados por tema e legislatura.

Esta observação serve apenas para ordenar uma futura recolha. O HTML vivo dos catálogos não é
tratado aqui como fotografia ingerida nem como prova de completude. A existência, URL efetivo,
formato, período e SHA-256 de cada recurso têm de ser confirmados novamente e arquivados no momento
da ingestão. Uma pasta ou ligação no catálogo não autoriza publicação.

| Fila | Legislaturas | Fontes-candidatas | Estado neste plano |
|---|---|---|---|
| 0 | legislatura em curso | recurso oficial já configurado para iniciativas/votações | manter atualizado; cada nova fotografia volta a revisão |
| 1 | anteriores, da mais recente para a mais antiga | catálogos de iniciativas e atividades | inventariar recurso a recurso; cobertura ainda não afirmada |
| 2 | períodos não servidos por esses catálogos | outro arquivo oficial a identificar | dados indisponíveis até existir fonte e metodologia próprias |

A fila não afirma que todas as legislaturas têm a mesma estrutura nem que um único recurso contém
toda a atividade. Quando a fonte muda de esquema, o parser e os testes são versionados antes da
recolha seguinte. Não se preenchem lacunas com notícias, cópias de terceiros ou inferência de IA.

## Execução de cada lote histórico

Cada legislatura e tipo de fonte percorre isoladamente estes gates:

1. descobrir o recurso através do catálogo oficial e validar anfitrião e redirecionamentos;
2. recolher os bytes com limite de tamanho, guardar URL efetivo, instante UTC e SHA-256;
3. escrever o objeto content-addressed e confirmar a atestação de arquivo;
4. normalizar numa nova fotografia append-only, conservando parser, manifesto, avisos e quatro
   contagens;
5. comparar com a fotografia anterior apenas por `source_id` oficial exato;
6. criar propostas privadas `PENDING` separadas para `activity` e `votes`;
7. rever contagens, amostras, períodos, detalhe nominal e valores `UNKNOWN`;
8. aprovar ou rejeitar sem alterar a projeção pública;
9. exigir uma confirmação `ADMIN` distinta para publicar cada âmbito;
10. verificar a nova linha da matriz, a fonte, os hashes e o histórico de decisão.

Uma falha termina o lote em estado privado e auditável. Não existe continuação automática para a
legislatura seguinte nem publicação automática depois de uma migração ou deployment.

## Critérios de aceitação da V5.21

- a API e a interface só mostram fotografias atualmente publicáveis e atestadas;
- todas as contagens são rotuladas como exatas apenas dentro da fotografia;
- período observado, recolha, revisão, fonte e hashes ficam visíveis;
- indisponibilidade nunca aparece como zero ou ausência factual;
- a interface explica como o histórico será preenchido sem prometer completude inexistente;
- testes de backend e de contrato impedem remoção destas portas;
- nenhum dado real, migração remota, utilizador ou segredo é alterado por esta entrega.
