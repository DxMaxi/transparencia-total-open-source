# Recuperação da base de dados

Este runbook descreve o estado real e o ensaio necessário para recuperar o PostgreSQL do projeto.
Não inclui credenciais e não promete uma capacidade que ainda não tenha sido testada.

## Estado e leitura deste runbook

Os números da secção seguinte são a prova histórica de agosto, não o volume atual. As provas
recentes e a situação da migração V5 estão no [registo de entrega](V5_DELIVERY_2026-09-09.md).
Um ensaio que autorize a migração protegida deve ter menos de 24 horas; uma prova antiga não
substitui esse requisito. A agenda de backup não garante a hora efetiva de execução nem o RPO.

## Baseline histórica — 9 de agosto de 2026

- Provedor: Supabase/PostgreSQL, projeto de produção `ACTIVE_HEALTHY`, plano Free confirmado em
  9 de agosto de 2026.
- Backup gerido ou point-in-time recovery do fornecedor: não demonstrado e, por isso, não usado como
  base da capacidade de recuperação.
- Destino externo: Backblaze B2 **EU Central**, bucket privado, SSE-B2, Object Lock
  `COMPLIANCE` e ciclo de vida limitado ao prefixo `database/`.
- Credenciais: chave de backup limitada a leitura, escrita e retenção; chave de restauro limitada a
  leitura. Ambos os âmbitos foram validados pela API B2 antes de usar produção ou descarregar a
  cópia.
- Automatização: backup diário às 05:17 UTC em
  `.github/workflows/database-backup.yml`; restauro exclusivamente manual em
  `.github/workflows/database-restore-drill.yml`.
- Primeira cópia real: [execução 31313078924](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31313078924),
  27 966 268 bytes cifrados, SHA-256
  `5255c0fa9a85711d0c0c7f86162376aece2b1d26026e32056916c2234bb41337`, protegida em
  `COMPLIANCE` até 9 de setembro de 2026.
- Primeiro ensaio real: [execução 31318699132](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31318699132),
  resultado `PASS` num PostgreSQL 17 isolado e efémero; produção não foi usada como destino.
- Conteúdo restaurado: 13 migrações, 54 tabelas, 104 737 linhas e 32 objetos de arquivo íntegros;
  estado operacional `HEALTHY`.
- Medição: RPO observado de 7 759 segundos e RTO observado de 37 segundos.
- Atestação: SHA-256
  `ed19814bbc93b3fcd8fff918a2465b52a41b2904e5a23d0ee40bea54a7abd859`, conservada como
  artefacto não sensível durante 90 dias.
- A identidade privada `age` foi removida do environment `recovery` após o ensaio e permanece
  guardada fora do GitHub.

O arquivo content-addressed prova a integridade dos bytes existentes. Não protege contra perda do
projeto inteiro porque está no mesmo PostgreSQL. As migrações reconstroem o esquema, mas não
reconstroem decisões de revisão, respostas, eventos de auditoria ou documentos arquivados.

A configuração completa, nomes das variáveis e sequência operacional estão em
[Backup PostgreSQL cifrado no Backblaze B2 EU](BACKUP_BACKBLAZE_B2.md). A primeira execução e o
primeiro restauro estão registados acima; futuras alterações de esquema, PostgreSQL, cifragem ou
fornecedor exigem novo ensaio.

## Requisitos da cópia externa

A operação ativa deve continuar a cumprir os requisitos seguintes:

1. ser criada por uma ferramenta PostgreSQL compatível com a versão do servidor;
2. incluir esquema, dados e objetos necessários à aplicação;
3. ser cifrada antes de sair do ambiente controlado;
4. ficar fora do projeto Supabase de produção, com acesso mínimo e registo de acessos;
5. ter retenção e eliminação definidas de acordo com a política de privacidade;
6. guardar, separadamente, data, versão da ferramenta, tamanho e SHA-256 do ficheiro cifrado;
7. nunca escrever `DATABASE_URL`, palavras-passe ou chaves nos argumentos registados, logs,
   artefactos de CI ou repositório.

Uma cópia num artefacto CI sem cifragem própria não satisfaz este gate. Uma cópia na mesma base de
dados também não satisfaz o requisito de separação do domínio de falha.

## Ensaio de restauro

O ensaio deve usar um PostgreSQL isolado e descartável; nunca restaurar por cima de produção.

1. Registar o instante de início, o identificador da cópia e o SHA-256 esperado.
2. Confirmar o SHA-256 antes de decifrar.
3. Restaurar roles estritamente necessárias, esquema e dados no destino isolado.
4. Comparar a lista de migrações com `prisma/migrations` e executar apenas migrações posteriores à
   cópia.
5. Iniciar o backend com integrações externas e publicação desativadas.
6. Executar, em modo de leitura, `python -m scripts.verify_v4_archive`.
7. Executar `python -m scripts.check_v4_operational_status`; datas antigas podem ficar `stale` num
   ensaio e devem ser registadas, não alteradas para forçar sucesso.
8. Comparar contagens de pessoas, reuniões, iniciativas, votações, revisões, `AuditEvent`, direitos
   de resposta, `SourceDocument`, atestações e objetos arquivados.
9. Confirmar que as proteções append-only e os caminhos fixos das funções continuam presentes.
10. Registar duração, perdas observadas, RPO e RTO; destruir o ambiente temporário de forma segura.

## Entrada em produção após desastre

Só alterar o destino da API depois de o arquivo passar, as contagens serem explicadas e os
diagnósticos de segurança não apresentarem `WARN` ou `ERROR`. Após o corte:

