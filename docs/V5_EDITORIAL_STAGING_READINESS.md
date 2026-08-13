# V5.8 — prontidão editorial para staging

## Estado e limite desta entrega

Esta entrega prepara uma prova segura da fundação editorial V5.1 a V5.4 antes de qualquer ativação
remota. Não configura o Supabase, não aplica migrações em staging ou produção, não cria contas, não
altera segredos e não escreve em dados reais.

O objetivo é impedir duas conclusões falsas:

1. testes verdes num PostgreSQL convencional não provam automaticamente o caminho específico do
   Supabase;
2. uma inspeção PostgreSQL verde não prova que o registo público está desativado, que os redirects
   estão corretos ou que MFA foi realmente concluído.

## O que passa a ser comprovado no CI

Antes de aplicar as migrações, o job backend cria exclusivamente na base PostgreSQL 17 descartável:

- os papéis `anon` e `authenticated`, ambos sem login e sem privilégios administrativos;
- um `auth.users` mínimo, suficiente para ativar a FK condicional de `staff_profiles`;
- uma marca interna que permite aos testes reconhecerem a base como descartável.

O bootstrap recusa executar se faltar qualquer uma destas condições:

- `ENVIRONMENT=test`;
- `CONFIRM_DISPOSABLE_DATABASE=true`;
- anfitrião `localhost`, `127.0.0.1` ou loopback IPv6;
- nome da base terminado em `_test`.

Não existe opção para contornar estas guardas. O script não aceita um endereço remoto, mesmo quando
a confirmação está presente.

Depois do bootstrap, o CI aplica todas as migrações e comprova:

- FK `staff_profiles.auth_user_id → auth.users.id` com `DELETE RESTRICT`;
- papéis `anon` e `authenticated` sem login, `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`
  ou `BYPASSRLS`;
- RLS ativa nas cinco tabelas editoriais;
- ausência de políticas RLS para browser;
- ausência de `USAGE`, privilégios de tabela e `EXECUTE` para `anon` e `authenticated`;
- ausência de privilégios predefinidos globais ou específicos de `public` que possam voltar a
  expor uma tabela, sequência ou função futura aos papéis browser;
- `search_path` mínimo e fixo nas funções editoriais;
- presença e ativação dos triggers de integridade, append-only, projeção e publicação;
- ciclo `PENDING → IN_REVIEW → APPROVED` e correção para nova versão `PENDING`;
- publicação e retirada parlamentares apenas pelos adaptadores específicos.

O bootstrap pertence apenas ao CI e a bases locais descartáveis. Não é um emulador integral do
Supabase Auth, não emite JWT e nunca deve ser executado em staging.

## Inspetor PostgreSQL read-only

Depois de as migrações e a conta de ensaio terem sido autorizadas e preparadas em staging, a
estrutura pode ser inspecionada com:

```bash
cd backend
python -m scripts.inspect_editorial_staging_readiness --confirm-read-only
```

O processo exige simultaneamente:

- `ENVIRONMENT=staging`;
- `DATABASE_URL` configurada;
- `SUPABASE_URL` configurada;
- a confirmação explícita `--confirm-read-only`.

A transação é `READ ONLY` e `REPEATABLE READ`. O relatório contém apenas resultados booleanos,
versão principal do PostgreSQL, contagens do inventário estrutural e contagens agregadas de
`ADMIN`/`REVIEWER` ativos. Não apresenta emails, UUID Auth, aliases, tokens, URLs de ligação,
conteúdo editorial ou segredos.

Um resultado `database_ready=true` prova apenas a estrutura PostgreSQL enumerada no relatório. Não
autoriza o passo seguinte nem prova os controlos do dashboard Supabase.

## Configuração manual do Supabase Auth

Estes controlos permanecem obrigatoriamente manuais e separados:

1. Confirmar uma signing key assimétrica em uso, `RS256` ou `ES256`. A mera presença de uma chave
   pública standby no JWKS não prova que os tokens atuais já usam essa chave.
2. Usar apenas a publishable key no frontend. A aplicação não precisa de `service_role` nem de uma
   secret key Supabase.
3. Desativar registo público e manter criação de contas exclusivamente por convite no dashboard.
4. Configurar o Site URL exato do ambiente.
5. Autorizar apenas o redirect completo `<site-url>/auth/confirmar`; previews adicionais são
   entradas exatas e deliberadas, nunca um wildcard amplo.
