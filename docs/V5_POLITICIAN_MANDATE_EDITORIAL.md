# V5.33 — intervalos oficiais no circuito editorial de mandatos

## Objetivo

A V5.33 abre uma porta privada e específica para preparar mandatos parlamentares a partir das
situações oficiais preservadas na V5.27. Não transforma uma data observada em conclusão jurídica,
não cria `Mandate`, não acrescenta `DataPublicationReview` e não publica qualquer cronologia.

O ponto de partida continua a ser a
[página oficial de atividade dos deputados](https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx)
e o respetivo recurso arquivado a partir do
[catálogo de dados abertos](https://www.parlamento.pt/Cidadania/Paginas/dadosabertos.aspx). A fonte
permite observar situações e datas, mas a interpretação de um período como mandato exige uma
decisão humana própria.

## Comparador privado

`GET /api/v1/editorial/parliament/mandate-candidates` exige uma conta editorial ativa com MFA e
expande apenas os intervalos `DepSituacao` já ligados a um `DepId` oficial. Para cada intervalo
mostra:

- pessoa e `DepId` exatamente como constam da observação privada;
- designação, data inicial e data final conservadas pela fonte;
- círculo e respetivo identificador oficial;
- URL, data de recolha, SHA-256 dos bytes e atestação de arquivo;
- SHA-256 canónico do intervalo selecionável;
- estado da identidade pública exata e bloqueios concretos.

Um candidato só pode entrar na fila quando a identidade já tem uma fotografia publicada pelo mesmo
`DepId`, a última revisão `PERSON` ligada à fonte é positiva, existe círculo com ID e designação,
as contagens coincidem com o manifesto, a data inicial existe e o intervalo não está invertido.
As designações elegíveis limitam-se às formas oficiais de exercício efetivo reconhecidas pelo
normalizador. Outros estados permanecem visíveis como dados observados, mas bloqueados.

## Proposta reconstruída no servidor

`POST /api/v1/editorial/parliament/mandate-proposals` recebe apenas:

- identificador interno da observação;
- SHA-256 do intervalo oficial escolhido;
- confirmação de que a proposta permanece privada;
- confirmação de correspondência exclusiva por `DepId` oficial exato;
- confirmação de que a semântica do período exige revisão humana;
- confirmação de que não será inferida filiação partidária.

O browser não fornece nomes, datas, círculo, título, conteúdo normalizado ou fonte. O servidor volta
a reconstruir toda a prova e cria, de forma idempotente, um caso `POLITICIAN_PROFILE` com assunto
`PARLIAMENT_MANDATE_SITUATION` e versão `politician-mandate-editorial-v1` em `PENDING`.
Identificadores internos e oficiais ficam representados no JSON editorial apenas por referências
SHA-256; os valores exatos continuam disponíveis apenas no comparador autenticado.

## Limites desta entrega

Mesmo depois de `START_REVIEW` e `APPROVE`, esta entrega cria zero:

- mandatos;
- revisões públicas `MANDATE`;
- ligações partidárias;
- eventos de publicação;
- alterações à consulta pública.

Uma aprovação significa apenas que a versão privada foi comparada com a fonte. Não autoriza a
publicação nem afirma que o intervalo corresponde juridicamente ao mandato completo. Campos em
falta são apresentados como **dados indisponíveis** e nunca preenchidos por nomes, siglas ou datas
de recolha.

## Próxima porta

A publicação futura terá de ser uma operação de domínio separada, exclusiva de `ADMIN` com MFA, e
voltar a confirmar fonte, arquivo, `DepId`, intervalo, círculo, versão aprovada e hashes. Só então
poderá acrescentar um `Mandate`, uma revisão `MANDATE`, `AuditEvent`, decisão `PUBLISH` e evento
editorial na mesma transação. Deverá ainda guardar a referência exata da observação e do intervalo,
ser append-only e dispor de retirada própria antes de qualquer ativação real.

Integrar, fazer deploy, migrar o esquema ou aprovar o caso nunca chama essa operação.
