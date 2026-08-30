# Fontes e integração

## Matriz atual

| Fonte | Estado técnico | Implementado | Limite conhecido |
|---|---|---|---|
| Assembleia da República | Release candidate | Catálogos, bytes PostgreSQL, deputados, reuniões observadas, iniciativas, votações, snapshots e revisão/publicação fail-closed | Reuniões são as referidas nos eventos de votação, não a agenda completa; nem toda votação é nominal |
| Diário da República | Funcional em staging | Extração por URL ELI, bytes exactos, arquivo atestado e snapshot privado append-only | Sem promoção pública; feed RSS só após confirmação documental |
| Entidade para a Transparência | Funcional em staging privado, com contingência explícita | Índice canónico com bytes exactos; perante falha de rede, timeout ou HTTP 429, apenas o portal oficial alternativo é arquivado como `PARTIAL` | O portal alternativo não equivale ao índice, não recolhe declarações nem autoriza publicação; qualquer tratamento exige revisão jurídica própria |
| Portal BASE / dados.gov.pt | Âmbito V5.49 e porta editorial privada V5.50 preparados; ingestão funcional em staging | Catálogo anual 2012–ano corrente, arquivo, lote append-only e caso `PENDING` por contrato exato sem materialização pública | Operações ainda não executadas em staging; sem promoção pública ou identidade organizacional; API direta de grande volume pode exigir registo e autorização |
| Tribunal de Contas | Colector privado funcional | Índice oficial preservado com URL, data, SHA-256 e recursos deduplicados | Sem publicação nem interpretação de decisões ou culpa |
| Parlamento Europeu | Colector privado funcional | Portal de dados abertos preservado com URL, data, SHA-256 e recursos deduplicados | Sem publicação nem atribuição individual sem voto nominal explícito |
| Portal da Transparência do SNS | Colector privado funcional | Índice oficial preservado com URL, data, SHA-256 e `SyncRun` | Não publica indicadores nem representa cobertura territorial nacional |
| Imprensa | Modelo preparado | RSS, notícia, menção, prova e revisão previstos no esquema | Fora do fecho V4; allowlist editorial necessária antes de produção |

## Regra comum de prova bruta V4

Os mesmos bytes oficiais podem ser interpretados novamente por uma versão posterior do parser.
Nesse caso é acrescentado um novo `official_index_snapshot`, identificado pela versão do parser;
o snapshot anterior e os seus recursos permanecem imutáveis. A repetição com os mesmos bytes e a
mesma versão só é idempotente se todos os recursos coincidirem, não apenas a contagem.

Os colectores do Parlamento, BASE, DRE, Entidade para a Transparência, Tribunal de Contas,
Parlamento Europeu e Portal da Transparência do SNS calculam o SHA-256 sobre os bytes exactos da resposta HTTP e
transportam-nos apenas num `PrivateRawDocument`, excluído de serialização.

Nos fluxos persistentes já activados, o documento só pode ser referenciado depois de o objecto
content-addressed ser escrito, verificado e atestado com o mesmo URL efectivo e hash. A operação
controlada `refresh-official-indexes` preserva os seis índices oficiais apenas em staging privado;
não cria qualquer projecção pública. Uma tentativa que falhe antes de obter bytes cria igualmente
um `SyncRun=FAILED`, para que um sucesso antigo nunca esconda a indisponibilidade mais recente.

Ausência de objecto, atestado, acesso ao arquivo ou estrutura suficiente significa “dados
indisponíveis”; nunca é interpretada como ausência de factos na fonte. Nenhuma recolha constitui
revisão editorial ou autorização de publicação.

## Assembleia da República

Catálogo: <https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx>

O portal fornece XML e JSON e organiza ficheiros por catálogo e legislatura. O colector descobre o
recurso oficial, valida o anfitrião após redireccionamentos e calcula o hash antes da normalização.
O pipeline rejeita fotografias sem reuniões observáveis, iniciativas ou votações e impõe um limite
de dimensão. A publicação exige arquivo atestado, SHA-256 da fonte, SHA-256 normalizado, quatro
contagens e revisão humana. Uma nova recolha não altera a fotografia anterior.

Posições de grupos parlamentares nunca são atribuídas automaticamente a deputados. Quando a fonte
não contém detalhe nominal estruturado, o ator permanece `UNKNOWN`. Uma votação associada a mais
de uma iniciativa não é ligada arbitrariamente a uma delas. As reuniões expostas são observações
dos campos `reuniao`, `tipoReuniao` e `data` da votação, não uma afirmação de agenda completa.

## Diário da República

Portal: <https://diariodarepublica.pt/>

O colector aceita apenas URLs DRE autorizados. O `content_sha256` identifica os bytes brutos e o
`normalised_text_sha256` identifica separadamente o texto extraído. Em staging, os bytes são
arquivados e atestados antes do snapshot privado append-only. O snapshot não cria leis públicas,
alertas ou registos de revisão, e o inspector nunca devolve o texto extraído.

Defina `DRE_RSS_URL` apenas quando a equipa confirmar e documentar o feed oficial a usar.

## Entidade para a Transparência

Índice canónico: <https://www.tribunalconstitucional.pt/tc/ept/>

