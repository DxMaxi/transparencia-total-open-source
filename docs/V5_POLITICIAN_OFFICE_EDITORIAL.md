# V5.36 — cargos parlamentares oficiais no circuito editorial

## Objetivo

A V5.36 abre uma porta privada e específica para cada `DepCargo` preservado na fotografia V5.27.
Um cargo observado não é tratado como mandato, filiação partidária, competência jurídica atual ou
prova de continuidade. Esta entrega cria apenas propostas `PENDING`; não cria tabelas públicas,
revisões de publicação ou eventos de publicação.

O ponto de partida é a
[página oficial de atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx)
e o recurso exato arquivado a partir do
[catálogo de dados abertos da Assembleia da República](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx).
Cada proposta conserva a URL oficial, a data de recolha, o SHA-256 dos bytes, a atestação do
arquivo, a versão do parser e o SHA-256 canónico do período selecionado.

## Comparador privado

`GET /api/v1/editorial/parliament/office-candidates` exige staff ativo com MFA e expande somente o
array privado `offices` de uma fotografia atestada. Para cada candidato mostra:

- `DepId` e `CarId` oficiais exatos;
- título oficial, início e fim observados;
- círculo e respetivo identificador oficial;
- pessoa já publicada pelo mesmo `DepId` e pela mesma fonte;
- URL, data de recolha, SHA-256 e prova do arquivo;
- contagens do manifesto e contagens materializadas;
- bloqueios e limitações, incluindo campos indisponíveis.

A pesquisa limita a lista; não cria relações. Nome, sigla, título semelhante ou posição na lista
nunca substituem `DepId`, `CarId` ou o identificador oficial do círculo. Não existe fuzzy matching.

## Proposta reconstruída no servidor

`POST /api/v1/editorial/parliament/office-proposals` recebe apenas o identificador interno da
observação, o SHA-256 do período e quatro confirmações explícitas. O servidor volta a reconstruir a
fonte e aceita o candidato apenas quando:

1. `DepId` e `CarId` existem;
2. título e data inicial foram fornecidos pela fonte;
3. o intervalo não está invertido;
4. círculo tem identificador e designação oficiais;
5. a identidade já foi publicada pelo mesmo `DepId` e documento;
6. fonte, arquivo e contagens coincidem integralmente.

O caso usa `kind=POLITICIAN_PROFILE`, `subject_type=PARLIAMENT_OFFICE_PERIOD` e
`schema_version=politician-office-editorial-v1`. Os identificadores internos e oficiais aparecem
no JSON editorial apenas como referências SHA-256. Título, período e círculo permanecem legíveis
para comparação humana, pois são os factos que o revisor tem de confrontar com a fonte.

## Separação entre aprovação e publicação

Mesmo depois de `START_REVIEW` e `APPROVE`, esta entrega cria zero:

- cargos ou mandatos públicos;
- ligações partidárias;
- revisões `DataPublicationReview`;
- eventos de publicação;
- alterações ao perfil público.

Aprovar confirma apenas que o cargo observado foi comparado com a fonte. Uma futura publicação terá
de usar um modelo próprio append-only, voltar a validar toda a prova numa transação `ADMIN` com MFA
e dispor de retirada específica antes de qualquer ativação real. Deploy, migração ou aprovação do
caso nunca chamam essa operação.

## Limites e porta operacional

- Um fim vazio significa intervalo aberto na fonte, não cargo atualmente exercido.
- Um cargo sem `CarId` continua visível no comparador como dados indisponíveis, mas fica bloqueado.
- O círculo acompanha a observação e não é inferido a partir do nome da pessoa.
- A IA não classifica cargos, não completa períodos e não decide elegibilidade.
- A fotografia continua `PARTIAL` e não afirma completude histórica.

Esta capacidade foi testada apenas localmente e num PostgreSQL descartável do CI. Não recolhe nem
altera dados em staging ou produção, não cria utilizadores, não muda segredos e não publica dados
reais.
