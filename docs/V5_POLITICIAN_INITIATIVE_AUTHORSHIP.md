# V5.42 — autoria individual de iniciativas no circuito editorial

## Resultado desta entrega

A V5.42 acrescenta uma fotografia privada, versionada e append-only das relações individuais de
autoria que a Assembleia da República declara dentro de `iniAutorDeputados`. Cada relação conserva
exatamente:

- o `IniId` da iniciativa;
- o `idCadastro` do deputado autor;
- o nome parlamentar e o grupo tal como aparecem no documento;
- a relação literal `AUTHOR`;
- URL oficial, data de recolha e SHA-256 dos bytes arquivados;
- versão do normalizador, SHA-256 da fotografia e SHA-256 de cada relação.

Esta entrega também permite criar um processo editorial privado `PENDING` por relação. Nem a
ingestão, nem a proposta, nem uma aprovação editorial genérica criam uma autoria pública, pessoa,
filiação, revisão pública ou evento de publicação. A publicação e a retirada deste domínio exigem
portas próprias posteriores.

## Prova oficial da estrutura

A estrutura foi confirmada na documentação técnica oficial da Assembleia da República:

| Documento | URL oficial | Verificado em | SHA-256 dos bytes verificados | Tamanho |
|---|---|---|---|---:|
| Significado das tags do ficheiro `Iniciativas<Legislatura>.xml` | [Assembleia da República — Iniciativas.pdf](https://app.parlamento.pt/webutils/docs/doc.pdf?Inline=true&fich=Iniciativas.pdf&path=6148523063446f764c324679626d56304c3239775a57356b595852684c3052685a47397a51574a6c636e52766379394a626d6c6a6157463061585a68637939594a5449775447566e61584e7359585231636d45765357357059326c6864476c3259584d756347526d) | 2026-08-27 | `765d35b6b0525a17feb78d8757e0e41a979bd6716514f5a6ffbbdd670a20265f` | 773 523 bytes |

O documento define `iniAutorDeputados` como a estrutura dos deputados autores da iniciativa e a
estrutura aninhada disponibiliza `idCadastro`, `Nome` e `GP`. A prova de cada recolha concreta não
usa o hash acima como substituto: guarda o URL, a data e o SHA-256 próprios do JSON oficial da
legislatura que foi efetivamente arquivado.

## Regra de identidade

`idCadastro` é a única chave admitida para reconciliar a observação com `people.source_id`.

- `Nome` é texto de apresentação da fonte;
- `GP` é texto contextual da fonte;
- nenhum dos dois cria ou confirma identidade, partido, filiação ou mandato;
- não existe fuzzy matching, distância de edição, normalização fonética ou aproximação de siglas;
- um identificador em falta, uma iniciativa sem correspondência única ou relações divergentes
  fazem a operação falhar fechada.

Uma pessoa com o mesmo `idCadastro` pode ser indicada como reconciliação exata mesmo que o nome de
apresentação tenha mudado. Uma pessoa com nome idêntico e identificador diferente nunca é ligada.

## O que autoria não significa

A relação prova apenas que a fonte oficial declarou aquela pessoa como autora daquela iniciativa
na fotografia recolhida. Não permite concluir automaticamente:

- que votou a favor ou contra em qualquer fase;
- que mantém hoje a mesma posição;
- que representa uma posição coletiva do partido;
- que a iniciativa entrou em vigor ou teve determinado impacto;
- que a autoria é positiva, negativa, meritória ou censurável.

Sem prova adicional, consequência e impacto permanecem **dados indisponíveis**. A IA não é usada
para preencher nenhuma destas lacunas.

## Separação entre recolha, revisão e publicação

```text
JSON oficial arquivado
        ↓
fotografia privada IniId + idCadastro
        ↓
proposta editorial PENDING reconstruída no servidor
        ↓
revisão humana
        ↓
publicação específica da V5.43, novamente confirmada por ADMIN com MFA
        ↓
retirada append-only da V5.44, sem apagar relação, fonte ou publicação
```

O formulário privado exige confirmação expressa de que:

1. a proposta permanece privada;
2. o `IniId` é exato;
3. o `idCadastro` é exato;
4. a relação é literalmente autoria declarada pela fonte;
5. nomes e siglas não são usados para correspondência;
6. autoria não é convertida em voto ou posição coletiva.

O servidor ignora qualquer tentativa do browser de construir os dados normalizados. Reconstrói a
proposta a partir da observação imutável, compara o SHA-256 enviado com o registo atual e volta a
validar fonte, arquivo, manifesto, iniciativa e contagens.

A etapa posterior está documentada em
[V5.43 — publicação transacional de autoria individual](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_PUBLICATION.md).
A retirada específica está documentada em
[V5.44 — retirada imutável de autoria individual](V5_POLITICIAN_INITIATIVE_AUTHORSHIP_WITHDRAWAL.md).

## Persistência e segurança

As tabelas `parliament_initiative_author_snapshots` e
`parliament_initiative_author_observations`:

- recusam `UPDATE` e `DELETE` através do trigger append-only já protegido por `search_path`;
- têm RLS ativa;
- não concedem políticas ou privilégios a `anon` ou `authenticated`;
- não têm projeção pública;
- não guardam NIF, contacto ou outro identificador fiscal;
- não criam pessoas, partidos, mandatos ou relações públicas durante a ingestão.

Uma nova interpretação exige outra versão do parser e outra fotografia; nunca altera a anterior.

## Verificação

Os testes locais cobrem extração estrita, duplicados divergentes, prova de arquivo, revalidação dos
bytes, recusa em produção e ausência de publicação. O teste de integração usa apenas PostgreSQL
descartável, prova idempotência e imutabilidade, reconcilia por `idCadastro` mesmo com nome
diferente e confirma que aprovar a proposta continua a criar zero revisões ou eventos públicos.

Nenhum comando de staging, migração remota ou operação sobre dados reais foi executado nesta
entrega.
