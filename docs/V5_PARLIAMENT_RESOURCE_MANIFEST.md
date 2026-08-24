# V5.23 — manifesto privado de recursos parlamentares

## Objetivo

A V5.23 cria o segundo gate do preenchimento histórico parlamentar: parte de uma única pasta já
inventariada pela V5.22, volta a provar a fotografia de catálogo que a contém e arquiva o HTML dessa
pasta antes de inventariar ligações XML ou JSON. O resultado continua privado e não é um conjunto
de dados parlamentar ingerido.

Esta entrega acrescenta código e testes. Não executa o comando em staging ou produção, não toca no
Supabase e não altera a matriz pública.

## Cadeia de prova obrigatória

O manifesto só pode ser persistido quando existe uma linha exata em
`official_index_resources`, ligada a uma fotografia de catálogo que cumpra simultaneamente:

1. identificador `official_index_<32 hex>` fornecido explicitamente;
2. `publisher=PARLIAMENT` e `publishable=false`;
3. tipo de catálogo, legislatura, etiqueta e URL do candidato exatamente iguais;
4. categoria privada `PENDING_INSPECTION` e `NOT_ASSERTED` criada pela V5.22;
5. `SourceDocument` do catálogo com atestação que repete o mesmo URL e SHA-256.

A consulta não usa título aproximado, fragmento de URL, nome de ficheiro semelhante ou a
fotografia “mais recente”. Um candidato noutra fotografia, noutro catálogo ou noutra legislatura é
recusado.

## Descoberta de ficheiros

Depois da prova do catálogo, é obtido o HTML da pasta candidata. O URL efetivo tem de permanecer
exatamente igual ao URL arquivado; um redirecionamento inesperado termina o lote. Os bytes, data
UTC, tipo MIME e SHA-256 são preservados antes do manifesto.

Uma ligação só entra no manifesto quando:

- usa HTTPS e um anfitrião parlamentar autorizado;
- o caminho, um parâmetro oficial de nome de ficheiro (`fich`, `file` ou `filename`) ou, apenas em
  último recurso, a etiqueta integral termina inequivocamente em `.xml`, `.json`, `.json.txt` ou
  `_json.txt`;
- o formato não é contraditório entre os campos do próprio URL;
- o URL exato ainda não apareceu na mesma fotografia.

PDF, navegação, fontes externas, nomes ambíguos e formatos desconhecidos são ignorados. Uma pasta
sem qualquer XML/JSON inequívoco falha fechada.

## Estado persistido

Cada ficheiro fica apenas como candidato:

- `PENDING_DOWNLOAD`;
- `historical_completeness=NOT_ASSERTED`;
- `publishable=false`;
- referência privada ao `snapshot_id` do catálogo pai.

O manifesto usa novamente o arquivo content-addressed, `SourceDocument`, atestação, fotografia
append-only, `SyncRun` e `AuditEvent` existentes. Não exige migração e não cria um atalho para o
circuito editorial.

## Porta operacional

O comando exige numa única execução:

- um tipo de catálogo;
- uma legislatura suportada exata;
- o `snapshot_id` do catálogo V5.22;
- o URL candidato exato;
- `ENVIRONMENT=staging`, `DATABASE_URL` e `--confirm-private-staging`.

A prova do catálogo é feita antes da chamada à fonte e repetida imediatamente antes da
persistência. O serviço recusa produção. Não existe workflow automático, calendário, continuação
para outra legislatura ou seleção implícita do catálogo mais recente.

## O que esta entrega não faz

- não descarrega os bytes dos ficheiros XML/JSON inventariados;
- não interpreta o esquema ou conta registos;
- não cria fotografias de reuniões, iniciativas, votações, posições ou deputados;
- não compara `source_id` nem associa pessoas ou partidos;
- não cria casos editoriais, revisões ou decisões;
- não aprova, publica ou retira dados;
- não afirma que a pasta ou o ficheiro cobre toda uma legislatura;
- não usa IA.

O gate seguinte deverá escolher um único ficheiro do manifesto, voltar a verificar o pai e arquivar
os seus bytes com limites de tamanho, sem normalizar automaticamente outros recursos.

## Critérios de aceitação

- nenhum manifesto existe sem catálogo pai exato e atestado;
- URL, legislatura, etiqueta, categoria e tipo de catálogo são comparados exatamente;
- a pasta fica arquivada com URL, data e SHA-256 próprios;
- apenas XML/JSON inequívocos e parlamentares entram no manifesto;
- o vínculo ao catálogo pai é preservado na categoria privada;
- a persistência continua append-only e `publishable=false`;
- zero ficheiros são descarregados e zero casos editoriais são criados;
- testes unitários e PostgreSQL descartável exercitam a cadeia completa.