1. repetir readiness e estado público;
2. executar smoke das páginas essenciais;
3. confirmar cabeçalhos de segurança, ausência de cookies não essenciais e CORS;
4. registar o incidente e a recuperação num `AuditEvent` ou no diário operacional aplicável;
5. conservar a base antiga sem mutações até terminar a análise, quando isso for possível e seguro.

## Cadência ativa e manutenção

- backup diário às 05:17 UTC;
- Object Lock `COMPLIANCE` por pelo menos 30 dias;
- expiração operacional aproximada aos 46 dias, através de regra 45 + 1 limitada a `database/`;
- ensaio de restauro inicial e depois trimestral;
- responsável por falhas: mantenedor do repositório, através do histórico e alertas GitHub Actions;
- cópia cifrada adicional mensal em suporte offline separado: recomendada, mas não automatizada nem
  contada como prova do gate V4.

A política B2 diária está ativa desde a primeira execução real. Os valores de RPO e RTO acima são
medições desse ensaio, não garantias permanentes; cada ensaio trimestral deve registar novos valores
sem substituir o histórico.

Referência operacional do provedor: [Backups da base de dados no Supabase](https://supabase.com/docs/guides/platform/backups).


## Ensaio V5 sobre uma cópia real (setembro de 2026)

O dispatch `rehearse_migrations=true` acrescenta duas provas à verificação normal do backup:

1. Aplicar as migrações pendentes no PostgreSQL local efémero, comparar contagens e impressões
   de todas as colunas originais, conferir cada checksum de migração e verificar RLS/privilégios.
   A única coluna retirada admitida é `organisations.public_nipc`, depois de provar que não tem
   nenhum valor; qualquer outro desaparecimento ou alteração de conteúdo faz falhar o ensaio.
2. Acrescentar um perfil editorial inativo exclusivamente sintético, cifrar uma cópia do esquema
   V5 e restaurá-la numa segunda base efémera. Conferir novamente dados, migrações e isolamento.

O backup cobre `public`, sem contas, sessões, palavras-passe nem fatores MFA de Supabase Auth.
O restauro isolado cria em `auth.users` somente UUIDs inertes necessários às referências de staff.
Esses placeholders não são contas funcionais e não provam recuperação de autenticação. A
reconstituição das contas e associação aos perfis tem de ser tratada separadamente num desastre.
O helper recusa qualquer destino diferente das duas bases localhost fixadas no workflow.

Como o dump portátil exclui ACLs, o helper repõe a recusa de privilégios browser antes de terminar.
As impressões de conteúdo e a cópia intermediária cifrada são eliminadas; só resultados agregados
são guardados nos artefactos. A ausência de COMMIT perante falha mantém o restauro atómico.


A comparação de checksums admite somente LF/CRLF e até duas quebras finais, sem alterar qualquer
byte de conteúdo SQL. As sete diferenças V4 observadas no backup de 09-09 foram reconciliadas
contra o histórico Git; todas eram exclusivamente quebras de linha. O histórico Prisma fica intacto.

O workflow `production-schema-migration.yml` é manual, exige o commit exato de `main`, confirmação
`MIGRAR-V5` e um ensaio de menos de 24 horas com as duas provas aprovadas. Verifica repositório,
evento, commit e ausência de diferenças nas migrações antes de usar o secret de produção. O destino
é limitado ao projeto Supabase confirmado, com TLS e porta de sessão. Compara o conteúdo antes e
depois e conserva apenas a prova agregada; não convida contas nem publica conteúdo editorial.

## Capacidade e integridade são verificações independentes

`report_archive_capacity` mede tanto a relação `raw_source_objects` (incluindo índices/TOAST)
como a base inteira por `pg_database_size`. O tamanho lógico dos documentos não equivale ao
espaço ocupado em disco: o PostgreSQL pode comprimir os bytes. Um arquivo abaixo do seu limite
não prova que a base completa esteja abaixo da quota.

- `RAW_ARCHIVE_WARNING_BYTES`: aviso para a relação, por omissão 400 000 000 bytes.
- `DATABASE_WARNING_BYTES`: aviso para a base inteira, por omissão 450 000 000 bytes,
  conservador para a instalação Free atual. Não é a quota do fornecedor nem uma proibição
  técnica de escrita. Rever explicitamente perante mudança de alojamento/capacidade.
- `OK` significa apenas que ambos os limites configurados não foram atingidos; não garante
  capacidade para qualquer carga futura. `WARNING` termina com código 2; `CHECK_FAILED`, com 1.

As ligações têm limites de espera e as leituras usam uma transação read-only. Nenhum destes
comandos apaga, compacta, publica ou regista uma nova sincronização na base.

O workflow `Archive integrity` conserva os dois relatórios durante 30 dias. Um aviso de capacidade
não impede o cálculo da integridade; o resultado global continua a falhar se uma das verificações
requerer atenção. Consultar os resultados separados antes de interpretar uma execução vermelha
como corrupção. Os relatórios não incluem conteúdo documental ou credenciais.

`verify_v4_archive` calcula SHA-256 diretamente sobre o `bytea` real no PostgreSQL e recebe
apenas hashes, tamanhos e chaves. Continua a comparar hash declarado, tamanho e chave derivada;
não aceita o hash registado como prova sem ler os bytes. Evita transferir o arquivo completo
para a memória do verificador. A consulta tem um limite de 300 segundos; excedê-lo produz falha
de verificação, nunca um resultado íntegro por omissão. Testes em PostgreSQL descartável alteram
conteúdo sem alterar o comprimento, tamanho declarado e chave para comprovar a deteção.
