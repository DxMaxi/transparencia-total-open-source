import {
  ExternalLinkIcon,
  LandmarkIcon,
  ShieldCheckIcon,
} from "@/components/icons";

const officialServices = [
  {
    title: "ePortugal",
    description: "Informação e serviços públicos para cidadãos e empresas.",
    href: "https://eportugal.gov.pt/",
    label: "Portal oficial de serviços públicos",
  },
  {
    title: "Diário da República",
    description: "Diplomas legais, versões consolidadas e datas de entrada em vigor.",
    href: "https://diariodarepublica.pt/",
    label: "Consultar legislação oficial",
  },
  {
    title: "Portal das Finanças",
    description: "Obrigações, declarações, pagamentos e simuladores fiscais oficiais.",
    href: "https://www.portaldasfinancas.gov.pt/",
    label: "Abrir Portal das Finanças",
  },
  {
    title: "Segurança Social Direta",
    description: "Prestações, contribuições e informação pessoal autenticada.",
    href: "https://app.seg-social.pt/sso/login",
    label: "Abrir Segurança Social Direta",
  },
];

export function CitizenGuideAlerts() {
  return (
    <section className="citizen-guide-public" aria-labelledby="citizen-guide-title">
      <article className="citizen-guide-principle card">
        <ShieldCheckIcon />
        <div>
          <span className="eyebrow">Informação responsável</span>
          <h2 id="citizen-guide-title">O cálculo oficial pertence à entidade competente</h2>
          <p>
            Impostos, prestações e direitos dependem de dados pessoais, vigência e exceções.
            Por isso, esta página encaminha para os serviços públicos que mantêm as regras e
            os simuladores oficiais, sem recolher informação sobre o visitante.
          </p>
        </div>
      </article>

      <div className="official-service-grid">
        {officialServices.map((service) => (
          <a
            className="official-service-card card"
            href={service.href}
            target="_blank"
            rel="noreferrer noopener"
            key={service.href}
          >
            <LandmarkIcon />
            <span className="eyebrow">Serviço oficial</span>
            <h2>{service.title}</h2>
            <p>{service.description}</p>
            <strong>{service.label} <ExternalLinkIcon /></strong>
          </a>
        ))}
      </div>

      <aside className="citizen-guide-safety card">
        <h2>Quando precisar de uma decisão individual</h2>
        <p>
          Confirme sempre a informação no serviço público competente ou junto de um
          profissional habilitado. Este projeto não presta aconselhamento jurídico, fiscal
          ou financeiro e não recolhe dados para criar perfis políticos.
        </p>
      </aside>
    </section>
  );
}
