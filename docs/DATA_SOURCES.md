# Fontes e integração

## Matriz atual

| Fonte | Estado técnico | Implementado | Limite conhecido |
|---|---|---|---|
| Assembleia da República | Funcional | Descoberta de catálogos, JSON, deputados e votações | Estruturas variam por legislatura; nem toda votação é nominal |
| Diário da República | Funcional em staging | Extração por URL ELI, bytes exactos, arquivo atestado e snapshot privado append-only | Sem promoção pública; feed RSS só após confirmação documental |
| Entidade para a Transparência | Funcional em staging, mínimo | Índice público, bytes exactos e staging privado de metadados com revisão jurídica obrigatória | Não recolhe conteúdo de declarações nem contorna formulários ou autenticação |
| Portal BASE / dados.gov.pt | Funcional em staging | Descoberta anual, JSON/XML/ZIP, arquivo, lote append-only e candidatos exactos apenas em ficheiro privado | Sem promoção pública; API directa de grande volume pode exigir registo e autorização |
| Tribunal de Contas | Funcional, mínimo | Índice oficial arquivado, hash dos bytes exactos e ligações oficiais deduplicadas | Sem interpretação de decisões, sujeitos, culpa ou estado processual; não publicável automaticamente |
| Parlamento Europeu | Funcional, mínimo | Índice oficial da API aberta arquivado e ligações oficiais deduplicadas | Sem atribuição de posição individual sem registo nominal explícito |
| Radar local/SNS | Funcional, mínimo | Índice SNS oficial arquivado como ponto inicial de cobertura | Não representa cobertura nacional nem cria factos locais sem conector territorial específico |
| Imprensa | Modelo preparado | RSS, notícia, menção, prova e revisão previstos no esquema | Fora do fecho V4; allowlist editorial necessária antes de produção |

## Regra comum de prova bruta V4

Os colectores do Parlamento, BASE, DRE, Entidade para a Transparência, Tribunal de Contas,
Parlamento Europeu e Radar SNS calculam o SHA-256 sobre os bytes exactos da resposta HTTP e
transportam-nos apenas num `PrivateRawDocument`, excluído de serialização. Uma persistência só pode
referenciar o documento depois de o objecto content-addressed ser escrito e verificado e de existir
uma atestação com o mesmo URL efectivo e hash.

Ausência de objecto, atestado, acesso ao arquivo ou estrutura suficiente significa “dados
indisponíveis”; nunca é interpretada como ausência de factos na fonte. Nenhuma recolha constitui
revisão editorial ou autorização de publicação.

## Assembleia da República

Catálogo: <https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx>

O portal fornece XML e JSON e organiza ficheiros por catálogo e legislatura. Como os URLs podem ser
opacos, `ParlamentoCollector.discover_dataset_url`:

1. descarrega a página temática oficial;
2. localiza a ligação da legislatura pedida;
3. abre a pasta oficial, quando necessário;
4. escolhe um ficheiro JSON;
5. volta a validar o anfitrião após cada redireccionamento;
6. calcula o hash antes da normalização.

Aliases de campo existem para tolerar nomes históricos. O SHA-256 é calculado sobre os bytes
recebidos, antes de descodificar e normalizar o JSON. Na operação persistente, os bytes são
arquivados e verificados antes de o repositório escrever o snapshot em staging. Uma mudança de
estrutura que produza zero registos gera aviso; não promove uma tabela vazia como verdade.

Na fotografia oficial da legislatura XVII, o detalhe das votações identifica sobretudo grupos
parlamentares ou rótulos textuais, não deputados através de um identificador individual estável.
Essas posições permanecem em staging como `UNKNOWN`: uma posição partidária nunca é atribuída a
uma pessoa. Quando a própria fonte não contém detalhe estruturado, a cobertura é apresentada como
“dados indisponíveis”, nunca como zero. A leitura pública exige uma revisão humana positiva e
específica do mesmo documento-fonte.

## Diário da República

Portal: <https://diariodarepublica.pt/>

O colector aceita apenas URLs de anfitriões DRE autorizados. URLs ELI podem ser construídos por tipo,
número e data. O HTML é reduzido a texto após remoção de navegação, scripts, estilos e formulários.
O `content_sha256` identifica o HTML/PDF bruto; `normalised_text_sha256` identifica separadamente o
texto extraído.

Em staging, os bytes são arquivados e atestados antes do snapshot privado append-only. O snapshot
não cria leis públicas, alertas ou registos de revisão, e o inspector nunca devolve o texto extraído.
A promoção pública continua deliberadamente inexistente.

Defina `DRE_RSS_URL` apenas quando a equipa confirmar e documentar o feed oficial a usar.

## Entidade para a Transparência

Portal: <https://www.tribunalconstitucional.pt/tc/ept/>

O conector indexa apenas ligações publicamente acessíveis, conserva bytes exactos e guarda em
staging apenas título, categoria e URL. O estado é sempre `REQUIRES_LEGAL_REVIEW` e `publishable`
permanece falso.

Não são recolhidos conteúdos de declarações, identificadores pessoais, respostas a formulários ou
áreas autenticadas. A existência ou ausência de uma ligação nunca é convertida em alegação sobre
cumprimento, incumprimento ou conteúdo de uma declaração.

## Tribunal de Contas, Parlamento Europeu e Radar SNS

`OfficialIndexCollector` fornece o contrato mínimo comum:

1. exige HTTPS e anfitrião na allowlist;
2. valida novamente o URL efectivo após redireccionamentos;
3. calcula SHA-256 sobre os bytes exactos;
4. conserva os bytes num `PrivateRawDocument`;
5. indexa apenas ligações para anfitriões oficiais permitidos;
6. deduplica por URL;
7. devolve sempre `publishable=False`.

No Tribunal de Contas, o índice não interpreta linguagem judicial, culpa, sujeitos ou estado
processual. No Parlamento Europeu, uma posição de grupo nunca é atribuída a uma pessoa sem voto
nominal explícito. No Radar SNS, o índice nacional é apenas uma origem inicial e não equivale a
cobertura territorial; cada município ou unidade precisa de contrato próprio e matriz pública.

## Novas fontes locais

Antes de integrar um município, SNS ou portal sectorial:

1. confirmar organismo competente e licença/regras de reutilização;
2. preferir API, RSS, CSV ou dados abertos a scraping HTML;
3. adicionar o domínio exacto à allowlist após revisão;
4. definir identificador estável e frequência razoável;
5. criar fixture e contrato de parser;
6. mapear distrito/município por código oficial, não apenas por nome;
7. publicar cobertura e data da última sincronização.

O radar não deve apresentar “Portugal” quando só alguns municípios têm cobertura. A página precisa
de uma matriz pública de cobertura por fonte e território.

## Portal BASE e dados.gov.pt

Catálogo oficial: <https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/>

O colector lê metadados do catálogo e escolhe o recurso correspondente ao ano. Aceita JSON, XML e ZIP
com limites de download, tamanho descomprimido e taxa de compressão; nunca executa conteúdos do
arquivo. Calcula o hash dos bytes exactos e mantém-nos privados durante a recolha. Uma operação
explicitamente confirmada em staging arquiva e atesta os bytes antes de carregar um lote
append-only; não cria contratos públicos, entidades, candidatos ou publicação.

Recursos com o mesmo identificador e conteúdo normalizado equivalente são conservados uma única
vez; versões materialmente diferentes do mesmo identificador são excluídas e remetidas para revisão.

No formato textual oficial `NIF/NIPC - Nome`, o separador só é aceite por correspondência estrita.
O identificador é convertido imediatamente para HMAC-SHA-256 com pepper e o valor em claro não entra
na colecção. Sem pepper configurado, não são persistidas correspondências por identificador.

Qualquer sequência autónoma de nove algarismos Unicode num nome ou texto livre publicável coloca o
contrato em quarentena privada. Campos fiscais explícitos inválidos têm o mesmo tratamento.

Extrações de grande volume através da API directa do Portal BASE devem seguir o procedimento oficial
do IMPIC. A existência de dados públicos não autoriza contornar autenticação, limites ou requisitos
de reutilização.
