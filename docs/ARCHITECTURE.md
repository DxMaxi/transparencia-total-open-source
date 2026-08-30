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
filtros e formulários explícitos. O manifesto não regista automaticamente o service worker. O modo
offline e os alertas têm escolhas separadas; pedir alertas não ativa a cache pública, e nenhuma
permissão é pedida sem consentimento. O frontend conhece apenas a chave VAPID pública, nunca a chave
privada, e não acede diretamente à base de dados.
As leituras seguem a política de timeout, cache e observabilidade sem dados pessoais descrita em
[PUBLIC_API_RESILIENCE.md](PUBLIC_API_RESILIENCE.md), preservando indisponibilidade explícita.

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
perfil conta apenas `PERSON` quando o `actor_source_id` preservado coincide exatamente com
`people.source_id`. Corrigir o parser cria uma nova fotografia; não atualiza a anterior.

### Perfil político

Uma fotografia de pertença indica apenas “observado em”. Um período de mandato exige datas
oficiais e revisão `MANDATE` própria. Presenças dependem simultaneamente da publicação da fotografia
de atividade e do mandato individual revisto. Iniciativas permanecem indisponíveis enquanto a
normalização não fornecer uma relação de autoria por identificador oficial. A ligação geral ao
portal da Entidade para a Transparência é uma porta de pesquisa, não prova individual.

Uma observação individual EPT permanece privada até cumprir a porta V5.47: processo aprovado,
HMAC coincidente, segunda fonte oficial arquivada ligada ao identificador oficial da pessoa,
avaliação jurídica humana independente registada e decisão de `ADMIN` com MFA. A base de dados
conserva ligação e avaliação em tabelas privadas append-only. A publicação acrescenta somente
metadados mínimos e a retirada acrescenta uma nova decisão; nenhuma das operações apaga prova ou
histórico. O sistema verifica estes registos, mas não emite parecer jurídico.

### Estado de promessa

A ingestão V5.48 fixa o PDF oficial por URL, data, tamanho, páginas e SHA-256 e extrai apenas itens
explicitamente enumerados. Cada item conserva bloco, hierarquia, intervalo de páginas e hashes numa
fotografia privada append-only; permanece `PENDING` e não cria `Promise` nem `PromiseReview`.

Uma fase editorial posterior consolida os candidatos segundo critérios públicos e liga separadamente
diploma, orçamento, regulamentação, execução e resultado material. Só depois um revisor pode propor
estado e justificação e outra decisão pode publicar. A alteração acrescenta `PromiseReview` e
`AuditEvent`; o frontend mostra o fundamento atual e o histórico. Ausência de prova nunca equivale
a incumprimento.

### Resumo de diploma

O texto DRE é preservado, segmentado e enviado ao fornecedor configurado. A saída estruturada é
guardada como `PENDING`, nunca no campo editorial final. Um revisor confirma âncoras, datas e
omissões antes de aprovar.

### Contrato e relação de interesse

Antes do recurso anual, a V5.49 arquiva e valida o catálogo oficial do dados.gov.pt. A fotografia
privada conserva um recurso ZIP por ano desde 2012, marca o ano corrente como provisório e recusa
lacunas, duplicados ou mudanças não revistas de dataset, produtor, licença e frequência. Esta etapa
cria zero contratos e zero relações.

O recurso anual BASE é descarregado para staging, validado contra limites de tamanho e expansão ZIP
e convertido para snapshots canónicos append-only. Na V5.50, a prova de um registo específico de
ano encerrado e de um lote normalizado coerente pode criar apenas um
`EditorialCase=PUBLIC_CONTRACT/PENDING`; não alega cobertura integral do ZIP e não cria
`PublicContract`, organização, correspondência ou aresta. Designações de partes são texto da
fonte, não identidade, e os HMAC não saem do staging. Uma etapa posterior terá de provar cada organização por fonte e identificador
oficiais próprios antes de propor qualquer `ContractMatchReview`. A API pública exige o evento
específico de publicação mais recente e nunca consulta candidatos.

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
