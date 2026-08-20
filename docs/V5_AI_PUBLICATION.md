# V5.15 — publicação responsável de explicações DRE com IA

## Resultado

A V5.15 acrescenta a projeção pública que faltava ao circuito responsável de IA. Uma proposta
`PENDING` continua privada; uma aprovação humana continua privada; e nenhum conteúdo é publicado
automaticamente. A publicação exige uma nova ação de um `ADMIN` autenticado com MFA (`aal2`).

O conteúdo público é identificado, sem ambiguidade, como **“Explicação gerada por IA — revista por
humano”**. Não é uma notícia, uma fonte, uma previsão política, uma opinião editorial, uma
classificação ideológica ou uma recomendação de partido ou sentido de voto.

## Prova exigida antes de publicar

A API reconstrói a projeção no servidor e bloqueia a operação se alguma prova deixar de coincidir:

- documento oficial do Diário da República e URL HTTPS permitida;
- data de recolha e SHA-256 dos bytes oficiais;
- snapshot de texto e atestação do arquivo content-addressed;
- SHA-256 do texto normalizado;
- versão editorial atual e respetivo SHA-256;
- contrato estruturado `CitizenSummary`;
- âncoras literais presentes no texto ou abstenção explícita;
- fornecedor, modelo, versão e SHA-256 das instruções;
- SHA-256 da entrada e da saída do modelo;
- indicação de não retenção pedida ao fornecedor;
- revisão humana anterior e confirmação pública separada;
- inexistência de outra explicação ativa para o mesmo documento exato.

Os identificadores internos do processo, da versão, do snapshot e do arquivo não são devolvidos
pela API pública. O identificador público deriva do SHA-256 do documento oficial.

## Transação de publicação

Uma única transação PostgreSQL, protegida por bloqueio por identificador público, acrescenta:

1. uma `DataPublicationReview` positiva para conteúdo oficial não pessoal;
2. um `AuditEvent` append-only com fundamentação pública redigida e referências por hash;
3. uma decisão editorial `PUBLISH` com a fundamentação privada;
4. o estado `PUBLISHED` da versão exata;
5. um `EditorialPublicationEvent` com SHA-256 próprio.

O processo não chama o modelo nesta transação e não grava uma cópia mutável numa tabela de
resumos. A leitura pública volta a calcular a projeção e valida estas cinco peças em modo
fail-closed.

## Retirada e correção

A retirada exige novamente `ADMIN` + MFA, uma categoria fechada, fundamentação privada,
fundamentação pública e confirmação do efeito calculado. A operação acrescenta uma revisão
negativa, um `AuditEvent`, uma decisão `WITHDRAW` e outro evento imutável. A versão publicada e a
prova anterior não são apagadas.

Depois da retirada, a consulta ativa devolve **dados indisponíveis** e o histórico público conserva
a data, a fonte, os hashes, a categoria e o motivo redigido. Uma correção ou nova geração cria uma
nova versão `PENDING`, exige nova revisão e só pode regressar ao público através de nova publicação.

## Verificação

Os testes unitários exercitam hashes, rótulos e falha fechada. O ensaio integral usa apenas uma base
PostgreSQL descartável, sem acesso de escrita a staging ou produção, e cobre aprovação, tentativa
com prova errada e rollback, publicação, leitura pública, retirada, histórico, nova versão e
republicação.
