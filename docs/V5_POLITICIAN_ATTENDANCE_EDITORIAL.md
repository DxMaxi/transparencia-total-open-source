# V5.39 — presenças parlamentares por reunião no circuito editorial

## Objetivo e âmbito

A V5.39 abre a primeira porta privada para presenças em reuniões plenárias. Cada fotografia cobre
uma única página oficial de detalhe da Assembleia da República e preserva a reunião inteira. Não
mede produtividade, não classifica deputados, não converte uma falta em incumprimento e não afirma
completude histórica fora das reuniões efetivamente recolhidas.

As fontes de referência são a
[consulta oficial de reuniões plenárias](https://www.parlamento.pt/DeputadoGP/Paginas/reunioesplenarias.aspx)
e cada página de detalhe com um único parâmetro numérico `BID`. Em cada entrada individual, a
ligação oficial para `Biografia.aspx?BID=...` fornece o identificador inequívoco do deputado. Nome,
sigla, posição visual ou semelhança textual nunca substituem esse identificador e não existe fuzzy
matching.

## Recolha privada e prova documental

O comando de recolha exige, ao mesmo tempo:

- `ENVIRONMENT=staging` e uma base de dados explicitamente configurada;
- a confirmação `--confirm-private-staging`;
- legislatura suportada e URL HTTPS exato no domínio `parlamento.pt`;
- o caminho oficial de detalhe e exatamente um `BID` numérico, sem parâmetros adicionais;
- HTML com data e tipo de reunião inequívocos;
- entre 100 e 500 entradas com `BID` individual exato;
- pelo menos 70% dos estados reconhecidos pelo vocabulário conservador.

Os bytes originais são arquivados antes da persistência. A fotografia conserva URL oficial, data
de recolha, SHA-256 do documento, atestação do arquivo, versão do parser e SHA-256 normalizado. O
parser é repetido sobre os mesmos bytes imediatamente antes da escrita; qualquer divergência
recusa toda a operação.

Os estados aceites são `PRESENT`, `JUSTIFIED_ABSENCE`, `UNJUSTIFIED_ABSENCE` e `UNKNOWN`. Texto que
não pertence ao vocabulário conhecido permanece `UNKNOWN`; não é corrigido por IA nem por
inferência e bloqueia uma futura publicação até a fonte ou o parser serem revistos.

## Fotografia integral e histórico append-only

`parliament_attendance_snapshots` guarda o manifesto da reunião e
`parliament_attendance_observations` guarda cada registo ligado ao mesmo snapshot. As duas tabelas:

- são privadas, têm RLS ativa e não concedem privilégios a `PUBLIC`, `anon` ou `authenticated`;
- rejeitam `UPDATE` e `DELETE` por trigger append-only;
- exigem que a soma dos estados coincida com o total do manifesto;
- não criam pessoas, mandatos, sessões ou presenças públicas;
- não criam automaticamente um processo editorial.

Uma nova versão da página oficial produz uma nova fonte e uma nova fotografia. Nunca substitui os
bytes, as observações ou o evento de ingestão anteriores.

## Comparador e proposta editorial

`GET /api/v1/editorial/parliament/attendance-candidates` exige staff autenticado e mostra apenas
reuniões com fonte e arquivo atestado. O painel volta a contar os registos e apresenta separadamente:

- totais por estado;
- identidades públicas ligadas pelo mesmo `BID` exato;
- identidades com revisão pública positiva;
- mandatos exatos que cobrem a data da reunião;
- mandatos com revisão pública positiva;
- estados `UNKNOWN`, divergências e restantes bloqueios.

`POST /api/v1/editorial/parliament/attendance-proposals` recebe apenas o identificador da fotografia
e seis confirmações explícitas. O servidor volta a reconstruir a reunião completa e cria, no
máximo, um caso privado `POLITICIAN_PROFILE` com
`subject_type=PARLIAMENT_ATTENDANCE_SNAPSHOT`, estado `PENDING` e referências individuais por
SHA-256. O URL da reunião permanece legível porque faz parte da prova oficial.

Mesmo depois de revisão e aprovação, esta entrega cria zero:

- sessões e presenças públicas;
- revisões públicas individuais;
- eventos de publicação;
- associações por nome;
- omissões ou promoções seletivas de deputados.

## Semântica pública futura

Uma futura porta de publicação só pode aceitar a reunião completa quando todos os registos tiverem
estado conhecido, identidade publicada pelo `BID` exato e exatamente um mandato publicado e revisto
que cubra a data. Ter a proposta pronta para revisão não satisfaz essas condições.

Se faltar prova, a resposta é **dados indisponíveis**. Uma presença prova apenas o estado publicado
para aquela reunião; uma falta não demonstra culpa, desinteresse, incumprimento nem ausência de
outro trabalho parlamentar. IA não é fonte e não pode preencher, interpretar ou prever estes
factos.

Esta capacidade foi exercitada localmente e num PostgreSQL descartável do CI. Não executa recolha,
migração, revisão ou publicação em staging ou produção, não cria utilizadores e não altera
segredos ou dados reais.
