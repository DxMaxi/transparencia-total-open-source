import type {
  EvidenceSource,
  InterestEdgeData,
  InterestGraphDataset,
  InterestNodeData,
  SpeechVoteComparisonData,
} from "@/types/public-data";

const parliamentSource: EvidenceSource = {
  label: "Assembleia da República — Dados Abertos",
  url: "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
  publisher: "AR",
  sha256: "hash-demonstrativo-ar",
};

const baseSource: EvidenceSource = {
  label: "Portal BASE / dados.gov.pt — contratos públicos",
  url: "https://dados.gov.pt/pt/datasets/contratos-publicos-portal-base-impic-contratos-de-2012-a-2025/",
  publisher: "BASE",
  sha256: "hash-demonstrativo-base",
};

const transparencySource: EvidenceSource = {
  label: "Entidade para a Transparência — enquadramento oficial",
  url: "https://www.tribunalconstitucional.pt/tc/ept/",
  publisher: "EPT",
  sha256: "hash-demonstrativo-ept",
};

export const interestGraphDemo: InterestGraphDataset = {
  isDemonstration: true as const,
  nodes: [
    {
      id: "person-demo",
      position: { x: 40, y: 130 },
      data: {
        label: "Titular demonstrativo",
        subtitle: "Pessoa / cargo político",
        kind: "person",
        verified: true,
        isDemonstration: true,
      } satisfies InterestNodeData,
    },
    {
      id: "public-body-demo",
      position: { x: 330, y: 25 },
      data: {
        label: "Entidade pública demonstrativa",
        subtitle: "Cargo exercido",
        kind: "public",
        verified: true,
        isDemonstration: true,
      } satisfies InterestNodeData,
    },
    {
      id: "company-demo",
      position: { x: 330, y: 235 },
      data: {
        label: "Sociedade demonstrativa",
        subtitle: "Empresa privada",
        kind: "company",
        verified: true,
        isDemonstration: true,
      } satisfies InterestNodeData,
    },
    {
      id: "contract-demo",
      position: { x: 635, y: 130 },
      data: {
        label: "Contrato BASE — exemplo",
        subtitle: "€110 500 · dado fictício",
        kind: "contract",
        verified: true,
        isDemonstration: true,
      } satisfies InterestNodeData,
    },
  ],
  edges: [
    {
      id: "office-demo",
      source: "person-demo",
      target: "public-body-demo",
      label: "Cargo público",
      data: {
        label: "Exerceu cargo público",
        period: "2024–2026 · exemplo",
        year: 2026,
        party: "Não indicado",
        reviewState: "Revisto",
        source: parliamentSource,
        isDemonstration: true,
      } satisfies InterestEdgeData,
    },
    {
      id: "board-demo",
      source: "person-demo",
      target: "company-demo",
      label: "Órgão social",
      data: {
        label: "Relação societária demonstrativa",
        period: "até 2023 · exemplo",
        year: 2023,
        party: "Não indicado",
        company: "Sociedade demonstrativa",
        reviewState: "Revisto",
        source: transparencySource,
        isDemonstration: true,
      } satisfies InterestEdgeData,
    },
    {
      id: "contract-party-demo",
      source: "public-body-demo",
      target: "contract-demo",
      label: "Adjudicante",
      data: {
        label: "Entidade adjudicante demonstrativa",
        period: "2026 · exemplo",
        year: 2026,
        party: "Não indicado",
        amount: 110500,
        reviewState: "Revisto",
        source: baseSource,
        isDemonstration: true,
      } satisfies InterestEdgeData,
    },
    {
      id: "contractor-demo",
      source: "company-demo",
      target: "contract-demo",
      label: "Adjudicatária",
      data: {
        label: "Entidade adjudicatária demonstrativa",
        period: "2026 · exemplo",
        year: 2026,
        party: "Não indicado",
        amount: 110500,
        company: "Sociedade demonstrativa",
        reviewState: "Revisto",
        source: baseSource,
        isDemonstration: true,
      } satisfies InterestEdgeData,
    },
  ],
};

export const speechVoteDemo: SpeechVoteComparisonData = {
  isDemonstration: true as const,
  subject: "Medida legislativa demonstrativa sobre transparência contratual",
  statement: {
    quote: "Defendemos a publicação de informação contratual em formatos abertos.",
    speaker: "Titular demonstrativo",
    date: "12 jun. 2026 · exemplo",
    source: parliamentSource,
  },
  vote: {
    choice: "A FAVOR",
    initiative: "Exemplo 04/XVII",
    date: "18 jun. 2026 · exemplo",
    source: parliamentSource,
  },
  comparison: {
    outcome: "CONSISTENT",
    score: 100,
    comparablePairs: 1,
    totalStatements: 3,
    methodologyVersion: "coerencia-v2-demo",
    rationale:
      "O texto demonstrativo e o sentido de voto referem a mesma matéria e direção. Dois enunciados foram excluídos por não serem comparáveis.",
  },
};

export const citizenAlertDemo = [
  {
    id: "impact-tax-demo",
    category: "Impostos",
    districts: ["Todos"],
    profiles: ["baixo", "medio", "alto"],
    title: "Alteração fiscal demonstrativa",
    deterministicResult: "Sem valor calculável: falta uma tabela oficial associada.",
    plainSummary:
      "A interface mostraria apenas o resultado produzido por uma regra fiscal versionada e revista.",
    effectiveDate: "Data a confirmar no diploma",
    source: {
      label: "Diário da República — diploma a associar",
      url: "https://diariodarepublica.pt/",
      publisher: "DRE",
      sha256: "hash-demonstrativo-dre-1",
    },
    isDemonstration: true as const,
  },
  {
    id: "impact-health-demo",
    category: "Saúde",
    districts: ["Lisboa", "Porto", "Braga"],
    profiles: ["isento", "baixo", "medio", "alto", "nao_indicar"],
    title: "Alerta local demonstrativo de serviço público",
    deterministicResult: "Possível impacto regional; nenhum efeito individual quantificado.",
    plainSummary:
      "O alerta real indicaria concelho, período, serviço afetado e documento oficial de suporte.",
    effectiveDate: "Período demonstrativo",
    source: {
      label: "SNS — informação oficial a associar",
      url: "https://www.sns.gov.pt/",
      publisher: "SNS",
      sha256: "hash-demonstrativo-sns",
    },
    isDemonstration: true as const,
  },
];

export const v2OfficialSources = { parliamentSource, baseSource, transparencySource };
