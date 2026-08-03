# Fontes e integração

## Matriz atual

| Fonte | Estado técnico | Implementado | Limite conhecido |
|---|---|---|---|
| Assembleia da República | Funcional | Descoberta de catálogos, JSON, deputados e votações | Estruturas variam por legislatura; nem toda votação é nominal |
| Diário da República | Funcional/configurável | Extração de diploma por URL ELI e RSS definido pelo operador | O RSS não é presumido sem endpoint oficial documentado |
| Entidade para a Transparência | Funcional, mínimo | Índice de recursos públicos do portal | Não contorna formulários nem republica dados excessivos |
| Portal BASE / dados.gov.pt | Funcional | Descoberta anual, JSON/XML/ZIP, hash, normalização e candidatos exatos | API direta de grande volume pode exigir registo e autorização |
| Tribunal de Contas | Modelo preparado | Editor, documentos, processos e relações aceites no esquema | Conector de relatórios ainda não ativado |
| Parlamento Europeu | Modelo preparado | Editor e votações europeias previstos no esquema | Adaptador REST ainda não ativado |
| Imprensa | Modelo preparado | RSS, notícia, menção, prova e revisão previstos no esquema | A allowlist editorial deve ser aprovada antes de produção |
| Radar local/SNS | Esquema preparado | Distritos, municípios e itens locais | Conectores específicos ainda não implementados |

## Assembleia da República

Catálogo: <https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx>

O portal fornece XML e JSON e organiza ficheiros por catálogo e legislatura. Como os URLs podem ser
opacos, `ParlamentoCollector.discover_dataset_url`:

1. descarrega a página temática oficial;
2. localiza a ligação da legislatura pedida;
3. abre a pasta oficial, quando necessário;
4. escolhe um ficheiro JSON;
5. volta a validar o anfitrião após cada redirecionamento;
6. calcula o hash antes da normalização.

Aliases de campo existem para tolerar nomes históricos. O SHA-256 é calculado sobre os bytes
recebidos, antes de descodificar e normalizar o JSON. Uma mudança de estrutura que produza zero
registos gera aviso; não promove uma tabela vazia como verdade.

Na fotografia oficial da legislatura XVII, o detalhe das votações identifica sobretudo grupos
parlamentares ou rótulos textuais, não deputados através de um identificador individual estável.
Essas posições permanecem em staging como `UNKNOWN`: uma posição partidária nunca é atribuída a
uma pessoa. Quando a própria fonte não contém detalhe estruturado, a cobertura é apresentada como
“dados indisponíveis”, nunca como zero. A leitura pública exige uma revisão humana positiva e
específica do mesmo documento-fonte.

## Diário da República

Portal: <https://diariodarepublica.pt/>

O coletor aceita apenas URLs de anfitriões DRE autorizados. URLs ELI podem ser construídos por tipo,
número e data. O HTML é reduzido a texto após remoção de navegação, scripts, estilos e formulários.
O documento guardado deve conservar o HTML/PDF original, mesmo que o parser produza apenas texto.

Defina `DRE_RSS_URL` quando a equipa confirmar e documentar o feed oficial a usar. Esta decisão
evita depender de um URL adivinhado.

## Entidade para a Transparência

Portal: <https://www.tribunalconstitucional.pt/tc/ept/>

O conector atual indexa ligações públicas e conserva a origem. O tratamento de declarações deve ser
precedido de revisão jurídica, avaliação de proteção de dados, termos de reutilização e decisão
documentada sobre campos necessários.

## Novas fontes locais

Antes de integrar um município, SNS ou portal setorial:

1. confirmar organismo competente e licença/regras de reutilização;
2. preferir API, RSS, CSV ou dados abertos a scraping HTML;
3. adicionar o domínio exato à allowlist após revisão;
4. definir identificador estável e frequência razoável;
5. criar fixture e contrato de parser;
6. mapear distrito/município por código oficial, não apenas por nome;
7. publicar cobertura e data da última sincronização.

O radar não deve apresentar “Portugal” quando só alguns municípios têm cobertura. A página precisa
de uma matriz pública de cobertura por fonte e território.

## Portal BASE e dados.gov.pt

Catálogo oficial: <https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/>

O coletor lê metadados do catálogo e escolhe o recurso correspondente ao ano. Aceita JSON, XML e ZIP
com limites de download, tamanho descomprimido e taxa de compressão; nunca executa conteúdos do
arquivo. Guarda o hash ligado ao URL do ficheiro efetivamente descarregado e, quando a linha inclui
um URL oficial individual, conserva-o apenas como metadado auxiliar. Um URL direto só pode receber
hash próprio depois de esse documento ser descarregado e verificado separadamente.
Recursos com o mesmo identificador e conteúdo normalizado equivalente são conservados uma única
vez; versões materialmente diferentes do mesmo identificador são excluídas da coleção e remetidas
para revisão, sem escolher automaticamente uma delas.

No formato textual oficial `NIF/NIPC - Nome`, o separador só é aceite por correspondência estrita:
o nome público perde o prefixo e o identificador é convertido imediatamente para HMAC-SHA-256 com
pepper. Só o digest excluído da serialização participa na deduplicação e no cruzamento privado; o
valor em claro não entra na coleção. Sem pepper configurado, usa-se um segredo efémero apenas para
deduplicar a recolha e não são produzidas correspondências por identificador.

Qualquer sequência autónoma de nove algarismos Unicode — também separada por espaços ou pontuação —
num nome ou noutro texto livre publicável coloca o contrato em quarentena privada. Campos fiscais
explícitos não vazios mas inválidos têm o mesmo tratamento. Os avisos são agregados e nunca repetem
o valor encontrado. Campos tipados, como montante, prazo e identificador oficial do contrato, não
são reinterpretados automaticamente como NIF.

Extrações de grande volume através da API direta do Portal BASE devem seguir o procedimento oficial
do IMPIC. A existência de dados públicos não autoriza contornar autenticação, limites ou requisitos
de reutilização. Identificadores individuais não são devolvidos pelos modelos públicos.

## Tribunal de Contas, Ministério Público e tribunais

Relatórios, comunicados e decisões entram como `SourceDocument` com editor específico. O parser não
converte automaticamente linguagem judicial em culpa. Estado, instância, recurso, datas e sujeitos
exigem validação. Segredo de justiça, direitos de personalidade e atualizações favoráveis têm de ser
tratados na política editorial antes de ativar qualquer conector.

## Parlamento Europeu

Portal de dados: <https://data.europarl.europa.eu/en/developer-corner/opendata-api>

O esquema aceita votações europeias com prova e identidade separadas das votações nacionais. Uma
posição de grupo europeu não pode ser atribuída a um eurodeputado sem registo nominal explícito.

## RSS de imprensa

A allowlist deve publicar critérios de inclusão, titular do feed, licença, frequência e data de
revisão. O agregador preserva o URL canónico e nunca usa uma peça jornalística como substituto de
contrato, decisão, acusação ou relatório oficial. Menções detetadas automaticamente são candidatas,
não factos editoriais.
