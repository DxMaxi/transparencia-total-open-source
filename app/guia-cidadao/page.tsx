import type { Metadata } from "next";
import { CitizenGuideAlerts } from "@/components/citizen-guide-alerts";
import { DemoBanner } from "@/components/demo-banner";

export const metadata: Metadata = {
  title: "Guia Neutro do Cidadão",
  description: "Simulador privado de impactos legais com regras verificadas e explicação simples.",
};

export default function CitizenGuidePage() {
  return (
    <main className="page-shell shell citizen-guide-page">
      <DemoBanner />
      <div className="page-heading page-heading--wide citizen-guide-heading">
        <span className="eyebrow">Impacto real, linguagem simples</span>
        <h1>A lei muda.<br /><span>Veja o que pode tocar-lhe.</span></h1>
        <p>
          O cálculo pertence a regras jurídicas versionadas; a IA só explica o resultado e deve abster-se quando faltam dados. Nenhum perfil político é criado.
        </p>
      </div>
      <CitizenGuideAlerts />
    </main>
  );
}
