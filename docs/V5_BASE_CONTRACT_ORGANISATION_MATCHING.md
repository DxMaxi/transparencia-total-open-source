# V5.54 — candidatos privados entre contratos e organizações

Uma igualdade criptográfica exata cria apenas um candidato privado `PENDING_REVIEW`.
A revisão de uma fonte, a igualdade de identificadores e a existência de duas publicações
ativas não provam controlo, benefício, conflito ou irregularidade. Esta operação tem
zero efeito público e não ativa staging por si só.

## Percurso

Em `/admin/revisao/contratos/correspondencias`, um revisor autenticado com MFA indica
o identificador público exato de um contrato. O servidor compara o identificador protegido
da parte com a identidade organizacional publicada a partir da fonte IRN independente.
Nomes servem apenas para leitura. Não existe correspondência aproximada.

Antes de criar, são obrigatórias seis confirmações e uma fundamentação sem identificadores
fiscais ou HMAC. O servidor volta a validar as publicações, arquivos, fontes e hashes;
o PostgreSQL verifica novamente a igualdade, unicidade e prova canónica. A ordem comum
dos bloqueios evita inversão perante publicação e retirada concorrentes.

## Privacidade e histórico

- O identificador fiscal e o HMAC não são devolvidos ao navegador nem copiados para o candidato.
- Não são criados contratos, organizações, partes públicas, revisões legadas, nós, relações
  ou eventos públicos pela criação do candidato.
- Repetições e pedidos concorrentes conservam o mesmo candidato.
- Alteração, eliminação e truncagem do candidato são recusadas na base de dados.
- `PUBLIC`, `anon` e `authenticated` não recebem privilégios; a tabela tem RLS.
- Uma retirada invalida novas propostas e preserva os candidatos anteriores como história privada.

## Verificação e entrega

A migração foi ensaiada num PostgreSQL 17 local descartável, juntamente com as anteriores.
Os testes específicos cobrem pedidos inválidos, privacidade HTTP, concorrência, idempotência,
recusa sem MFA, conta inativa, ausência de igualdade, retirada e imutabilidade.
O resultado global e as operações remotas estão registados em `V5_DELIVERY_2026-09-09.md`.

A V5.55 corresponde ao circuito de decisão humana e eventual ligação factual, com fontes,
tipo, período, retirada e direito de resposta próprios. Esta entrega não publica essa relação.
