# V5.41 — retirada integral e imutável de presenças por reunião

## Objetivo

A V5.41 fecha o ciclo editorial iniciado na V5.39 e publicado na V5.40. Uma reunião só deixa a
consulta pública através de uma nova decisão humana, expressa e auditável. A retirada incide sempre
sobre a reunião inteira; não existe um caminho para esconder a presença ou falta de uma pessoa
isolada.

Esta entrega não executa uma retirada real, não aplica migrações remotas e não altera staging ou
produção. Prepara e testa a porta privada que continuará dependente da ativação operacional da V5.

## Prova reconstruída antes da decisão

O servidor volta a verificar, sem confiar nos campos ocultos do browser:

1. processo `PUBLISHED`, versão aprovada e decisão de publicação atual;
2. URL oficial da Assembleia da República, data de recolha e SHA-256 da fonte;
3. arquivo atestado dos mesmos bytes e fotografia privada novamente derivável;
4. manifesto da reunião, zero estados `UNKNOWN` e todas as observações;
5. correspondência exclusiva por BID oficial exato e exatamente um mandato revisto por linha;
6. sessão pública, todas as presenças e o SHA-256 individual de cada registo;
7. revisão positiva atual, auditoria `PUBLISHED` e evento de publicação com hash válido;
8. efeito público previsto e prova SHA-256 específica da retirada.

Qualquer divergência bloqueia a operação. Não há correspondência por nome, sigla, semelhança ou
*fuzzy matching*. Uma falta continua a reproduzir apenas o estado da fonte naquela reunião; nunca
é convertida automaticamente em culpa ou incumprimento.

## Transação append-only

A ação exige `ADMIN` e MFA e acrescenta, numa única transação:

1. uma nova `DataPublicationReview` negativa para a fotografia integral;
2. um `AuditEvent` `WITHDRAWN` com categoria pública fechada e efeito comprovado;
3. uma decisão editorial `WITHDRAW`, levando o processo a `WITHDRAWN`;
4. um `EditorialPublicationEvent` imutável de retirada.

Nenhuma linha é eliminada ou alterada. Permanecem a `ParliamentarySession`, todas as
`AttendanceRecord`, as observações privadas, a fonte, o arquivo, a versão, a revisão positiva, a
auditoria e o evento de publicação originais. O teste de integração confirma ainda que uma prova
incorreta cria zero novas revisões e que uma segunda retirada é recusada.

## Efeito na consulta pública

A ficha política usa sempre a revisão integral mais recente. Depois da revisão negativa, nenhuma
linha dessa reunião entra nos totais ou no histórico ativo. O registo histórico continua preservado
para auditoria e eventual correção por nova fonte, nova fotografia e novo circuito editorial.

A retirada não conclui que os dados originais eram falsos, nem que houve incumprimento. A categoria
e a fundamentação pública documentam o motivo permitido. Se a fonte ou cobertura não fornecer prova
suficiente, a apresentação correta continua a ser **dados indisponíveis**.

## Limites operacionais

- não altera pessoas, mandatos, filiações ou outras reuniões;
- não permite retirada seletiva por pessoa ou estado;
- não usa IA para decidir, interpretar ou recomendar a retirada;
- não apaga histórico nem substitui a versão publicada;
- não ativa recolha, publicação ou retirada em dados reais.

Com a V5.41, o domínio de presenças fica tecnicamente fechado para avançar para autoria oficial de
iniciativas e votos nominais individuais, mantendo cada domínio numa porta editorial independente.
