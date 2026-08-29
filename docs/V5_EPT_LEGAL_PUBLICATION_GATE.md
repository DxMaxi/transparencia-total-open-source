# V5.47 — porta jurídica e publicação específica EPT

## Resultado

A V5.47 acrescenta ao circuito privado da V5.46 uma porta específica para ligar e publicar
**metadados mínimos** de um registo público de interesses. A porta é fail-closed: sem processo
editorial aprovado, prova oficial arquivada, identidade inequívoca, avaliação jurídica humana
independente válida e decisão de um administrador com MFA, não existe publicação.

Esta implementação não conclui que uma declaração concreta possa ser publicada e não constitui
aconselhamento jurídico. Regista e verifica a integridade de uma avaliação externa já realizada;
o sistema não gera, resume nem substitui o parecer.

## Três provas independentes

### 1. Fonte individual EPT

A observação continua vinculada ao documento individual da Entidade para a Transparência por:

- URL HTTPS oficial individual;
- identificador oficial exato da declaração;
- data de recolha;
- SHA-256 do documento;
- atestação do original no arquivo privado;
- SHA-256 canónico da observação normalizada.

O portal institucional geral continua a ser apenas uma porta de pesquisa e nunca prova uma
declaração individual.

### 2. Identidade oficial exata

A ligação a `people` só pode ser criada quando todos os elementos seguintes coincidem:

- o identificador introduzido pelo administrador produz exatamente o HMAC já guardado na
  observação, usando o pepper privado;
- `person_id` e `people.source_id` correspondem ao identificador oficial esperado;
- existe uma segunda fonte oficial HTTPS, diferente da declaração EPT;
- essa segunda fonte tem arquivo atestado e uma revisão positiva da pessoa ligada à mesma fonte;
- o administrador confirma que não usou nome, semelhança ou fuzzy matching.

O valor original do identificador é recebido como segredo, usado apenas para calcular o HMAC e
nunca é escrito em tabelas, auditorias, respostas ou logs da aplicação.

### 3. Avaliação jurídica humana independente

O sistema conserva apenas um registo privado e append-only da avaliação:

- âmbito fixo `PUBLIC_INTEREST_METADATA_ONLY`;
- conclusão humana fechada;
- SHA-256, tipo e tamanho do documento;
- referência para o objeto cifrado no arquivo privado;
- referências pseudonimizadas do avaliador, qualificação e controlo de conflitos;
- data da avaliação e validade, quando definida;
- administrador que registou a prova.

O conteúdo do parecer não integra a projeção pública. Uma avaliação posterior que não permita a
publicação ou tenha expirado bloqueia o gate, mesmo que exista uma avaliação permissiva anterior.

## Publicação transacional

O preview é reconstruído no servidor e contém hashes de confirmação para o processo, versão,
fonte, observação, identidade, avaliação jurídica e efeito público. A publicação volta a validar
todos esses elementos dentro da mesma transação e só então acrescenta:

1. `AssetDeclarationMetadata`, sem notas nem conteúdo patrimonial;
2. `DataPublicationReview` positiva e ligada à fonte;
3. `AuditEvent` com as provas e sem identificadores protegidos;
4. decisão editorial `PUBLISH`;
5. `EditorialPublicationEvent` com hash próprio.

A projeção pública contém apenas tipo, data ou período disponibilizados pela fonte e a respetiva
proveniência. Rendimentos, património, moradas, contactos, conteúdo integral, identificadores
protegidos e o documento jurídico privado ficam sempre excluídos.

## Retirada sem apagamento

A retirada requer novo preview e confirmação explícita de um administrador com MFA. Acrescenta
uma revisão pública negativa, auditoria, decisão `WITHDRAW` e evento de retirada. Não apaga a
declaração, a fonte, a ligação protegida, a avaliação jurídica, a publicação anterior ou qualquer
decisão editorial.

Assim, a consulta ativa deixa de mostrar o registo, mas o histórico auditável permanece. Uma
correção posterior tem de acrescentar nova prova e nova decisão; não pode reescrever o passado.

## Defesa na base de dados

As tabelas `ept_independent_legal_assessments` e `ept_exact_identity_links`:

- são privadas e têm RLS ativa sem políticas de acesso pelo browser;
- revogam privilégios a `PUBLIC`, `anon` e `authenticated`;
- rejeitam `UPDATE` e `DELETE` por trigger;
- usam chaves estrangeiras `RESTRICT` e índices nas relações;
- repetem no PostgreSQL as condições críticas de processo aprovado, administrador ativo, HMAC,
  pessoa exata, segunda fonte oficial, arquivo e revisão positiva da pessoa.

Estas proteções são defesa em profundidade; o backend continua a usar uma ligação privada e a
aplicar autorização `ADMIN` com nível `aal2` em todas as escritas.

## Limite operacional e jurídico

O código não autoriza recolha nem tratamento de declarações reais. Antes de ativar este domínio
em staging ou produção são ainda obrigatórios:

1. avaliação jurídica portuguesa independente para o tratamento concreto e para os prazos de
   retenção;
2. avaliação de impacto e validação pelo responsável de proteção de dados, quando aplicável;
3. arquivo cifrado e política de acesso operacional comprovados;
4. ensaio isolado do esquema e das permissões em staging;
5. conta administrativa individual com MFA e dupla revisão humana do primeiro caso;
6. verificação pública de que só os metadados autorizados ficam acessíveis.

Enquanto qualquer condição faltar, o resultado público correto é `dados indisponíveis`.