Portal oficial alternativo ligado pelo índice canónico:
<https://entidadetransparencia.pt/>.

O colector indexa apenas ligações publicamente acessíveis e conserva os bytes exactos. O schema de
staging guarda somente título, categoria e URL, com estado fixo `REQUIRES_LEGAL_REVIEW` e sem
projecção pública. A operação controlada arquiva e atesta o índice, mas não promove recursos nem
autoriza qualquer tratamento de declarações.

Se o índice canónico falhar por erro de rede, timeout ou limitação HTTP 429 durante a operação
controlada, o colector pode preservar somente os bytes do portal oficial alternativo. Essa recolha
fica obrigatoriamente marcada `PARTIAL`, com aviso explícito, URL efectiva, data, SHA-256 e evento
de auditoria; mantém
`publishable=False` e não cria recursos públicos. Não existe equivalência inferida entre o portal e
o índice, nem entre a disponibilidade do portal e a existência, ausência ou conteúdo de qualquer
declaração. Outros erros HTTP, uma resposta não oficial ou a falha do próprio portal
continuam a produzir `SyncRun=FAILED`.

Não são recolhidos conteúdos de declarações, identificadores pessoais, respostas a formulários ou
áreas autenticadas. A existência ou ausência de uma ligação nunca é convertida em alegação sobre
cumprimento, incumprimento ou conteúdo de uma declaração.

Na V5.6, o perfil público distingue esta ligação geral de um eventual metadado individual. O
índice atual não cria esse metadado. Um registo futuro em `AssetDeclarationMetadata` só poderá ser
projetado depois de recolha separada e autorizada, original EPT atestado, revisão jurídica
confirmada e última decisão editorial positiva ligada ao mesmo documento. Sem toda essa cadeia, a
área permanece como `Dados indisponíveis` e o portal surge apenas como pesquisa externa.

## Tribunal de Contas, Parlamento Europeu e Portal da Transparência do SNS

`OfficialIndexCollector` fornece o contrato mínimo comum:

1. exige HTTPS e anfitrião na allowlist;
2. valida novamente o URL efectivo após redireccionamentos;
3. calcula SHA-256 sobre os bytes exactos;
4. conserva os bytes num `PrivateRawDocument`;
5. indexa apenas ligações para anfitriões oficiais permitidos;
6. deduplica por URL;
7. devolve sempre `publishable=False`.

O colector isolado não publica nem persiste índices. A operação V4 que o invoca arquiva os bytes e
os recursos apenas em staging privado, com `publishable=False`. No Tribunal de Contas não interpreta
linguagem judicial, culpa, sujeitos ou estado processual. No Parlamento Europeu não atribui posições
de grupo a pessoas. No Portal da Transparência do SNS, o índice nacional é apenas uma origem inicial
e não equivale a cobertura territorial nem a indicadores de saúde publicados pela plataforma.

Portal SNS usado pelo colector:
<https://transparencia.sns.gov.pt/pages/home-page/>.

## Portal BASE e dados.gov.pt

Catálogo oficial: <https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/>

A V5.49 separa a prova do catálogo da ingestão dos contratos. O manifesto exige o dataset e produtor
oficiais, licença `other-pd`, frequência semanal e exatamente um ZIP por ano desde 2012. Na
fotografia de 2026, 2012–2025 são períodos históricos e 2026 é provisório. “Histórico” não quer
dizer definitivo: uma correção oficial posterior cria outra fotografia e preserva a anterior.
Consulte [V5.49 — âmbito temporal privado do Portal BASE](V5_BASE_TEMPORAL_SCOPE.md).

A V5.50 usa esse catálogo como condição da proposta editorial: um registo específico de ano
encerrado, com URL anual coincidente, arquivo e lote normalizado coerente, pode criar um caso
privado `PENDING`. As limitações da recolha ficam visíveis e não se alega cobertura integral do
ZIP. O endpoint não devolve HMAC, não associa partes por nome e não cria contratos ou relações
públicas. Consulte [V5.50 — porta editorial privada dos contratos BASE](V5_BASE_CONTRACT_EDITORIAL.md).

O colector aceita JSON, XML e ZIP com limites de download, tamanho descomprimido e taxa de compressão.
Uma operação explicitamente confirmada em staging arquiva e atesta os bytes antes de carregar um
lote append-only; não cria contratos públicos, entidades ou publicação.

Identificadores fiscais são convertidos imediatamente para HMAC-SHA-256 com pepper e nunca entram
em claro na colecção pública. Sem pepper configurado, não são persistidas correspondências por
identificador. Texto livre com sequências fiscais suspeitas entra em quarentena privada.

Extrações de grande volume através da API directa do Portal BASE devem seguir o procedimento oficial
do IMPIC. A existência de dados públicos não autoriza contornar autenticação, limites ou requisitos
de reutilização.

## Novas fontes locais

Antes de integrar um município, SNS ou portal sectorial é obrigatório confirmar organismo, licença,
identificador estável, frequência, fixture de parser e mapeamento territorial por código oficial.
O radar nunca deve apresentar “Portugal” quando só alguns territórios têm cobertura.
