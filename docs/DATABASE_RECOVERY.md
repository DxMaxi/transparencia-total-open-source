# Recuperação da base de dados

Este runbook descreve o estado real e o ensaio necessário para recuperar o PostgreSQL do projeto.
Não inclui credenciais e não promete uma capacidade que ainda não tenha sido testada.

## Estado atual

- Provedor: Supabase/PostgreSQL, projeto de produção `ACTIVE_HEALTHY`.
- Plano confirmado em 9 de agosto de 2026: Free.
- Backup gerido ou point-in-time recovery: não demonstrado e, por isso, não garantido.
- Destino externo configurado em 9 de agosto de 2026: conta Backblaze B2 confirmada em **EU
  Central**, bucket privado no endpoint `eu-central-003`, cifragem predefinida SSE-B2, Object Lock e
  retenção `COMPLIANCE` de 30 dias ativos. A regra de ciclo de vida está limitada a `database/`, com
  ocultação aos 45 dias e eliminação de versões ocultas 1 dia depois.
- A primeira chave de escrita, demasiado ampla, foi revogada antes de ser usada. As duas chaves de
  privilégio mínimo ainda têm de ser aprovisionadas e validadas; nenhum segredo revogado é válido.
- Automatização: preparada em `.github/workflows/database-backup.yml`, incluindo validação
  fail-closed do âmbito da credencial, mas ainda não demonstrada com credenciais e objeto reais.
- Cópia lógica externa: ainda não demonstrada.
- Ensaio de restauro: não executado.
- RPO e RTO: indisponíveis até existir um ensaio medido.
- Arquivo interno: 32 objetos, todos verificados, zero corrupção em 9 de agosto de 2026.
- Migrações: versionadas em `prisma/migrations` e aplicadas por operação separada.

O arquivo content-addressed prova a integridade dos bytes existentes. Não protege contra perda do
projeto inteiro porque está no mesmo PostgreSQL. As migrações reconstroem o esquema, mas não
reconstroem decisões de revisão, respostas, eventos de auditoria ou documentos arquivados.

A configuração completa, nomes das variáveis e sequência de ativação estão em
[Backup PostgreSQL cifrado no Backblaze B2 EU](BACKUP_BACKBLAZE_B2.md). A implementação no
repositório não altera o estado deste runbook enquanto uma execução e um restauro reais não forem
registados.

## Requisitos da cópia externa

A operação só deve ser ativada depois de o responsável definir um destino autorizado. A cópia deve:

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

## Cadência decidida, ainda por ativar

- backup diário às 05:17 UTC;
- Object Lock `COMPLIANCE` por pelo menos 30 dias;
- expiração operacional aproximada aos 46 dias, através de regra 45 + 1 limitada a `database/`;
- ensaio de restauro inicial e depois trimestral;
- responsável por falhas: mantenedor do repositório, através do histórico e alertas GitHub Actions;
- cópia cifrada adicional mensal em suporte offline separado.

Esta política só fica **ativa** depois da primeira execução real. Qualquer objetivo de RPO/RTO
publicado deve resultar do ensaio, não de uma estimativa.

Referência operacional do provedor: [Backups da base de dados no Supabase](https://supabase.com/docs/guides/platform/backups).