6. Confirmar que `NEXT_PUBLIC_SUPABASE_URL` e `SUPABASE_URL` apontam para o mesmo projeto de staging.
7. Confirmar que o CORS da API contém apenas a origem frontend de staging necessária.

As mudanças de 2026 na exposição automática de tabelas pela Data API não são usadas como mecanismo
de segurança. Este projeto conserva RLS e revoga explicitamente acesso de `PUBLIC`, `anon` e
`authenticated`, mesmo quando uma tabela não seja exposta automaticamente.

## Convite, MFA e desativação

A criação da conta de ensaio é outra operação, com autorização própria:

1. Convidar a pessoa no dashboard Supabase.
2. Confirmar o UUID em **Authentication → Users**.
3. Inserir um `staff_profiles` com alias público, função `ADMIN` e referência exata ao UUID convidado.
4. Entrar pela ligação enviada sem revelar no ecrã se um email pertence à equipa.
5. Com sessão `aal1`, confirmar:
   - `GET /api/v1/editorial/session` responde apenas para permitir preparar MFA;
   - qualquer rota de casos responde `403` e `X-MFA-Required: true`.
6. Inscrever e confirmar TOTP.
7. Com sessão `aal2`, confirmar o acesso ao painel e ao inventário privado.

Para retirar acesso, a ordem segura é:

1. definir `staff_profiles.active=false`, produzindo recusa imediata na API;
2. revogar as sessões Supabase;
3. só depois eliminar a conta Auth, se houver fundamento e se as restrições de integridade o
   permitirem.

Eliminar apenas o utilizador Auth não deve ser tratado como revogação imediata de todos os JWT já
emitidos.

## Ensaio do circuito editorial

O ensaio deve usar uma fonte oficial já arquivada e atestada em staging; não se cria uma fonte falsa
para obter um resultado verde.

Ordem obrigatória:

1. registar as contagens e hashes públicos anteriores;
2. criar uma proposta privada `PENDING` sobre a fonte atestada;
3. iniciar revisão e obter `IN_REVIEW`;
4. comparar URL, data de recolha, SHA-256, arquivo e JSON normalizado;
5. aprovar para `APPROVED`, confirmando que nenhuma projeção pública mudou;
6. corrigir, confirmando nova versão `PENDING` e preservação da versão e decisões anteriores;
7. para Parlamento, testar publicação e retirada apenas com `ADMIN`, prova completa e âmbito
   específico;
8. confirmar `AuditEvent`, decisão, evento de publicação e efeito público, sem notas privadas na API
   pública;
9. voltar a comparar as contagens e hashes públicos.

Correspondências de nomes continuam fora deste ensaio. Não existe fuzzy matching, e uma posição
coletiva partidária nunca é convertida num voto individual.

## Condições de paragem

Parar sem promover dados se ocorrer qualquer uma destas situações:

- token `HS256`, emissor, audiência ou `kid` inesperados;
- `aal1` aceite numa rota editorial;
- conta inativa ainda aceite;
- privilégio efetivo de `anon` ou `authenticated` numa tabela ou função editorial;
- default global ou específico de `public` que conceda a um papel browser acesso a um objeto
  futuro;
- tabela editorial sem RLS;
- trigger, FK ou migração obrigatória ausente;
- alteração da projeção pública durante aprovação privada;
- versão, decisão ou evento histórico alterável;
- divergência entre URL, data, SHA-256 e arquivo atestado;
- necessidade de usar uma secret key Supabase no browser;
- qualquer dúvida sobre o destino da base de dados.

Cada falha permanece visível como falha. Não se desativa uma guarda para completar a checklist.

## Evidência a conservar

Quando o ensaio remoto for autorizado, conservar sem segredos:

- commit e resultado do CI;
- data, ambiente e versão PostgreSQL;
- relatório read-only da estrutura;
- identificação pública/alias da função de quem fez cada decisão, nunca o email no relatório;
- IDs e SHA-256 das versões, decisões e eventos criados no ensaio;
- contagens públicas antes e depois;
- resultado da recusa `aal1` e do acesso `aal2`;
- limitações ou itens ainda por determinar.

Esta evidência permite marcar itens da checklist, mas não substitui autorização para migração,
configuração, criação de staff, publicação ou deploy.

O reforço preventivo dos defaults e a sequência de autorização seguinte estão documentados em
[V5.10 — gate de ativação editorial em staging](V5_EDITORIAL_STAGING_ACTIVATION.md).
