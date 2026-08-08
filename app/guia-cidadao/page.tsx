import type { Metadata } from "next";
import { CitizenGuideAlerts } from "@/components/citizen-guide-alerts";

export const metadata: Metadata = {
  title: "Guia Neutro do Cidadão",
  description: "Guia responsável para consultar legislação e serviços públicos oficiais.",
};

export default function CitizenGuidePage() {
  return (
    <main className="page-shell shell citizen-guide-page">
      <div className="page-heading page-heading--wide citizen-guide-heading">
        <span className="eyebrow">Fontes certas, limites claros</span>
        <h1>Informação pública.<br /><span>Sem falsas certezas.</span></h1>
        <p>
          Encontre os serviços oficiais adequados para legislação, impostos, prestações e
          procedimentos administrativos. Para situações pessoais, use sempre a entidade competente.
        </p>
      </div>
      <CitizenGuideAlerts />
    </main>
  );
}
