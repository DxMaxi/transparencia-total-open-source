# V5.16 — endurecimento do candidato de release

## Objetivo

A V5.16 fecha riscos técnicos concretos identificados na auditoria de 2026-08-15 sem alterar
dados cívicos, executar migrações ou promover conteúdo. Esta etapa reforça as escritas públicas,
o consentimento dos alertas, a cache pública, a acessibilidade e a verificação em navegador real.

## Escritas públicas e antiabuso

As rotas de subscrição push, direito de resposta e envio administrativo de alertas têm limites
explícitos por origem e por processo:

- subscrição ou remoção push: 20 pedidos por hora;
- direito de resposta: 5 pedidos por hora;
- difusão administrativa: 30 pedidos por hora.

O identificador de origem é transformado com SHA-256 e um sal efémero aleatório. O endereço de
origem não é persistido nem registado em claro. Uma recusa devolve HTTP 429 e `Retry-After`, sem
detalhes internos.

Este controlo é uma proteção mínima por instância. Se o backend passar a executar mais do que uma
instância, o gate de produção exige adicionalmente um limitador partilhado na plataforma ou num
serviço próprio. O código não apresenta o limite local como proteção distribuída.

As indisponibilidades PostgreSQL produzem respostas genéricas e não consomem a quota. Falhas do
fornecedor push não colocam endpoints, chaves ou mensagens de exceção nos logs.

Endpoints de subscrição têm HTTPS obrigatório e ficam limitados aos serviços Web Push suportados
dos navegadores. URLs arbitrárias, IPs e hosts com sufixos semelhantes são recusados antes da
persistência. As chaves `p256dh` e `auth` são descodificadas e validadas nos comprimentos
criptográficos esperados, evitando que uma subscrição malformada interrompa uma difusão futura.

## Alertas com consentimento e publicação comprovada

Visitar o site não pede autorização de notificações. O pedido do navegador ocorre apenas depois de
o cidadão:

1. escolher uma região;
2. assinalar consentimento informado;
3. carregar no botão de ativação.

As preferências podem ser atualizadas. A revogação pede a eliminação exata no backend e desativa a
subscrição no navegador. Se o backend estiver temporariamente indisponível, o navegador deixa na
mesma de receber alertas; a página mantém o endpoint apenas em memória e permite repetir a
eliminação no servidor, apresentando o estado parcial sem o ocultar.

A difusão não aceita título, texto, URL ou território livres. Um administrador só pode indicar o
identificador de um `CitizenAlert`. O backend reconstrói o envio a partir de um registo:

- com estado `PUBLISHED`;
- marcado para revisão humana e com a última revisão `CITIZEN_ALERT` de publicação positiva;
- não expirado;
- ligado a um `SourceDocument` cujo URL e SHA-256 coincidem com uma atestação do arquivo.

Se qualquer condição falhar, nenhum alerta é enviado. O destino é uma rota pública fixa da mesma
origem. Este mecanismo não recolhe geolocalização, não cria perfis de navegação e não transforma a
IA numa fonte.

## PWA, cache e acessibilidade

O service worker usa uma allowlist de páginas, recursos estáticos e tipos de ficha públicos. Rotas
privadas, API, pedidos autenticados, respostas `private`/`no-store` e páginas com parâmetros de
pesquisa ficam fora da runtime cache. Novas rotas não entram automaticamente na cache.

O mesmo worker suporta notificações e modo offline, mas a cache só é criada depois da escolha
“Ativar modo offline”. Consentir alertas, por si só, não precacheia nem interceta páginas. Ao
desativar o modo offline, o registo técnico só é conservado se existir uma subscrição push ativa.

O manifesto e o service worker não atravessam o proxy de autenticação. O alvo do skip-link aceita
foco programático e conserva um indicador visual de teclado.

Os diretórios de diagnóstico Playwright ficam excluídos do Git. Quando o E2E local falha no CI, os
relatórios são conservados por sete dias para diagnóstico.

## Builds e verificação

`npm run build:next` é o build canónico do release e da Vercel. `npm run build` continua reservado
ao adaptador Sites/vinext usado pelo ambiente de preview do projeto. Os ficheiros `.vinext/fonts`
versionados são recursos intencionais desse adaptador; não são tratados como resultado descartável
do build nem removidos automaticamente.

O CI abre o artefacto Next localmente em Chromium e testa rotas, links, 404, viewport móvel,
políticos e atividade parlamentar. O workflow `Public smoke` repete a verificação no domínio
oficial depois de um deployment de produção bem-sucedido.

## Limites que continuam abertos

Esta etapa não prova staging, Supabase, migrações remotas, backup pós-migração, restauro final,
aconselhamento jurídico, cobertura histórica nem a completude das fontes. Esses gates permanecem
visíveis na checklist da V5 e só podem ser fechados com evidência do ambiente correspondente.
