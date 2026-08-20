# Política de resiliência da API pública

Esta política aplica-se apenas às leituras do frontend público. Não altera recolhas, revisões,
publicações nem o histórico editorial.

## Limites e cache

- cada leitura tem um limite máximo de 10 segundos;
- respostas públicas válidas podem ser revalidadas durante 60 segundos;
- não existem novas tentativas automáticas no frontend;
- uma falha nunca é convertida em zero, ausência de atividade ou dado antigo apresentado como
  atual;
- cada módulo mantém o estado explícito `Dados indisponíveis` ou o estado de cobertura aplicável.

A ausência de repetição automática é intencional. As páginas fazem várias leituras em paralelo e
uma repetição indiscriminada duplicaria a carga durante um arranque lento ou incidente. A política
só deverá mudar depois de existirem medições de produção que distingam latência normal, arranque a
frio e indisponibilidade real.

## Observabilidade sem dados pessoais

As falhas são registadas no servidor com o evento `public_api_fetch_failed`. O registo contém
somente:

- caminho do endpoint sem query string;
- categoria controlada (`not_configured`, `timeout`, `abort`, `network`, `http`, `invalid_json` ou
  `unknown`);
- estado HTTP, quando existe;
- duração, limite aplicado e política de repetição.

Não são registados o URL de origem, query strings, payloads, corpos de resposta, mensagens brutas
de exceção, tokens ou cabeçalhos. Esta telemetria serve exclusivamente para operação técnica e não
cria perfis de visitantes.

## Decisão pública perante falhas

Uma resposta não-2xx, timeout, falha de rede ou JSON inválido é tratada como indisponibilidade. O
frontend não inventa conteúdo, não recupera listas antigas como se fossem atuais e não interpreta
a ausência como incumprimento. Quando existir conteúdo editorial estático conhecido, como o
catálogo inicial do Promessómetro, o módulo identifica-o explicitamente como contingência e não
como resposta atual da API.
