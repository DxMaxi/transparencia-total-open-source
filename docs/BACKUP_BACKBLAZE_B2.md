# Backup PostgreSQL cifrado no Backblaze B2 EU

Este runbook configura a cópia externa que falta para fechar a V4. O destino escolhido é um bucket
privado Backblaze B2 na região **EU Central**, alojada em Amesterdão. A escolha da região é feita ao
criar a conta Backblaze e não pode ser alterada nessa conta. Consulte a documentação oficial sobre
[regiões de dados](https://www.backblaze.com/docs/cloud-storage-data-regions).

## Estado do gate

**IMPLEMENTED no repositório; BLOCKED na operação até existir uma execução real e um restauro
aprovado.** Ter as workflows e este documento não prova que existe uma cópia recuperável.

O fecho exige, por esta ordem:

1. criar e configurar o bucket europeu;
2. executar manualmente o primeiro backup;
3. confirmar no B2 o objeto, SHA-256 e Object Lock;
4. restaurar esse objeto no PostgreSQL efémero da workflow de ensaio;
5. registar no gate V4 o URL da execução, o SHA-256 da atestação, RPO e RTO observados;
6. remover do GitHub a chave privada de decifragem usada temporariamente no ensaio.

Até estes seis passos passarem, `docs/V4_TO_V5_RELEASE_GATE.md` permanece `BLOCKED`, não se cria a
tag `v0.4.0` e não se anuncia recuperação garantida.

## O que a implementação garante

- `pg_dump` da mesma versão principal do PostgreSQL de produção, limitado ao esquema `public`;
- formato PostgreSQL custom, sem owners nem privilégios do fornecedor;
- cifragem `age` X25519 em streaming: o dump em claro não é gravado no runner;
- a workflow diária recebe apenas a chave **pública** `age`;
- inventários de leitura antes e depois da cópia; uma mudança de contagens ou migrações bloqueia o
  envio e evita associar um manifesto incoerente ao dump;
- manifesto separado com data, commit, versão do `pg_dump`, tamanho e SHA-256 do ficheiro cifrado;
- Object Lock explícito em modo `COMPLIANCE` durante pelo menos 30 dias, tanto no dump como no
  manifesto;
- confirmação pós-upload do tamanho, metadados e retenção devolvidos pelo B2;
- restauro apenas num serviço PostgreSQL 17 efémero, com URL local fixa e sem acesso ao segredo de
  produção;
- SHA-256 confirmado antes da decifragem; comparação integral das contagens das tabelas públicas e
  das migrações; verificação do arquivo oficial e do estado operacional;
- atestação sem credenciais nem dados pessoais, conservada como artefacto da execução durante 90
  dias. O seu SHA-256 deve depois ser registado no gate versionado.

O manifesto contém nomes e contagens de tabelas, não contém linhas da base de dados, URL de ligação,
bucket, palavra-passe, Application Key nem chave privada `age`.

## 1. Criar a conta e o bucket

1. Crie uma conta Backblaze B2 escolhendo **EU Central**. Se uma conta existente tiver outra região,
   crie uma conta separada para este backup; a região de uma conta já criada não é convertível.
2. Crie um bucket com nome próprio, tipo **Private** e sem qualquer referência a pessoas ou segredos.
3. Ative **Object Lock**. Esta ativação não pode ser revertida.
4. Configure a retenção predefinida do bucket em modo **Compliance**, por 30 dias. A workflow aplica
   adicionalmente a retenção a cada objeto e falha se não a conseguir confirmar. O funcionamento e
   os modos são descritos na documentação oficial de
   [Object Lock](https://www.backblaze.com/docs/cloud-storage-object-lock).
5. Configure uma regra de ciclo de vida apenas para o prefixo `database/`:

   - ocultar ficheiros 45 dias depois do upload;
   - eliminar versões ocultas 1 dia depois;
   - cancelar uploads multipart incompletos após 1 dia, se a consola disponibilizar essa opção.

O Object Lock prevalece enquanto a retenção estiver ativa. A regra de 45 + 1 dias deixa uma margem
superior aos 30 dias imutáveis. Não aplique uma regra vazia a todo o bucket: um prefixo vazio pode
atingir todos os objetos. Consulte as
[regras de ciclo de vida B2](https://www.backblaze.com/docs/cloud-storage-lifecycle-rules).

Copie da página do bucket o **S3 Endpoint** exato, por exemplo
`https://s3.eu-central-003.backblazeb2.com`. A região é a segunda parte do endpoint, neste exemplo
`eu-central-003`; não presuma o número do cluster.

## 2. Criar duas Application Keys limitadas

Não use na automação a Master Application Key nem o perfil genérico **Read and Write** da consola.
Esse perfil concede operações que estes fluxos não precisam. Em 9 de agosto de 2026, a primeira
chave criada com esse perfil foi revogada antes de ser usada e nenhum objeto foi enviado. O segredo
revogado não pode ser reutilizado e qualquer cópia temporária deve ser eliminada.

Crie as duas chaves com a versão 4 da ferramenta oficial B2 CLI, para fixar o conjunto exato de
capacidades. A credencial administrativa usada só para este aprovisionamento deve permanecer no
computador controlado, nunca no GitHub, no repositório, numa workflow ou nos argumentos da linha de
comandos. `b2 account authorize` pede o identificador e o segredo sem os incluir no comando.

```powershell
$bucket = Read-Host "Nome exato do bucket B2"
$cacheB2 = Join-Path ([IO.Path]::GetTempPath()) ("tt-b2-provision-" + [guid]::NewGuid().ToString("N") + ".sqlite")
$env:B2_ACCOUNT_INFO = $cacheB2

b2 account authorize
b2 key create --bucket $bucket --name-prefix "database/" transparencia-total-backup readFiles,writeFiles,readFileRetentions,writeFileRetentions
b2 key create --bucket $bucket --name-prefix "database/" transparencia-total-restore readFiles
b2 key list --long

b2 account clear
Remove-Item -LiteralPath $cacheB2 -Force -ErrorAction SilentlyContinue
Remove-Item Env:B2_ACCOUNT_INFO -ErrorAction SilentlyContinue
```

Guarde cada `applicationKeyId` e `applicationKey` diretamente no respetivo secret do GitHub assim
que a ferramenta os apresentar; o segredo só é mostrado uma vez. Não os copie para notas, ficheiros
do projeto, mensagens ou capturas de ecrã. Se foi usada a Master Application Key para aprovisionar,
regenere-a depois e guarde a nova versão apenas no cofre administrativo offline.

Os perfis permitidos são deliberadamente exatos:

| Chave | Capacidades permitidas | Âmbito obrigatório |
| --- | --- | --- |
| `transparencia-total-backup` | `readFiles`, `writeFiles`, `readFileRetentions`, `writeFileRetentions` | bucket exato e prefixo `database/` |
| `transparencia-total-restore` | `readFiles` | mesmo bucket e prefixo `database/` |

A leitura no perfil de backup permite confirmar o objeto enviado; as capacidades de retenção
permitem aplicar e verificar Object Lock em modo `COMPLIANCE`. Nenhuma chave pode ter `deleteFiles`,
`bypassGovernance`, `writeBuckets`, administração de chaves, ciclo de vida, replicação ou permissões
de conta. A workflow autoriza a chave na API B2 v4 antes de ler produção ou descarregar objetos e
falha se encontrar uma capacidade em falta ou a mais, outro bucket, outro prefixo ou um endpoint
fora do destino EU configurado.

A criação destas chaves exige uma credencial de aprovisionamento com `writeKeys`, que por definição
tem alcance administrativo. Use-a apenas nesta operação, limpe o cache indicado e revogue-a ou
regenere-a depois. A Backblaze documenta as
[Application Keys e respetivas limitações](https://www.backblaze.com/docs/en/cloud-storage-application-keys),
o [mapeamento de capacidades para operações S3](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys)
e a [criação granular pela B2 CLI](https://b2-command-line-tool.readthedocs.io/en/v4.4.1/subcommands/key_create.html).

## 3. Criar a identidade `age` fora do repositório

Num computador controlado, depois de instalar a ferramenta oficial `age`, execute:

```text
age-keygen -o transparencia-total-backup-age.key
age-keygen -y transparencia-total-backup-age.key
```

O segundo comando mostra o destinatário público iniciado por `age1`. Pode ser guardado como
variável do GitHub. O ficheiro `transparencia-total-backup-age.key`, iniciado por
`AGE-SECRET-KEY-`, permite decifrar todas as cópias e:

- não entra no repositório;
- não é enviado para o B2;
- não fica permanentemente no GitHub;
- deve ter uma cópia num gestor de segredos e outra cópia cifrada num suporte offline separado;
- só é colocado temporariamente no environment `recovery` para um ensaio autorizado, sendo removido
  depois da execução.

Sem esta chave privada, a perda é irrecuperável. Guardar apenas o projeto no computador não a
substitui e também não recupera os dados históricos da base de produção.

## 4. Configurar o GitHub sem expor valores

Faça esta configuração diretamente em **Settings → Secrets and variables → Actions**. Não cole os
valores numa issue, PR, log, mensagem ou ficheiro `.env` versionado.

Crie como **Repository variables** (não são segredos):

| Nome | Valor |
| --- | --- |
| `B2_BUCKET_NAME` | nome exato do bucket privado |
| `B2_S3_ENDPOINT` | endpoint completo começado por `https://s3.eu-central-` |
| `B2_S3_REGION` | segunda parte do endpoint, por exemplo `eu-central-003` |
| `BACKUP_AGE_RECIPIENT` | chave pública iniciada por `age1` |

No environment existente **production**, crie estes **Environment secrets**:

| Nome | Valor |
| --- | --- |
| `B2_BACKUP_KEY_ID` | Key ID da chave de backup limitada |
| `B2_BACKUP_APPLICATION_KEY` | segredo da chave de backup limitada |

`PRODUCTION_DATABASE_URL` já é usado pelas operações de produção e não deve ser copiado para o
environment de recuperação.

Crie um environment **recovery**, de preferência com aprovação obrigatória, e adicione:

| Nome | Valor |
| --- | --- |
| `B2_RESTORE_KEY_ID` | Key ID da chave só de leitura |
| `B2_RESTORE_APPLICATION_KEY` | segredo da chave só de leitura |
| `BACKUP_AGE_IDENTITY` | conteúdo da chave privada `age`, apenas durante o ensaio |

A workflow de restauro não referencia `PRODUCTION_DATABASE_URL`; o destino está fixado em
`localhost` dentro do runner. Depois de cada ensaio, elimine `BACKUP_AGE_IDENTITY` do environment
`recovery`. Mantenha a identidade principal fora do GitHub.

## 5. Executar o primeiro backup

Depois de a branch ser fundida e as variáveis estarem configuradas:

1. abra **Actions → Database backup to Backblaze B2 EU**;
2. escolha **Run workflow**;
3. confirme que todos os passos passaram;
4. guarde o URL da execução, a chave do objeto, o SHA-256 cifrado, o tamanho, o SHA-256 do manifesto
   e a data final do Object Lock apresentados no resumo;
5. confirme na consola B2 que existem o `.dump.age` e o `.manifest.json` sob `database/daily/`.

Não transfira nem publique o dump através de GitHub Artifacts. A workflow diária nunca o faz.

Quando a primeira execução passar, a mesma workflow corre diariamente às **05:17 UTC**, depois da
recolha parlamentar agendada. Uma falha aparece nas GitHub Actions e deve ser investigada no próprio
dia; uma execução anterior válida não torna a falha nova invisível.

## 6. Executar o primeiro restauro

1. Adicione temporariamente `BACKUP_AGE_IDENTITY` ao environment `recovery`.
2. Abra **Actions → Isolated database restore drill**.
3. Introduza a chave exata do objeto `.dump.age`, o SHA-256 cifrado e o SHA-256 do ficheiro de
   manifesto indicados no resumo do backup. Estes dois hashes são a prova fora do B2 contra a
   substituição de uma versão por outra.
4. Escreva `RESTAURO` na confirmação e execute.
5. Confirme no resumo:

   - resultado `PASS` ou, para uma cópia antiga, `PASS_WITH_OPERATIONAL_WARNING`;
   - produção usada como destino: `não`;
   - SHA-256 da atestação;
   - RPO e RTO medidos;
   - ligação para o artefacto que contém apenas a atestação.

6. Elimine imediatamente `BACKUP_AGE_IDENTITY` do environment `recovery`.
7. Atualize `docs/V4_TO_V5_RELEASE_GATE.md` com o URL da execução, objeto, hashes, RPO e RTO. Só
   essa alteração transforma o gate em `PASS`.

Datas antigas podem tornar `check_v4_operational_status` em `ATTENTION_REQUIRED`. A workflow conserva
esse resultado como aviso e nunca altera datas para fingir atualidade. Incompatibilidade de hash,
contagens, migrações ou arquivo falha o ensaio.

## Cadência e responsabilidade

- cópia: diária, 05:17 UTC;
- imutabilidade: pelo menos 30 dias em modo Compliance;
- retenção operacional: cerca de 46 dias pela regra 45 + 1;
- ensaio: na ativação, depois trimestralmente e sempre após alteração relevante de PostgreSQL,
  esquema, cifragem ou fornecedor;
- cópia adicional: mensal, cifrada, num suporte offline separado;
- falhas: responsabilidade do mantenedor do repositório, através dos alertas e histórico GitHub
  Actions;
- RPO/RTO: só os valores observados no ensaio podem ser publicados.

Com o tamanho atual, é provável que a retenção fique dentro da franquia inicial do B2, mas o custo
deve ser verificado nos objetos realmente enviados e na
[tabela de preços oficial](https://www.backblaze.com/cloud-storage/transaction-pricing). Não se fixa
no projeto uma promessa de custo futuro.

## Privacidade e resposta a incidentes

A cópia contém os dados privados necessários para reconstruir produção, incluindo staging,
revisões, eventos de auditoria, direitos de resposta e bytes oficiais. Apesar da cifragem do lado do
cliente, o bucket deve continuar privado, com MFA na conta, acesso mínimo, contrato do fornecedor e
registo de acessos revistos no contexto da AIPD. Esta configuração técnica não constitui parecer
jurídico.

Se uma chave B2 for exposta, revogue-a, crie outra limitada e volte a executar o backup. Se a chave
privada `age` for exposta, crie uma nova identidade, altere `BACKUP_AGE_RECIPIENT` e preserve a chave
antiga apenas no cofre necessário para restaurar as cópias ainda retidas. Nunca elimine prova ou
histórico para ocultar o incidente.
