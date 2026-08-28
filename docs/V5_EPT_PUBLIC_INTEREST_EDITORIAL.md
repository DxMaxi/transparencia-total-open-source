# V5.46 — registo público de interesses EPT em circuito privado

## Resultado

A V5.46 prepara uma entrada **privada, mínima e fail-closed** para uma prova individual da
Entidade para a Transparência. Não recolhe nem publica o conteúdo da declaração, não associa uma
pessoa por nome e não transforma o portal institucional num facto sobre um titular.

O limite é deliberado. O artigo 17.º da Lei n.º 52/2019 distingue os campos do registo de
interesses, cuja publicidade é prevista no n.º 4, dos elementos relativos a rendimentos e
património, cujo acesso é condicionado, sem faculdade de reprodução, e cuja divulgação geral é
restringida. O texto oficial está publicado pelo
[Tribunal Constitucional](https://www.tribunalconstitucional.pt/tc/legislacao0306-lei20190052.html).
Esta leitura técnica não substitui uma AIPD, o encarregado de proteção de dados ou aconselhamento
jurídico português independente.

## Dados admitidos

Uma observação `ept_public_interest_observations` conserva somente:

- identificador público da declaração;
- HMAC-SHA-256 do identificador oficial do titular, com pepper privado durável;
- nome que a própria prova apresenta publicamente, apenas para inspeção humana;
- tipo fixo `INTEREST_REGISTER`;
- data e período, quando a fonte os fornece;
- referência ao `SourceDocument`, data de recolha e SHA-256;
- hash canónico da observação;
- estados fixos `UNLINKED_PRIVATE` e `REQUIRES_INDEPENDENT_LEGAL_REVIEW`.

Não existem colunas para rendimentos, património, moradas, contactos, NIF, conteúdo integral,
anexos ou notas livres. O identificador do titular nunca é aceite como argumento da linha de
comandos: é pedido sem eco e convertido imediatamente para HMAC. Sem
`PROTECTED_IDENTIFIER_PEPPER`, a operação falha antes de consultar a base de dados.

## Prova obrigatória

A escrita só é aceite quando o documento já existe no arquivo privado e reúne simultaneamente:

1. `publisher = TRANSPARENCY_ENTITY`;
2. `kind = DECLARATION`;
3. URL HTTPS individual, diferente dos portais institucionais gerais;
4. `SourceDocument.official_identifier` exatamente igual ao identificador da declaração;
5. atestação do arquivo com URL, data e SHA-256 coincidentes.

O PostgreSQL repete estas condições num trigger. `UPDATE` e `DELETE` são recusados; uma nova versão
da fonte cria outra observação.

## Separação editorial

O painel `/admin/revisao/declaracoes` lista apenas observações privadas. O browser envia o ID da
observação, o SHA-256 canónico e confirmações fechadas. O servidor reconstrói a prova e cria um
processo `POLITICIAN_PROFILE / EPT_PUBLIC_INTEREST_OBSERVATION` em `PENDING`.

Criar ou aprovar esta proposta produz sempre zero:

- ligações a `people`;
- `AssetDeclarationMetadata`;
- `DataPublicationReview` pública;
- `EditorialPublicationEvent`;
- alterações ao site público.

A pesquisa por nome é apenas um filtro dentro do painel. Não existe `similarity`, Levenshtein,
fuzzy matching ou associação automática.

## Porta antiga fechada

O comando genérico `review_publication ASSET_DECLARATION --publish` deixou de poder publicar este
domínio. Mesmo uma confirmação booleana de base legal não substitui a futura porta EPT específica.
A consulta pública também exige um evento de publicação EPT dedicado, além da fonte, arquivo e
revisão positiva. Assim, uma linha antiga ou inserida fora do novo circuito permanece invisível.

## Operação futura

Depois de o documento individual ter sido recolhido e arquivado por um processo autorizado, a
observação pode ser preparada localmente com:

```text
python -m scripts.stage_ept_public_interest SOURCE_DOCUMENT_ID DECLARATION_ID "NOME PÚBLICO" \
  --actor operador-ept --confirm-public-interest-register-only \
  --confirm-no-income-or-asset-content --confirm-no-protected-identifiers-persisted \
  --confirm-private-only
```

O comando pede depois o identificador do titular sem o mostrar. Este exemplo documenta o contrato;
não autoriza recolha, migração ou escrita em staging/produção.

A V5.47 só poderá criar a ligação individual e a projeção pública depois de existir prova oficial
inequívoca da identidade, revisão jurídica independente registada, decisão humana, conta `ADMIN`
com MFA, preview do efeito público e histórico append-only. Se qualquer elemento faltar, a área
pública deve dizer `dados indisponíveis`.
