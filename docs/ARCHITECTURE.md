# Arquitetura técnica

## Objetivo do sistema

Transformar documentos oficiais heterogéneos em registos comparáveis sem perder a proveniência,
sem converter ausência de dados em conclusões e sem permitir que um modelo de IA publique factos.

## Limites de confiança

| Zona | Pode fazer | Não pode fazer |
|---|---|---|
| Fonte oficial | Publicar o documento de origem | Garantir que todos os seus dados estão completos |
| Coletor | Descarregar, validar, datar e calcular hash | Inventar campos ausentes ou ultrapassar controlos de acesso |
| Normalizador | Mapear nomes oficiais para um esquema comum | Atribuir uma posição coletiva a uma pessoa |
| IA | Propor linguagem simples a partir do texto fornecido | Determinar mérito político ou cumprimento de promessa |
| Revisor | Aplicar critérios públicos e fundamentar decisão | Alterar a fonte ou apagar o histórico |
| Frontend | Mostrar dados, limites, datas e ligações | Apresentar uma inferência como dado oficial |

## Componentes

### Next.js

O App Router renderiza as páginas públicas. Os componentes interativos limitam-se a navegação,
filtros e formulários explícitos. O manifesto e a infraestrutura de notificações não estão ligados
à interface pública. O frontend não conhece chaves privadas nem acede diretamente à base de dados.

### API FastAPI

A API organiza coletores por fonte, aplica validação Pydantic e expõe apenas representações com
origem. O cliente HTTP impõe HTTPS, uma lista de anfitriões oficiais, limite de tamanho, timeout,
rate limit e revalidação do URL após redirecionamentos.

### PostgreSQL e Prisma

`SourceDocument` é o centro da proveniência. Entidades derivadas referenciam o documento que as
sustenta. `AuditEvent`, `PromiseReview` e `AiSummary` registam decisões posteriores. Prisma gere
migrações do frontend/operador; FastAPI usa `asyncpg` nos caminhos operacionais de alto volume.

Na V2, `InterestEntity` fornece uma identidade comum a pessoa e organização. `PublicContract` e
`PublicContractParty` preservam o contrato e os papéis; `ContractMatchReview` guarda apenas
candidatos privados. `InterestRelationship` requer fonte para cada aresta. Notícias, processos,
comparações, regras de impacto, alertas e direitos de resposta têm estados separados de verificação
e publicação.

Na V3, `ParliamentaryMembershipSnapshot` preserva a pertença observada numa fotografia oficial sem
a confundir com a data jurídica de início de um `Mandate`. Os coletores persistem snapshots e
abrem/fecham `SyncRun`; a promoção humana cria `DataPublicationReview` e `AuditEvent`. A API de
leitura usa projeções SQL próprias e não consulta staging, correspondências pendentes ou IA por
rever. O frontend mostra separadamente `LIVE`, `EMPTY` e `UNAVAILABLE`.

Identificadores pessoais usados na deduplicação ficam em `ProtectedIdentifierDigest` como HMAC; o
valor original não pertence ao esquema publicável. Restrições SQL verificam sujeitos exclusivos,
arestas não reflexivas, montantes não negativos, limites das métricas e hashes válidos.

### Processamento assíncrono

Em desenvolvimento, scripts CLI podem ser executados manualmente. Em produção, use jobs
idempotentes:

1. descobrir catálogo;
2. descarregar documento;
3. calcular hash e guardar original imutável;
4. normalizar para tabelas de staging;
5. comparar contagens e campos obrigatórios;
6. promover a versão;
7. criar alertas apenas após promoção.

Cada execução abre um `SyncRun`. Falha parcial conserva avisos e não substitui a última versão
publicada. Na V3 isto já está implementado para deputados, votações e contratos BASE.

## Contrato de proveniência

Todo o dado publicável deve permitir reconstruir:

- editor oficial e tipo de documento;
- URL exato e identificador oficial, quando existe;
- instante de recolha em UTC;
- hash SHA-256 do conteúdo recebido;
- versão do parser;
- versão e decisão de revisão, quando aplicável.

URLs não são prova de imutabilidade. O armazenamento durável deve manter o original com uma chave
de conteúdo e política WORM ou versionamento equivalente.

## Fluxos críticos

### Voto nominal

Um `VoteRecord` recebe `actorType=PERSON` apenas quando o dataset contém identificador explícito da
pessoa. Texto livre sem ID permanece `UNKNOWN`; posições por grupo usam `PARTY`. A métrica de um
perfil conta apenas `PERSON`.

### Perfil político

Uma fotografia de pertença indica apenas “observado em”. Um período de mandato exige datas
oficiais e revisão `MANDATE` própria. Presenças dependem simultaneamente da publicação da fotografia
de atividade e do mandato individual revisto. Iniciativas permanecem indisponíveis enquanto a
normalização não fornecer uma relação de autoria por identificador oficial. A ligação geral ao
portal da Entidade para a Transparência é uma porta de pesquisa, não prova individual.

### Estado de promessa

A ingestão liga a frase e página do programa a evidência oficial. Um revisor propõe estado e
justificação; outro aprova ou devolve. A alteração cria `PromiseReview` e `AuditEvent`. O frontend
mostra o fundamento atual e o histórico.

### Resumo de diploma

O texto DRE é preservado, segmentado e enviado ao fornecedor configurado. A saída estruturada é
guardada como `PENDING`, nunca no campo editorial final. Um revisor confirma âncoras, datas e
omissões antes de aprovar.

### Contrato e relação de interesse

O recurso anual BASE é descarregado para staging, validado contra limites de tamanho e expansão ZIP
e convertido para um contrato canónico. O matcher exato gera `ContractMatchReview=PENDING_REVIEW`.
Um revisor confirma identidade, papel, datas e fonte da associação; outro controlo promove a aresta
para `InterestRelationship`. A API pública nunca consulta candidatos.

### Direito de resposta

O POST cria um texto anexado ao registo alvo, timestamp UTC, hash do texto e recibo de auditoria.
Não altera o hash do alvo. Verificação de identidade e decisão de publicação ocorrem depois, com
novo evento. Respostas publicadas aparecem também na exportação própria.

### Open Data

Consultas enumeradas exportam apenas registos publicados/verificados. O servidor acrescenta versão
do esquema, data, paginação e política de redação; contactos, NIF individual, perfis do cidadão,
candidatos e notas internas não fazem parte das projeções SQL.

## Escala e disponibilidade

- CDN para páginas e ativos públicos.
- API sem estado, escalável horizontalmente.
- PostgreSQL com recuperação adequada ao risco e ao plano contratado; a configuração gratuita
  atual não é descrita como tendo backup ou point-in-time recovery garantido.
- Object storage versionado externo quando a escala exceder o arquivo PostgreSQL atual.
- Redis/fila para jobs e rate limit distribuído, quando houver mais de uma instância.
- Observabilidade sem conteúdo sensível: latência, contagens, hash, código do job e falhas.

## Segurança

- SSRF mitigado por allowlist e revalidação de redirecionamento.
- Endpoints de escrita sensíveis protegidos por chave administrativa; em produção,
  substituir por OIDC, RBAC e rotação.
- Segredos apenas em variáveis do backend.
- CORS enumerado, sem cookies cross-origin.
- Cabeçalhos CSP mínimos bloqueiam objetos, `base-uri` externa e enquadramento; qualquer política
  mais restrita deve ser validada contra a hidratação do Next.js antes de produção.
- Sanitizar ou converter documentos oficiais antes de renderizar HTML; o frontend recebe texto ou
  campos estruturados, não HTML arbitrário.
