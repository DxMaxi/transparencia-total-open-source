# V5.22 — catálogo privado de fontes parlamentares históricas

## Objetivo

A V5.22 transforma o inventário documental da V5.21 num coletor versionado e testável, sem
confundir uma ligação no portal da Assembleia da República com dados recolhidos ou publicados.
Esta entrega não executa o coletor, não altera uma base remota e não cria cobertura pública.

O catálogo oficial da Assembleia declara que os dados abertos são organizados por área temática e
legislatura. As páginas específicas de iniciativas, atividades e atividade dos deputados expõem
pastas por legislatura. Essas páginas são pontos de descoberta; não provam que uma pasta esteja
completa, que todos os ficheiros tenham o mesmo esquema ou que o seu conteúdo possa ser publicado
sem arquivo e revisão.

## O que é arquivado

Cada execução trata apenas um destes catálogos oficiais:

| Tipo privado | Página oficial |
|---|---|
| `INITIATIVES` | `https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx` |
| `ACTIVITIES` | `https://www.parlamento.pt/Cidadania/Paginas/DAatividades.aspx` |
| `DEPUTY_ACTIVITY` | `https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx` |

O HTML exato é guardado como objeto content-addressed e ligado a um `SourceDocument`. A fotografia
do índice conserva URL efetivo, instante UTC de recolha, tipo MIME, SHA-256, versão do parser,
atestação de arquivo e `AuditEvent`. A tabela `official_index_snapshots` continua protegida por
`publishable=FALSE`.

## Regra de correspondência

O parser aceita apenas a etiqueta integral publicada pela fonte:

- `I Legislatura` a `XVII Legislatura`;
- `Constituinte`.

Espaços são normalizados apenas para interpretar o texto HTML. Não existe correspondência
aproximada, pesquisa por fragmento, inferência a partir do URL ou associação por nome. Expressões
como “Acolhimento aos Deputados - XVII Legislatura” ou “XVII Legislatura — arquivo” não são
candidatos. URLs fora dos anfitriões parlamentares exatos são rejeitados mesmo que tenham uma
etiqueta válida.

Cada ligação aceite fica marcada internamente como:

- `PENDING_INSPECTION`;
- `historical_completeness=NOT_ASSERTED`;
- `publishable=false`.

Uma alteração futura da nomenclatura, a criação de nova legislatura ou uma estrutura diferente
exigem nova versão do parser e testes próprios; não são adivinhadas.

## Porta operacional

O comando de persistência:

- aceita um único catálogo por execução;
- exige `ENVIRONMENT=staging`, `DATABASE_URL` e `--confirm-private-staging`;
- é recusado em desenvolvimento, teste operacional e produção;
- não está ligado a `push`, deployment, calendário ou ao sincronizador V4;
- não segue automaticamente para outro catálogo ou legislatura.

O ambiente `test` é aceite apenas pela classe de persistência para os testes de integração sobre
PostgreSQL descartável. A execução remota real continua bloqueada enquanto não existir um projeto
Supabase de staging inequivocamente isolado e autorizado.

## O que esta entrega não faz

- não descarrega os ficheiros XML ou JSON dentro das pastas candidatas;
- não afirma períodos, quantidade de registos ou completude histórica;
- não normaliza reuniões, iniciativas, votações, posições ou perfis;
- não cria casos editoriais `PENDING`;
- não aprova, publica, retira ou altera a projeção pública;
- não associa políticos, partidos ou votações;
- não usa IA.

Esse passo seguinte está implementado em
[V5.23 — manifesto privado de recursos parlamentares](V5_PARLIAMENT_RESOURCE_MANIFEST.md): seleciona
uma única pasta candidata, volta a provar o catálogo pai e arquiva a respetiva página antes de
inventariar XML/JSON. Cada legislatura e cada tipo de recurso mantém uma execução independente.

## Critérios de aceitação

- bytes, URL efetivo, data e SHA-256 do catálogo são preservados antes do inventário;
- apenas etiquetas exatas e URLs parlamentares autorizadas geram candidatos;
- duplicados usam o URL exato, nunca semelhança textual;
- uma página sem candidatos válidos falha fechada;
- a persistência produz arquivo, atestação, índice append-only e auditoria;
- nenhum caso editorial ou evento de publicação é criado;
- produção é recusada pela própria camada de serviço;
- testes unitários e PostgreSQL descartável comprovam estas portas.
