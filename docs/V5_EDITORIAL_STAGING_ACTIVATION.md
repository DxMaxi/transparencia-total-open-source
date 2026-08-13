# V5.10 — gate de ativação editorial em staging

## Estado e autorização

Esta entrega fecha localmente as condições técnicas que podem ser verificadas antes do primeiro
ensaio editorial remoto. Não autoriza configurar o Supabase, aplicar uma migração em staging,
criar utilizadores, alterar segredos, publicar o backend, recolher dados nem executar operações de
escrita sobre dados reais. Cada uma dessas operações continua a exigir autorização própria.

A V5.10 também não transforma uma verificação estrutural em aprovação operacional. O inspetor pode
provar a forma da base de dados; as definições de Auth, o convite, o MFA e o percurso editorial têm
de ser comprovados separadamente no ambiente certo.

## Falha preventiva corrigida

O PostgreSQL concede `EXECUTE` a `PUBLIC` por defeito quando uma função é criada. Uma instrução
`ALTER DEFAULT PRIVILEGES IN SCHEMA public ... REVOKE` não consegue retirar um privilégio concedido
pelo default global; a documentação oficial do PostgreSQL identifica expressamente essa diferença.

A migração `20260813150000_v5_harden_default_privileges` acrescenta, para o papel que executa as
migrações:

- revogação dos privilégios predefinidos globais de `PUBLIC` em tabelas, sequências e funções;
- a mesma revogação global para `anon` e `authenticated`, quando esses papéis existem;
- nenhuma política, `GRANT`, conta, segredo ou alteração de dados.

As revogações específicas do esquema `public` e dos objetos existentes continuam na migração de
blindagem V4. As duas camadas são necessárias: uma fecha os objetos e defaults específicos já
conhecidos; a outra impede que o default global volte a abrir uma função futura.

Referência oficial: [ALTER DEFAULT PRIVILEGES — PostgreSQL 17](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html).

## Prova automática antes de staging

O PostgreSQL 17 descartável do CI continua a ser preparado com `auth.users`, `anon` e
`authenticated` antes de aplicar as migrações. Depois da V5.10, o teste de integração cria ainda
uma função-sonda temporária e confirma que `PUBLIC`, `anon` e `authenticated` não recebem
`EXECUTE`. A função é removida no final do teste e nunca existe fora dessa base descartável.

O inspetor read-only passa também a avaliar os defaults globais e específicos de `public` dos
proprietários dos objetos editoriais. Um privilégio futuro efetivo para `anon` ou `authenticated`
faz falhar `safe_default_privileges` e mantém `database_ready=false`.

O relatório conserva apenas:

- resultado e explicação de cada verificação;
- versão principal do PostgreSQL;
- contagens de tabelas, funções, triggers, políticas e migrações editoriais;
- número de defaults inseguros, que tem de ser zero;
- contagens agregadas de perfis `ADMIN` e `REVIEWER` ativos;
- lista das verificações Auth que continuam manuais.

Não apresenta nomes de ligação, emails, UUID, tokens, aliases privados, conteúdo editorial ou
segredos.

## Ordem futura, sempre separada

Quando existir autorização específica para staging, a ordem segura é:

1. confirmar o commit e o CI integralmente verdes;
2. confirmar destino, versão e isolamento da base de staging;
3. configurar Auth com signing key assimétrica, URLs exatos e registo público desativado;
4. aplicar as migrações V5 por uma operação dedicada;
5. convidar uma conta de ensaio e associá-la a `staff_profiles` sem expor o email;
6. provar recusa `aal1`, TOTP e acesso `aal2`;
7. executar o inspetor numa transação `READ ONLY` e `REPEATABLE READ`;
8. só com nova autorização, ensaiar o circuito com uma fonte oficial já arquivada e atestada;
9. guardar evidência sem segredos e voltar a confirmar que a projeção pública não mudou.

Nenhum passo autoriza automaticamente o seguinte. Uma falha permanece falha e interrompe o ensaio.

## Condições de saída desta entrega local

A V5.10 local fica pronta para revisão quando:

- a migração de defaults passa a validação Prisma e o PostgreSQL descartável do CI;
- o inspetor falha perante qualquer default browser inseguro;
- o relatório não expõe dados pessoais ou credenciais;
- os contratos frontend e backend, `ruff`, formatação, `mypy` e build permanecem verdes;
- o patch é revisto antes de qualquer commit, push, PR ou operação remota.

Mesmo depois desses pontos, migração em staging, configuração Supabase, criação de staff e ensaio
editorial continuam abertos na checklist de release.
