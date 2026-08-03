# Arquitetura técnica

## Objetivo do sistema

Transformar documentos oficiais heterogéneos em registos comparáveis sem perder a proveniência,
sem converter ausência de dados em conclusões e sem permitir que um modelo de IA publique factos.

## Limites de confiança

| Zona | Pode fazer | Não pode fazer |
|---|---|---|
| Fonte oficial | Publicar o documento de origem | Garantir que todos os seus dados estão completos |
| Coletor | Descarregar, validar, datar e calcular hash | Inventar campos ausentes ou ultrapassar controlos de acesso |
| Arquivo privado | Conservar e verificar os bytes por SHA-256 | Rever, interpretar ou publicar o documento |
| Normalizador | Mapear nomes oficiais para um esquema comum | Atribuir uma posição coletiva a uma pessoa |
| IA | Propor linguagem simples a partir do texto fornecido | Determinar mérito político ou cumprimento de promessa |
| Revisor | Aplicar critérios públicos e fundamentar decisão | Alterar a fonte ou apagar o histórico |
| Frontend | Mostrar dados, limites, datas e ligações | Apresentar uma inferência como dado oficial |

## Componentes

### Next.js PWA

O App Router renderiza as páginas públicas. Componentes interativos limitam-se a filtros,
instalação, subscrição push e futura pesquisa. O frontend não conhece chaves privadas nem acede
diretamente à base de dados.

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
rever. O frontend mostra separadamente `LIVE`, `EMPTY`, `UNAVAILABLE` e `DEMO`.

Na V4.1, `SourceArchiveAttestation` liga um `SourceDocument` a um objeto privado
content-addressed. O PostgreSQL valida a igualdade de URL, SHA-256 e chave, rejeita alterações ou
eliminação da atestação e protege o URL/hash de uma fonte já atestada. A existência da atestação é
uma porta adicional e fail-closed nas projeções públicas; nunca substitui a última revisão humana
exigida pelo domínio.

### Arquivo privado de originais

`PrivateRawDocument` transporta os bytes apenas dentro do processo de ingestão e exclui-os de
serialização e representação. O backend local escreve com chave
`sha256/<prefixo>/<sha256 completo>`, sem operações de substituição, leitura de conteúdo ou
eliminação. Um recibo validado é a única entrada aceite pelo repositório para criar a atestação.

O backend de ficheiros serve desenvolvimento, testes e staging controlado. O adaptador de produção
para object storage privado, versionado ou WORM, continua por implementar; por isso a V4.1 não deve
ser ativada em produção apenas com disco local ou efémero.

Identificadores pessoais usados na deduplicação ficam em `ProtectedIdentifierDigest` como HMAC; o
valor original não pertence ao esquema publicável. Restrições SQL verificam sujeitos exclusivos,
arestas não reflexivas, montantes não negativos, limites das métricas e hashes válidos.

### Processamento assíncrono

No protótipo, scripts CLI podem ser executados por cron. Em produção, use uma fila com jobs
idempotentes:

1. descobrir catálogo;
2. descarregar documento;
3. calcular o hash sobre os bytes exatos e guardar o original imutável;
4. verificar o objeto e acrescentar a atestação coerente;
5. normalizar para tabelas de staging;
6. comparar contagens e campos obrigatórios;
7. promover a versão após revisão humana;
8. criar alertas apenas após promoção.

Cada execução persistente abre um `SyncRun`. Falha parcial conserva avisos e não substitui a última
versão publicada. Na V3 isto está implementado para as fontes parlamentares. O coletor BASE produz
apenas um artefacto privado e a sua persistência permanece bloqueada até existir carga em lote
append-only e atestação explícita de staging.

## Contrato de proveniência

Todo o dado publicável deve permitir reconstruir:

- editor oficial e tipo de documento;
- URL exato e identificador oficial, quando existe;
- instante de recolha em UTC;
- hash SHA-256 do conteúdo recebido;
- chave e atestação do original privado, coerentes com esse URL e hash;
- versão do parser;
- versão e decisão de revisão, quando aplicável.

URLs não são prova de imutabilidade. O armazenamento durável deve manter o original com uma chave
de conteúdo e política WORM ou versionamento equivalente.

## Fluxos críticos

### Voto nominal

Um `VoteRecord` recebe `actorType=PERSON` apenas quando o dataset contém identificador explícito da
pessoa. Texto livre sem ID permanece `UNKNOWN`; posições por grupo usam `PARTY`. A métrica de um
perfil conta apenas `PERSON`.

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
- PostgreSQL com backups e point-in-time recovery.
- Arquivo content-addressed local apenas para desenvolvimento/teste/staging; object storage
  privado e versionado continua obrigatório antes de produção.
- Redis/fila para jobs e rate limit distribuído, quando houver mais de uma instância.
- Observabilidade sem conteúdo sensível: latência, contagens, hash, código do job e falhas.

## Segurança

- SSRF mitigado por allowlist e revalidação de redirecionamento.
- Endpoints de escrita sensíveis protegidos por chave administrativa no protótipo; em produção,
  substituir por OIDC, RBAC e rotação.
- Segredos apenas em variáveis do backend.
- CORS enumerado, sem cookies cross-origin.
- CSP deve ser adicionada quando os domínios finais de imagem, métricas e API estiverem definidos.
- Sanitizar ou converter documentos oficiais antes de renderizar HTML; o frontend recebe texto ou
  campos estruturados, não HTML arbitrário.
