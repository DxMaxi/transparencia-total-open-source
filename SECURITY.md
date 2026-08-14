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
- A interface pública não ativa subscrições push. Se esta opção vier a ser ativada, deve exigir
  escolha explícita, guardar apenas os filtros necessários e permitir eliminação e revogação.
- Frontend e API enviam cabeçalhos defensivos contra MIME sniffing, framing, origens indevidas e
  acesso a capacidades do navegador.
- Dependabot acompanha dependências npm, Python e GitHub Actions. Alertas, code scanning,
  secret scanning e proteção de `main` devem ser ativados nas definições do repositório quando
  estiverem disponíveis para o respetivo plano.

## Verificação contínua

O CI valida lint, tipos, testes frontend/backend, build e contratos de segurança. O workflow
`Public smoke` verifica o domínio oficial após cada alteração de `main` e diariamente. O
workflow `Official index sync` atualiza apenas os índices operacionais; não publica conteúdo
editorial e não substitui revisão humana.

Versões suportadas: apenas a versão publicada mais recente.
