# V5.3 — publicação parlamentar específica por âmbito

## Objetivo

A V5.3 liga um processo parlamentar aprovado no circuito editorial V5 à porta pública já
auditada na V4. A operação é deliberadamente específica: um processo de atividade só pode
publicar reuniões e iniciativas; um processo de votações só pode publicar votações e posições.
O browser confirma o âmbito apresentado, mas nunca escolhe o tipo de alvo que será escrito. O
servidor deriva-o das colunas imutáveis `kind` e `subject_type` do processo.

Esta entrega implementa o código e os testes locais. Não executa qualquer publicação real: o
ensaio transacional usa apenas PostgreSQL descartável, sem acesso de escrita à produção. Também
não aplica migrações remotas nem altera ambientes, utilizadores ou segredos.

## Pré-condições fail-closed

Uma publicação só é elegível quando todas estas condições são verdadeiras:

1. a sessão pertence a um `ADMIN` ativo, autenticado com MFA (`aal2`);
2. o processo está exatamente em `APPROVED` e nasceu com origem `INGESTION`;
3. a combinação de tipo e assunto corresponde a um dos dois âmbitos reconhecidos;
4. o identificador relacional do processo aponta para a fotografia e para o documento-fonte
   oficiais exatos;
5. a fonte continua a ser da Assembleia da República, usa HTTPS, não é notícia e possui arquivo
   atestado com URL, data e SHA-256 coincidentes;
6. as quatro contagens materializadas continuam iguais ao manifesto imutável;
7. atividade contém reuniões e iniciativas; votações contém pelo menos uma votação;
8. uma publicação de votações não contém ligações de atores incompatíveis com o tipo registado;
9. o JSON da versão editorial continua a corresponder ao seu próprio SHA-256;
10. o envelope factual da versão editorial coincide com a prova reconstruída no servidor;
11. ainda não existe um evento `PUBLISH` para aquele processo e alvo;
12. revisão, âmbito, fotografia e quatro SHA-256 enviados na confirmação continuam atuais.

Qualquer divergência termina a operação antes das escritas públicas. Não há correspondência
aproximada de nomes, inferência de votos individuais, tolerância silenciosa a contagens diferentes
nem substituição de dados ausentes por valores inventados.

## Envelope factual e correções

O envelope factual é reconstruído a partir do snapshot e inclui:

- versão do esquema, âmbito e legislatura;
- referência derivada da fotografia, parser, SHA-256 normalizado e data de recolha;
- referência derivada do documento, URL oficial, data, SHA-256 e atestação de arquivo;
- manifesto, métricas de cobertura, diferenças por identificador oficial exato e limitações;
- marcas de controlo que mantêm a publicação automática desativada e a revisão humana obrigatória.

Notas editoriais adicionais podem receber uma nova versão humana, mas as limitações de origem não
podem ser removidas ou enfraquecidas. Uma correção que altere factos ou salvaguardas desse envelope
não pode publicar a projeção antiga: primeiro é necessário corrigir os dados materializados ou criar
prova oficial coerente e repetir a revisão. Assim, uma correção editorial nunca finge ter alterado
reuniões, iniciativas, votações ou posições que o site público realmente consulta.

## Confirmação humana

O painel mostra o âmbito, a cobertura e estes quatro digests antes de ativar a ação:

- SHA-256 dos bytes da fonte;
- SHA-256 normalizado da fotografia;
- SHA-256 da versão editorial;
- SHA-256 do envelope factual de publicação.

O administrador tem de acrescentar fundamentação e confirmar separadamente que voltou a rever a
fonte, que não inferiu votos individuais e que pretende publicar apenas o âmbito indicado. Uma
aprovação anterior não substitui esta nova confirmação.

## Commit transacional único

Depois de bloquear o processo e a fotografia, uma única transação acrescenta:

1. `DataPublicationReview` V4 para o tipo e fotografia exatos;
2. `AuditEvent` V4 com estado anterior, hashes, contagens e ligação ao processo editorial;
3. `EditorialDecision` com ação `PUBLISH`, identidade do administrador e SHA-256;
4. projeção do processo de `APPROVED` para `PUBLISHED`, com revisão incrementada uma unidade;
5. `EditorialPublicationEvent` ligado à versão e ao alvo, também com SHA-256.

Os gatilhos PostgreSQL impedem alterações ao histórico e exigem que a decisão corresponda ao
estado anterior. A restrição diferida recusa o commit se `PUBLISHED` não tiver o respetivo evento
imutável. Se qualquer uma das cinco escritas falhar, nenhuma delas é confirmada e a projeção
pública permanece como estava.

## Superfície privada

- `GET /api/v1/editorial/parliament/cases/{case_id}/publication` reconstrói a prova e não escreve;
- `POST /api/v1/editorial/parliament/cases/{case_id}/publication` exige `ADMIN`, MFA e todas as
  confirmações exatas;
- não existe endpoint genérico `publish` para outros tipos editoriais;
- o botão só é apresentado a administradores e fica desativado perante qualquer bloqueio;
- decisões e eventos de publicação ficam visíveis no histórico privado.

## Fora do âmbito

Esta etapa ainda não:

- publica automaticamente processos aprovados;
- publica correções que não estejam refletidas na fotografia parlamentar materializada;
- associa nomes a pessoas ou partidos sem identificadores oficiais inequívocos;
- cria explicações por IA ou usa IA como fonte;
- executa deploy, migração remota, configuração do Supabase ou publicação real de dados.

A operação explícita e append-only de retirada, o efeito de recuo para fotografias anteriores e o
ciclo obrigatório de correção estão especificados em
[V5.4 — retirada parlamentar imutável e ciclo de correção](V5_PARLIAMENT_WITHDRAWAL.md).
