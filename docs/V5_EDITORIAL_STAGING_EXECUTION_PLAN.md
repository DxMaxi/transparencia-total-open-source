# V5.11 — plano de execução editorial em staging

## Estado e limite de autorização

Este documento transforma as guardas técnicas da V5.8 e da V5.10 numa sequência operacional
auditável. Foi preparado localmente em 13 de agosto de 2026. Não cria nem configura um projeto
Supabase, não consulta um ambiente Supabase/staging remoto, não aplica migrações, não cria contas,
não altera segredos, não faz deploy manual e não acede a uma base de dados real.

Cada fase abaixo exige autorização própria. Uma autorização para uma fase não autoriza a seguinte.
O deployment automático do frontend resultante de uma integração em `main` também não autoriza
backend, base de dados, Auth, recolha, revisão, publicação ou retirada.

## Baseline comprovada antes de staging

| Evidência | Resultado |
|---|---|
| Commit integrado em `main` | `f0f626eaabf21c0efffb741a35117ce4ca58feeb` |
| Pull request | [#48 — blindagem da ativação editorial](https://github.com/DxMaxi/transparencia-total-open-source/pull/48) |
| CI | [run 31705647871](https://github.com/DxMaxi/transparencia-total-open-source/actions/runs/31705647871), aprovado em PostgreSQL 17 |
| Deployment automático | `dpl_49w94v7DGKaAhjsNAbzSshQgFNf2`, estado `READY`, commit esperado |
| Domínio público | `https://www.transparenciatotal.pt`, verificado apenas em leitura |
| Rotas públicas verificadas | `/`, `/politicos`, `/atividade-parlamentar`, `/promessas` e `/contacto` |
| API pública | continua em `0.4.0`; os endpoints e o painel V5 não estão ativos |

O CI já prova, numa base local descartável com a forma mínima do Supabase, a aplicação integral das
migrações V5, a FK para `auth.users`, RLS, triggers, `search_path` fixo e ausência de privilégios
browser presentes ou futuros. Esta prova não substitui o inventário nem o ensaio no projeto remoto
de staging.

## Fundação técnica V5.12 integrada

O plano V5.11 foi integrado sem executar qualquer operação remota. A V5.12 integra em `main` um
workflow dedicado a staging; o environment GitHub `staging`, as variáveis, os segredos e qualquer
execução remota continuam por configurar e autorizar separadamente. O workflow
`.github/workflows/production-operations.yml`:

- pertence ao environment GitHub `production`;
- exige a confirmação `PRODUCAO`;
- usa nomes de credenciais de produção;
- nunca pode ser reutilizado, copiado com as mesmas credenciais ou apontado para staging.

A entrega V5.12 foi revista, integrada e teve CI verde. Acrescenta
`.github/workflows/staging-editorial-operations.yml`, validadores sanitizados e os respetivos testes
de contrato. Antes de qualquer operação remota, o workflow:

- aceitar apenas execução manual por `workflow_dispatch`, sem `push`, calendário ou execução
  automática;
- usar exclusivamente o environment GitHub `staging`;
- começar com `permissions: contents: read` e acrescentar apenas a permissão mínima demonstrada
  como necessária;
- separar inventário read-only, migração e ensaio editorial em operações e confirmações distintas;
- exigir o identificador esperado do projeto e recusar o identificador de produção;
- mapear nomes segregados, como `STAGING_DATABASE_URL` e `STAGING_IDENTIFIER_PEPPER`, para as
  variáveis da aplicação apenas dentro do job;
- manter URL, origem frontend e publishable key como configuração de staging; a publishable key não
  é uma credencial administrativa;
- nunca aceitar `service_role`, secret key Supabase ou uma credencial de produção no browser;
- não imprimir ligações, tokens, chaves, emails, UUID Auth, seed TOTP, QR code ou conteúdo editorial;
- parar no primeiro erro e conservar apenas evidência sanitizada.

A implementação integrada está descrita em
[V5.12 — fundação do workflow editorial de staging](V5_STAGING_WORKFLOW_FOUNDATION.md). A existência
do ficheiro, um eventual commit, PR ou merge não autoriza a sua execução, não configura o
environment GitHub e não permite reutilizar credenciais de produção.

## Decisão do destino

O destino recomendado é um projeto Supabase dedicado a staging, numa organização e região
deliberadamente escolhidas, sem ligação à base de produção. Um projeto ou branch já existente só
pode ser usado depois de provar o mesmo isolamento.

Antes de criar um recurso:

1. identificar as opções disponíveis e o respetivo custo, retenção, região e limitações;
2. obter confirmação explícita do custo quando existir qualquer encargo;
3. escolher um identificador público do ambiente, sem guardar a ligação privada no repositório;
4. comparar o destino com produção e provar que projeto, host e base não coincidem;
5. fixar os URLs exatos do frontend e backend de staging.

Qualquer dúvida sobre o destino interrompe o processo. Nunca se “experimenta” uma ligação para
descobrir se é produção.

## Matriz de autorização

| Fase | Tipo de acesso | Efeito possível | Autorização separada |
|---|---|---|---|
| 0. Workflow dedicado | apenas código local/GitHub | nenhum efeito em staging | commit, push e PR |
| 1. Inventário remoto | leitura de metadados | nenhum | consulta read-only |
| 2. Recurso e configuração | controlo do projeto | altera configuração | criação/custo e configuração |
| 3. Environment e credenciais | configuração GitHub | altera segredos/variáveis | alteração de segredos |
| 4. Migrações | escrita de esquema | cria objetos V5 | migração remota |
| 5. Inspetor | transação read-only | nenhum | inspeção remota |
| 6. Conta e MFA | Auth e tabela de staff | cria acesso privado | utilizador e perfil |
| 7. Ensaio editorial privado | escrita append-only em staging | cria versões e auditoria | dados de ensaio |
| 8. Publicação parlamentar | projeção pública de staging | muda saída pública de staging | publicação/retirada |
| 9. Produção | fora deste plano | pode afetar cidadãos | autorização de produção própria |

As fases 8 e 9 não fazem parte do primeiro ensaio editorial. A sua presença na matriz serve para
impedir que uma aprovação privada seja confundida com autorização de publicação.

## Fase 1 — inventário remoto exclusivamente read-only

Depois de existir autorização específica, recolher apenas metadados necessários para a decisão:

- organização, região, identificador do projeto e versão principal do PostgreSQL;
- estado do projeto e separação inequívoca de produção;
- Site URL e lista de redirects, sem tokens ou parâmetros sensíveis;
- estado de registo por email, login anónimo e criação por convite;
- algoritmo ativo de assinatura e presença de `kid` no JWKS;
- configuração relevante da Data API e schemas expostos;
- existência do environment GitHub `staging`, registando apenas nomes de variáveis e segredos;
- inexistência de contas de staff ou dados editoriais inesperados.

O relatório não conserva valores de segredos, ligações de base de dados, emails, UUID, tokens ou
cookies. Se o inventário mostrar um projeto já usado para produção, a execução termina.

## Fase 2 — configuração isolada do projeto

Esta é uma operação de escrita de configuração e precisa de nova autorização. O resultado esperado
é:

- signing key assimétrica ativa, preferencialmente `ES256`; `RS256` continua aceite pelo backend;
- tokens emitidos a usar efetivamente o algoritmo e `kid` esperados;
- registo público e login anónimo desativados;
- criação de utilizadores apenas por convite administrativo;
- Site URL exato e apenas o redirect completo `<site-url>/auth/confirmar`;
- nenhuma wildcard ampla de preview;
- CORS da API limitado à origem frontend de staging;
- frontend apenas com URL e publishable key desse projeto;
- nenhum `service_role` ou secret key no frontend ou no repositório.

A configuração de interface não é suficiente: RLS e revogações PostgreSQL continuam obrigatórias.

## Fase 3 — environment GitHub e credenciais segregadas

Depois de autorizada a alteração de segredos:

- criar ou rever o environment `staging` com proteção apropriada;
- adicionar apenas as variáveis e credenciais exigidas pelo workflow aprovado;
- usar um pepper exclusivo de staging, nunca o de produção;
- impedir que nomes `PRODUCTION_*` sejam lidos pelo workflow de staging;
- confirmar que logs e artefactos não revelam valores;
- registar apenas a presença e a data de rotação, não o conteúdo.

Se uma credencial aparecer num log, comentário, patch ou artefacto, parar, revogá-la e tratar o
evento antes de continuar.

## Fase 4 — migração de esquema em staging

Esta é a primeira escrita na base remota e exige autorização explícita para o destino exato. Antes
da migração devem existir:

- commit e CI aprovados;
- inventário read-only e identificação do destino;
- baseline do esquema e contagens agregadas;
- plano de recuperação do ambiente de staging;
- workflow dedicado aprovado;
- confirmação humana específica para migração.

A migração cria apenas o esquema, as funções, as guardas e as tabelas V5. Não cria utilizadores, não
recolhe fontes, não aprova propostas e não publica dados. Depois da migração, qualquer divergência
interrompe o processo.

## Fase 5 — inspeção estrutural read-only

Executar o inspetor apenas com `ENVIRONMENT=staging`, confirmação read-only e transação
`READ ONLY / REPEATABLE READ`. O resultado tem de provar:

- PostgreSQL 17 e todas as migrações esperadas;
- FK `staff_profiles.auth_user_id → auth.users.id`;
- RLS ativa e zero políticas browser nas cinco tabelas editoriais;
- zero privilégios efetivos ou predefinidos para `PUBLIC`, `anon` e `authenticated`;
- `search_path` fixo e triggers obrigatórios;
- inventário e contagens agregadas sem dados pessoais.

`database_ready=true` não prova Auth, MFA nem o circuito editorial e não autoriza a fase seguinte.

## Fase 6 — conta administrativa e MFA

Com nova autorização:

1. convidar uma única conta de ensaio;
2. obter o UUID em Auth sem o expor em logs;
3. criar um `staff_profiles` ativo com alias público e função `ADMIN`;
4. confirmar que `/editorial/session` permite preparar MFA em `aal1`;
5. confirmar que todas as outras rotas editoriais recusam `aal1` com
   `X-MFA-Required: true`;
6. inscrever e confirmar TOTP;
7. confirmar acesso em `aal2`;
8. confirmar que um perfil inativo é recusado de imediato.

Uma conta `REVIEWER` só é criada se um teste de separação de funções a tornar necessário e depois
de nova autorização. O seed TOTP, QR code, email, UUID e tokens nunca entram em evidência.

## Fase 7 — ensaio editorial privado

O primeiro ensaio usa um documento oficial real, já arquivado e atestado no próprio staging. Se for
necessário recolher ou copiar esse documento, essa operação sobre dados exige autorização própria.
Não se cria uma fonte fictícia para obter um resultado verde.

O ensaio deve:

1. registar contagens e hashes públicos anteriores;
2. confirmar URL oficial, data de recolha, SHA-256, bytes arquivados e atestação;
3. criar uma proposta privada `PENDING`;
4. avançar para `IN_REVIEW` e comparar fonte com JSON normalizado;
5. aprovar para `APPROVED` e provar que nenhuma projeção pública mudou;
6. rejeitar uma proposta distinta e conservar versão, decisão e auditoria;
7. corrigir uma versão e provar o regresso a `PENDING` sem alterar o passado;
8. provar a recusa de uma decisão concorrente baseada numa revisão antiga;
9. provar a recusa de NIF ou NIPC em claro;
10. comparar novamente contagens e hashes públicos.

Não entram neste ensaio correspondências por nome, fuzzy matching, inferências individuais a partir
de partidos, geração por IA, publicação parlamentar, retirada ou produção.

## Fase 8 — publicação e retirada parlamentares

Esta fase fica deliberadamente fora do primeiro ensaio. Só pode ser planeada depois de o circuito
privado passar integralmente e exige autorização autónoma para escrita na projeção pública de
staging. Deve usar apenas um âmbito parlamentar aprovado, `ADMIN` com `aal2`, fonte completa e
identificadores oficiais exatos. Publicação, retirada, correção e republicação são ações distintas,
append-only e auditadas.

Nenhum resultado de staging autoriza a mesma operação em produção.

## Encerramento e evidência

No fim de cada fase autorizada, conservar apenas:

- commit, PR, run de CI e instante;
- rótulo do ambiente e versão principal do PostgreSQL;
- resultado booleano das guardas e contagens agregadas;
- IDs editoriais públicos ou pseudónimos e hashes SHA-256 necessários à auditoria;
- resultado das recusas `aal1`, conta inativa e concorrência;
- contagens e hashes públicos antes e depois;
- limitações e falhas ainda abertas.

Nunca conservar ligações privadas, emails, UUID Auth, tokens, cookies, chaves, pepper, seed TOTP, QR
code, notas privadas ou conteúdo protegido.

Para retirar o acesso de ensaio, desativar primeiro o `staff_profiles`, revogar depois as sessões
Auth e só considerar remover a conta quando as restrições e a necessidade de auditoria o permitirem.
As versões, decisões e `AuditEvent` do ensaio não são apagados.

## Condições de paragem

Parar sem contornar guardas se ocorrer qualquer uma destas situações:

- destino ausente, ambíguo ou coincidente com produção;
- custo novo sem confirmação explícita;
- workflow de produção ou uma credencial de produção envolvidos;
- execução automática ou confirmação demasiado genérica;
- PostgreSQL diferente da versão suportada ou migração inesperada;
- token `HS256`, emissor, audiência ou `kid` inesperados;
- registo público ou login anónimo ativos;
- redirect ou CORS mais amplo do que o necessário;
- `aal1` aceite numa rota editorial ou perfil inativo ainda aceite;
- acesso browser, RLS, trigger, FK, `search_path` ou default inseguro;
- necessidade de usar `service_role` ou secret key no browser;
- divergência entre URL, data, SHA-256, arquivo e atestação;
- alteração da projeção pública durante aprovação privada;
- versão, decisão, direito de resposta ou evento histórico alterável;
- NIF/NIPC em claro;
- qualquer segredo ou dado pessoal em logs ou artefactos.

Uma falha permanece `FAIL`; não se desativa a verificação para prosseguir.

## Revisão de documentação vigente

Na preparação de 13 de agosto de 2026 foram revistas as referências oficiais:

- [Signing Keys do Supabase](https://supabase.com/docs/guides/auth/signing-keys);
- [MFA do Supabase](https://supabase.com/docs/guides/auth/auth-mfa) e
  [TOTP](https://supabase.com/docs/guides/auth/auth-mfa/totp);
- [Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls) e
  [configuração geral de Auth](https://supabase.com/docs/guides/auth/general-configuration);
- [segurança da Data API](https://supabase.com/docs/guides/api/securing-your-api);
- [breaking changes do Supabase](https://supabase.com/changelog?types=breaking-change).

As alterações anunciadas sobre o endpoint Management API de logs, versões explícitas de extensões e
o proxy Envoy self-hosted não são usadas por este percurso. A evolução da exposição da Data API
também não substitui RLS e revogações explícitas. Esta conclusão deve ser revista novamente na data
da execução, porque configuração e documentação do fornecedor podem mudar.

## Critérios para considerar staging comprovado

O gate de staging só fica concluído quando:

- o workflow dedicado estiver integrado e o destino isolado aprovado;
- as fases 1 a 7 tiverem evidência válida e sem segredos;
- todas as caixas correspondentes das secções C e D da checklist estiverem justificadamente
  marcadas;
- a projeção pública de produção continuar inalterada;
- falhas e limitações estiverem visíveis;
- houver uma decisão explícita sobre avançar, corrigir ou parar.

Mesmo nesse ponto, backend de produção, migrações de produção, publicação de dados, IA, utilizadores
reais e release `v0.5.0` continuam fora desta autorização.
