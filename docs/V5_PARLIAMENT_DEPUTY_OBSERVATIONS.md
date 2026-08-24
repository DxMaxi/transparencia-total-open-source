# V5.27 — observações privadas e auditáveis de deputados

## Objetivo

A V5.27 interpreta um único recurso JSON de **atividade dos deputados** que já tenha passado pelos
gates V5.22, V5.23 e V5.24. O resultado é uma fotografia privada, versionada e append-only das
fichas biográficas observadas na Assembleia da República. Esta fotografia não cria perfis públicos,
mandatos, relações partidárias, casos editoriais ou publicações.

A [página oficial de atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx)
disponibiliza este tema por legislatura dentro do
[catálogo de dados abertos](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx). A
existência de um ficheiro no catálogo não demonstra cobertura integral, atualidade de cada campo
ou exercício de um cargo durante todo o período. Por isso, a fotografia fica sempre com
`historical_completeness=NOT_ASSERTED` e `sync_status=PARTIAL`.

## Cadeia de prova

O normalizador aceita apenas:

1. catálogo `DEPUTY_ACTIVITY` arquivado e atestado;
2. pasta de legislatura exata e manifesto V5.23;
3. recurso inequívoco em formato `JSON` arquivado pela V5.24;
4. URL, tamanho e SHA-256 iguais em todas as etapas;
5. bytes UTF-8 com JSON válido.

Antes da escrita, o serviço volta a obter a prova privada no PostgreSQL e recalcula integralmente a
normalização. Qualquer diferença de IDs, URL, hash, bytes ou conteúdo normalizado termina a
operação. O comando recebe os três `snapshot_id` pais e o URL completo; não escolhe a versão mais
recente nem procura títulos semelhantes.

## Identidade e correspondências

Uma pessoa só entra na fotografia quando o bloco principal `Deputado` contém:

- `DepId` explícito;
- nome parlamentar explícito;
- uma situação oficial que indique que recebeu ou exerceu mandato.

Referências com nomes dentro de listas de iniciativas ou outras atividades não criam pessoas. Um
nome, uma sigla ou a ordem dos registos nunca substituem `DepId`. Se o mesmo `DepId` tiver fichas
divergentes no mesmo recurso, o lote é rejeitado em vez de escolher silenciosamente uma delas.

O grupo parlamentar conserva `GpId`, sigla e intervalo quando a fonte os fornece. O círculo
conserva `DepCPId` e designação. Sem ID oficial, o texto pode permanecer como observação privada,
mas não cria associação a uma entidade. Não existe fuzzy matching.

## Datas sem inferência

Os intervalos de `DepSituacao`, `DepGP` e `DepCargo` são preservados separadamente e com a
designação oficial. Não são convertidos automaticamente em início ou fim de mandato. Uma revisão
de mandato futura terá de confirmar a semântica, a fonte e o período próprios antes de criar uma
projeção pública `MANDATE`.

Datas não vazias que o parser não consiga interpretar fazem o lote falhar. Um intervalo legível em
que o fim anteceda o início é preservado como anomalia da própria fonte, acrescenta um aviso e fica
impedido de originar automaticamente um mandato. Uma correção exige nova versão de parser,
mantendo a fotografia anterior.

## Privacidade e imutabilidade

O novo modelo não contém campos de email, telefone, morada, NIF, NIPC ou outro identificador fiscal.
Mesmo que o ficheiro bruto venha a incluir contactos, esses valores permanecem apenas no arquivo
privado atestado e não são normalizados. A saída operacional apresenta apenas IDs técnicos,
contagens, estados e hashes.

As tabelas `parliament_deputy_snapshots` e `parliament_deputy_observations`:

- têm RLS ativa e privilégios removidos de `PUBLIC`, `anon` e `authenticated`;
- recusam `UPDATE` e `DELETE` por trigger;
- identificam a fotografia por documento, legislatura e versão do parser;
- guardam um SHA-256 da normalização canónica;
- validam as contagens materializadas antes de concluir a transação;
- acrescentam um `AuditEvent` de ingestão apenas com proveniência, hashes e contagens.

Não há escrita em `people`, `parties`, `mandates`, `parliamentary_membership_snapshots`,
`editorial_cases`, revisões ou projeções públicas.

## Porta operacional

O comando processa um único recurso e exige cumulativamente:

- `ENVIRONMENT=staging`;
- `DATABASE_URL` do staging;
- catálogo, manifesto e arquivo indicados por ID exato;
- URL parlamentar integral;
- `--confirm-private-staging`.

Não existe workflow agendado para esta operação. Integrar ou fazer deploy do código não executa a
normalização e uma migração não recolhe, revê ou publica dados.

## Critérios de aceitação

- entre 100 e 500 deputados com `DepId` único e prova explícita de mandato observado;
- pelo menos 70% de cobertura de IDs oficiais de grupo e círculo, sem preencher faltas por sigla;
- datas ilegíveis e duplicados divergentes recusados; intervalos contraditórios preservados com aviso;
- fonte, URL, data de recolha, SHA-256 e versão do parser preservados;
- nenhuma informação de contacto ou fiscal no modelo normalizado;
- fotografia `NOT_ASSERTED`, `PARTIAL`, `publishable=false`;
- zero pessoas, mandatos, casos editoriais ou eventos de publicação criados;
- testes unitários e integração num PostgreSQL descartável exercitam toda a cadeia.

O gate seguinte deve adaptar estas observações ao circuito editorial de perfis. Essa adaptação terá
de criar propostas `PENDING` distintas por âmbito e nunca poderá transformar uma observação, uma
situação ou uma data de recolha em publicação ou mandato sem decisão humana explícita.
