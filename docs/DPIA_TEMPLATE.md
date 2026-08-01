# Modelo de AIPD — dados de titulares de cargos públicos

Este é um guião técnico para uma Avaliação de Impacto sobre a Proteção de Dados. Deve ser preenchido
e validado pela entidade responsável, pelo encarregado de proteção de dados e por assessoria
jurídica antes da ingestão de dados reais. Não é parecer jurídico.

## 1. Identificação

- Responsável pelo tratamento e contactos:
- Encarregado de proteção de dados:
- Versão, data e aprovadores:
- Datasets, países, períodos e grupos abrangidos:
- Processadores, subcontratantes e transferências internacionais:

## 2. Finalidade e necessidade

Para cada operação, documentar finalidade cívica concreta, base jurídica proposta, expectativa
razoável do titular e alternativa menos intrusiva. “É público” não basta como justificação para
recolher, cruzar, conservar ou republicar.

| Operação | Campos | Fonte | Finalidade | Base jurídica | Retenção | Público? |
|---|---|---|---|---|---|---|
| Cargo público |  |  |  |  |  |  |
| Contrato |  |  |  |  |  |  |
| Associação societária |  |  |  |  |  |  |
| Processo/decisão |  |  |  |  |  |  |
| Direito de resposta |  |  |  |  |  |  |

## 3. Fluxo e separação de zonas

Mapear fonte, descarga, armazenamento bruto, staging, correspondência, revisão, publicação,
exportação, arquivo e eliminação. Confirmar que candidatos privados e identificadores protegidos não
chegam ao frontend, telemetria, logs, fornecedores de IA ou exportações.

## 4. Minimização

- Lista positiva de cargos e períodos de relevância pública.
- Excluir moradas, contactos pessoais, assinaturas, localização exata, dados de menores e categorias
  especiais salvo necessidade legal documentada.
- Comparar NIF individual por HMAC, com segredo separado e rotação; não o publicar.
- Preferir ligação e metadados ao documento em vez de republicação integral.
- Usar perfil genérico e efémero no Guia do Cidadão; não criar perfil político ou comportamental.

## 5. Riscos a avaliar

Pontuar probabilidade e severidade antes/depois dos controlos para: homónimo ou falso positivo;
acusação implícita por design do grafo; dado judicial desatualizado; reidentificação por combinação;
scraping massivo da API; exposição de relações familiares; alteração da fonte; prompt injection;
alucinação; enviesamento de cobertura; abuso do direito de resposta; ataque à cadeia de fornecimento;
perda de originais; acesso interno indevido e retenção excessiva.

## 6. Controlos e evidência de eficácia

| Controlo | Responsável | Teste | Frequência | Evidência |
|---|---|---|---|---|
| Dupla revisão de relações de alto risco |  |  |  |  |
| Estado `PENDING_REVIEW` por omissão |  |  |  |  |
| HMAC e gestão de segredos |  |  |  |  |
| Filtro Open Data |  |  |  |  |
| Atualização de estados judiciais |  |  |  |  |
| Direito de resposta e recurso |  |  |  |  |
| Testes de IA e validação de citações |  |  |  |  |
| Logs sem conteúdo protegido |  |  |  |  |
| Restauro de backup e arquivo imutável |  |  |  |  |

## 7. Direitos, transparência e retenção

Definir avisos públicos, canal de acesso/retificação/oposição/limitação, autenticação do requerente,
prazos, escalamento e comunicação à fonte. Fixar retenção por classe e regras especiais para fim de
mandato, absolvição, arquivamento, correção e litígio. O histórico auditável não elimina a obrigação
de restringir ou apagar dados quando juridicamente exigido.

## 8. Decisão residual

- Riscos residuais altos e consulta prévia necessária:
- Restrições de lançamento:
- Data de reavaliação e gatilhos (nova fonte, novo cruzamento, novo modelo, incidente ou mudança
  legal):
- Decisão final, fundamentos e assinaturas:

