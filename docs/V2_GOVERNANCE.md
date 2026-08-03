# Governação editorial, jurídica e de dados — V2

Este documento define barreiras mínimas entre uma pista técnica e um facto publicável. Aplica-se
simetricamente a todas as pessoas, partidos, empresas, governos, municípios e períodos.

## Estados de publicação

| Estado | Visibilidade | Significado |
|---|---|---|
| `INGESTED` | Operacional | Cópia recebida; estrutura e origem ainda por validar |
| `CANDIDATE` | Privada | Correspondência técnica que precisa de prova e contexto |
| `VERIFIED` | Privada | Fonte, identidade, datas e âmbito confirmados |
| `REVIEWED` | Privada | Decisão editorial e jurídica registada por pessoa autorizada |
| `PUBLISHED` | Pública | Pode entrar no site e na API Open Data |
| `RETRACTED` | Pública no histórico | Retirada de circulação, com motivo; o rasto não é apagado |

Nenhuma contagem, pontuação, grafo, alerta ou texto de IA pode saltar estados. O frontend consulta
apenas registos `PUBLISHED` e, quando aplicável, `VERIFIED`.

## Matriz de prova por afirmação

| Afirmação | Prova mínima | Linguagem pública permitida |
|---|---|---|
| Contrato celebrado | Registo individual BASE ou dump oficial com identificador e hash | “A entidade A consta como adjudicante/adjudicatária no contrato B” |
| Cargo público | Página, despacho ou registo do órgão competente | “Exerceu o cargo C entre as datas publicadas” |
| Cargo societário | Registo oficial legalmente reutilizável ou ato oficial equivalente | “Consta no registo indicado como…” |
| Associação indireta | Duas ou mais fontes oficiais que fecham a cadeia e revisão | “As fontes documentam a sequência A–B–C” |
| Processo criminal | Comunicado/ato do MP ou documento do tribunal | Estado processual exato, data e presunção de inocência |
| Condenação | Sentença/decisão oficial, distinguindo trânsito em julgado | Dispositivo, instância e estado do recurso |
| Falha financeira | Relatório ou decisão do Tribunal de Contas | Conclusão e âmbito tal como constam do relatório |
| Discurso vs. voto | Declaração íntegra e voto nominal sobre objeto comparável | Resultado, denominador, exclusões e nível de confiança |

Notícias e redes sociais são índices de descoberta. Não substituem a prova documental nas linhas
acima. Uma ligação documentada também não demonstra intenção, influência, benefício ou ilícito.

## Contratos e grafo de interesses

O coletor BASE privilegia dumps anuais abertos do dados.gov.pt. Uma API de extração de grande
volume só é usada com autorização aplicável. Cada ficheiro fica associado a URL, instante de
recolha, tamanho, versão do parser e SHA-256.

O cruzamento automático aceita apenas:

1. HMAC exato de identificador fiscal protegido;
2. HMAC exato de NIPC de pessoa coletiva, com associação oficial;
3. nome normalizado exatamente igual, sempre com confiança inferior e revisão.

Não existe fuzzy matching. Homónimos, mudanças de firma, grupos económicos, familiares, doadores ou
beneficiários efetivos exigem um modelo de prova separado e autorização jurídica. O produto nunca
usa a expressão “rede de corrupção”; mostra relações documentadas e o seu tipo.

## Processos judiciais e ética pública

- O estado é enumeração controlada: investigação, inquérito, acusação, julgamento, absolvição,
  condenação, recurso, arquivamento ou outro estado documentado.
- “Investigado”, “arguido”, “acusado” e “condenado” não são sinónimos.
- A presunção de inocência é mostrada em todos os estados anteriores a decisão final condenatória.
- Cada mudança cria nova versão; uma absolvição, arquivamento ou recurso tem o mesmo destaque da
  acusação anterior.
- O título não contém linguagem de culpa além do que a decisão oficial estabelece.

## Discurso público vs. voto

Uma comparação é publicável apenas se o tema, o objeto normativo, a pessoa e o período coincidirem.
Alterações entre versões do texto são exclusões documentadas. O índice é:

`coerência = pares classificados como consistentes / pares comparáveis × 100`

O denominador, as exclusões, a janela temporal e a versão da metodologia aparecem junto ao valor.
Pares inconclusivos ou não comparáveis nunca contam contra ou a favor. A IA pode sugerir pares, mas
não publica a classificação.

## Notícias e relações internacionais

Feeds são aceites apenas de uma allowlist editorial pública. Guardam título, URL canónico, editor,
data, hash e entidades detetadas. Categorização automática permanece `PENDING`; uma notícia não é
reescrita como facto. Viagens, reuniões, lobbies e votações europeias exigem registo oficial do
organismo competente e o contexto institucional disponível.

## Direito de resposta e correção

Uma submissão recebe referência pública, timestamp UTC, hash do texto e hash do recibo de auditoria.
A equipa verifica identidade, capacidade de representação e correspondência ao registo. Se
publicada, a resposta aparece junto ao item alvo, sem apagar o original. Erros da plataforma são
corrigidos por uma nova versão; erros da fonte são assinalados e encaminhados ao editor oficial.

## Open Data

As exportações contêm apenas campos publicáveis, proveniência e versão do esquema. Excluem NIF
individual, contactos, dados de subscrição push, perfis do Guia do Cidadão, candidatos privados,
notas de revisão e segredos. Limites, paginação, licença e data de geração acompanham a resposta.

## Responsabilidades antes de produção

- entidade responsável pelo tratamento e contactos públicos;
- base jurídica por dataset, finalidade, retenção e destinatários;
- AIPD concluída e revista pelo encarregado de proteção de dados;
- política editorial, conflito de interesses dos revisores e mecanismo de recurso;
- backups, arquivo versionado, resposta a incidentes e testes de restauro;
- revisão periódica de fontes, allowlists, taxonomia e modelos;
- aconselhamento jurídico independente sobre RGPD, direitos de personalidade, segredo de justiça,
  reutilização de informação pública e responsabilidade editorial.
