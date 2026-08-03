import type {
  GovernmentPromise,
  PoliticianProfileData,
} from "@/types/domain";

const parliamentOpenData = {
  label: "Dados Abertos — Assembleia da República",
  url: "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx",
  publisher: "AR" as const,
};

export const demoPolitician: PoliticianProfileData = {
  id: "demo-politician",
  slug: "perfil-demonstrativo",
  name: "Perfil demonstrativo",
  role: "Deputado/a à Assembleia da República",
  party: "Partido não indicado",
  partyShort: "—",
  constituency: "Círculo eleitoral demonstrativo",
  legislature: "XVII Legislatura",
  attendanceRate: 94,
  nominalVotesAvailable: true,
  nominalVoteCount: 3,
  attendanceLabel: "Valor fictício para demonstrar a interface",
  verifiedAt: "Modo de demonstração",
  profileSource: parliamentOpenData,
  declarationSource: {
    label: "Entidade para a Transparência — enquadramento oficial",
    url: "https://www.tribunalconstitucional.pt/tc/ept/",
    publisher: "EPT",
  },
  isDemonstration: true,
  votes: [
    {
      id: "demo-vote-1",
      title: "Proposta legislativa demonstrativa sobre habitação",
      date: "2026-06-18",
      choice: "FAVOR",
      result: "Aprovada — dado fictício",
      initiativeNumber: "Exemplo 01/XVII",
      source: parliamentOpenData,
      isNominal: true,
    },
    {
      id: "demo-vote-2",
      title: "Proposta legislativa demonstrativa sobre saúde",
      date: "2026-05-30",
      choice: "AGAINST",
      result: "Rejeitada — dado fictício",
      initiativeNumber: "Exemplo 02/XVII",
      source: parliamentOpenData,
      isNominal: true,
    },
    {
      id: "demo-vote-3",
      title: "Resolução demonstrativa sobre transparência",
      date: "2026-05-16",
      choice: "ABSTENTION",
      result: "Aprovada — dado fictício",
      initiativeNumber: "Exemplo 03/XVII",
      source: parliamentOpenData,
      isNominal: true,
    },
  ],
};

export const demoPromises: GovernmentPromise[] = [
  {
    id: "demo-promise-1",
    title: "Medida demonstrativa para simplificar o acesso à habitação",
    area: "Habitação",
    status: "IN_PROGRESS",
    progress: 62,
    programmePage: "p. 47 (exemplo)",
    programmeSource: {
      label: "Programas do Governo — Assembleia da República",
      url: "https://www.parlamento.pt/ActividadeParlamentar/Paginas/Programas_do_Governo.aspx",
      publisher: "AR",
    },
    rationale:
      "Classificação meramente demonstrativa. Em produção, este campo só é publicado após ligação entre a medida e prova oficial.",
    lastReviewedAt: "Modo de demonstração",
    isDemonstration: true,
    evidence: [
      {
        id: "demo-evidence-1",
        legalReference: "Fonte DRE a associar",
        summary: "A plataforma exige um diploma oficial antes de validar o estado.",
        source: {
          label: "Diário da República",
          url: "https://diariodarepublica.pt/",
          publisher: "DRE",
        },
        publishedAt: "—",
      },
    ],
  },
  {
    id: "demo-promise-2",
    title: "Medida demonstrativa de reforço dos cuidados de saúde",
    area: "Saúde",
    status: "FULFILLED",
    progress: 100,
    programmePage: "p. 83 (exemplo)",
    programmeSource: {
      label: "Programas do Governo — Assembleia da República",
      url: "https://www.parlamento.pt/ActividadeParlamentar/Paginas/Programas_do_Governo.aspx",
      publisher: "AR",
    },
    rationale:
      "Estado fictício usado apenas para mostrar a apresentação de uma medida cumprida.",
    lastReviewedAt: "Modo de demonstração",
    isDemonstration: true,
    evidence: [
      {
        id: "demo-evidence-2",
        legalReference: "Fonte DRE a associar",
        summary: "Exemplo de evidência legal auditável.",
        source: {
          label: "Diário da República",
          url: "https://diariodarepublica.pt/",
          publisher: "DRE",
        },
        publishedAt: "—",
      },
    ],
  },
  {
    id: "demo-promise-3",
    title: "Medida demonstrativa para modernizar serviços públicos",
    area: "Administração Pública",
    status: "BROKEN",
    progress: 18,
    programmePage: "p. 112 (exemplo)",
    programmeSource: {
      label: "Programas do Governo — Assembleia da República",
      url: "https://www.parlamento.pt/ActividadeParlamentar/Paginas/Programas_do_Governo.aspx",
      publisher: "AR",
    },
    rationale:
      "Estado fictício. A versão real requer uma decisão humana fundamentada e publicada no histórico de auditoria.",
    lastReviewedAt: "Modo de demonstração",
    isDemonstration: true,
    evidence: [
      {
        id: "demo-evidence-3",
        legalReference: "Ausência de diploma confirmada por revisão",
        summary: "Em produção, a pesquisa, o período e o revisor ficam registados.",
        source: {
          label: "Pesquisa oficial no Diário da República",
          url: "https://diariodarepublica.pt/dr/pesquisa",
          publisher: "DRE",
        },
        publishedAt: "—",
      },
    ],
  },
  {
    id: "demo-promise-4",
    title: "Medida demonstrativa de mobilidade sustentável",
    area: "Transportes",
    status: "ABANDONED",
    progress: 8,
    programmePage: "p. 138 (exemplo)",
    programmeSource: {
      label: "Programas do Governo — Assembleia da República",
      url: "https://www.parlamento.pt/ActividadeParlamentar/Paginas/Programas_do_Governo.aspx",
      publisher: "AR",
    },
    rationale:
      "Estado fictício para validar contraste, filtros e acessibilidade da interface.",
    lastReviewedAt: "Modo de demonstração",
    isDemonstration: true,
    evidence: [
      {
        id: "demo-evidence-4",
        legalReference: "Deliberação ou relatório a associar",
        summary: "Nenhuma classificação real é feita a partir deste conteúdo de teste.",
        source: parliamentOpenData,
        publishedAt: "—",
      },
    ],
  },
];
