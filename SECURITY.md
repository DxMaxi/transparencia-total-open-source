# Política de segurança

## Comunicar uma vulnerabilidade

Não publique detalhes exploráveis numa issue. Envie uma descrição privada aos responsáveis do
repositório através do canal de segurança do GitHub. Inclua impacto, passos mínimos de reprodução
e, se possível, uma correção proposta.

## Âmbito e práticas

- As chaves OpenAI, VAPID, de administração e da base de dados pertencem apenas ao backend.
- URLs fornecidos pelo utilizador passam por uma lista de domínios oficiais para reduzir SSRF.
- Endpoints de sincronização, revisão e envio em massa exigem autenticação administrativa.
- A aplicação não deve guardar filiação, preferências políticas nem localização exata do cidadão.
- O modo offline só é ativado por escolha explícita. O service worker exclui rotas privadas,
  pedidos autenticados e respostas `private`/`no-store`, e nunca apaga caches de outros projetos.
- As subscrições push dependem de configuração operacional e consentimento explícito; guardam
  apenas os filtros necessários e permitem eliminação e revogação. Sem configuração válida,
  a interface apresenta os alertas como indisponíveis.
- Frontend e API enviam cabeçalhos defensivos contra MIME sniffing, framing, origens indevidas e
  acesso a capacidades do navegador.
- Dependabot acompanha dependências npm, Python e GitHub Actions. A proteção de `main` foi
  verificada em setembro de 2026: PR, CI frontend/backend, branch atualizada, histórico linear
  e resolução de conversas, também para administradores; sem force push ou eliminação.
  A disponibilidade e ativação de alertas, code scanning e secret scanning devem ser verificadas
  separadamente; esta proteção de branch não comprova essas capacidades.

## Verificação contínua

O CI valida lint, tipos, testes frontend/backend, build e contratos de segurança. O workflow
`Public smoke` verifica o domínio oficial após um deployment `Production` bem-sucedido,
diariamente e por execução manual. A API é incluída nas execuções diárias e manuais. O
workflow `Official index sync` atualiza apenas os índices operacionais; não publica conteúdo
editorial e não substitui revisão humana.

Versões suportadas: apenas a versão publicada mais recente.
