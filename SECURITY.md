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
- Subscrições push guardam apenas os filtros regionais escolhidos e devem poder ser eliminadas.

Versões suportadas: apenas a versão publicada mais recente.
