# Fontes e integração

## Matriz atual

| Fonte | Estado técnico | Implementado | Limite conhecido |
|---|---|---|---|
| Assembleia da República | Funcional | Descoberta de catálogos, JSON, deputados e votações | Estruturas variam por legislatura; nem toda votação é nominal |
| Diário da República | Funcional em staging | Extração por URL ELI, bytes exactos, arquivo atestado e snapshot privado append-only | Sem promoção pública; feed RSS só após confirmação documental |
| Entidade para a Transparência | Colector funcional; staging preparado | Índice público com bytes exactos e schema privado de metadados com revisão jurídica obrigatória | A escrita operacional no staging ainda exige ensaio controlado; não recolhe declarações |
| Portal BASE / dados.gov.pt | Funcional em staging | Descoberta anual, JSON/XML/ZIP, arquivo, lote append-only e candidatos exactos apenas em ficheiro privado | Sem promoção pública; API directa de grande volume pode exigir registo e autorização |
| Tribunal de Contas | Colector mínimo funcional | Hash dos bytes exactos e ligações oficiais deduplicadas em memória privada | Sem persistência automática nem interpretação de decisões ou culpa |
| Parlamento Europeu | Colector mínimo funcional | Índice oficial da API aberta e ligações oficiais deduplicadas em memória privada | Sem persistência automática nem atribuição individual sem voto nominal explícito |
| Radar local/SNS | Colector mínimo funcional | Índice SNS oficial como origem inicial de descoberta | Sem persistência automática; não representa cobertura territorial nacional |
| Imprensa | Modelo preparado | RSS, notícia, menção, prova e revisão previstos no esquema | Fora do fecho V4; allowlist editorial necessária antes de produção |

## Regra comum de prova bruta V4

Os colectores do Parlamento, BASE, DRE, Entidade para a Transparência, Tribunal de Contas,
Parlamento Europeu e Radar SNS calculam o SHA-256 sobre os bytes exactos da resposta HTTP e
transportam-nos apenas num `PrivateRawDocument`, excluído de serialização.

Nos fluxos persistentes já activados — Parlamento, BASE e DRE — o documento só pode ser referenciado
depois de o objecto content-addressed ser escrito, verificado e atestado com o mesmo URL efectivo e
hash. EPT tem schema privado preparado mas requer ensaio operacional. Tribunal de Contas,
Parlamento Europeu e Radar SNS ficam nesta versão no limite deliberado de colector privado, sem
escrita automática.

Ausência de objecto, atestado, acesso ao arquivo ou estrutura suficiente significa “dados
indisponíveis”; nunca é interpretada como ausência de factos na fonte. Nenhuma recolha constitui
revisão editorial ou autorização de publicação.

## Assembleia da República

Catálogo: <https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx>

O portal fornece XML e JSON e organiza ficheiros por catálogo e legislatura. O colector descobre o
recurso oficial, valida o anfitrião após redireccionamentos e calcula o hash antes da normalização.
Aliases de campo toleram estruturas históricas, mas uma mudança que produza zero registos gera aviso
e não promove uma tabela vazia como verdade.

Posições de grupos parlamentares nunca são atribuídas automaticamente a deputados. Quando a fonte
não contém detalhe nominal estruturado, a cobertura é apresentada como “dados indisponíveis”.

## Diário da República

Portal: <https://diariodarepublica.pt/>

O colector aceita apenas URLs DRE autorizados. O `content_sha256` identifica os bytes brutos e o
`normalised_text_sha256` identifica separadamente o texto extraído. Em staging, os bytes são
arquivados e atestados antes do snapshot privado append-only. O snapshot não cria leis públicas,
alertas ou registos de revisão, e o inspector nunca devolve o texto extraído.

Defina `DRE_RSS_URL` apenas quando a equipa confirmar e documentar o feed oficial a usar.

## Entidade para a Transparência

Portal: <https://www.tribunalconstitucional.pt/tc/ept/>

O colector indexa apenas ligações publicamente acessíveis e conserva os bytes exactos. O schema de
staging guarda somente título, categoria e URL, com estado fixo `REQUIRES_LEGAL_REVIEW` e sem
projecção pública. A ligação operacional entre colector, arquivo e staging fica dependente de ensaio
controlado antes de qualquer activação.

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

Este colector não persiste automaticamente os índices. No Tribunal de Contas não interpreta
linguagem judicial, culpa, sujeitos ou estado processual. No Parlamento Europeu não atribui posições
de grupo a pessoas. No Radar SNS, o índice nacional é apenas uma origem inicial e não equivale a
cobertura territorial.

## Portal BASE e dados.gov.pt

Catálogo oficial: <https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/>

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
