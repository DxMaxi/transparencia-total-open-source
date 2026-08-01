import type { Metadata } from "next";
import { DemoBanner } from "@/components/demo-banner";
import { RightOfReplyForm } from "@/components/right-of-reply-form";

export const metadata: Metadata = {
  title: "Direito de resposta auditável",
  description: "Canal de resposta e retificação com histórico, timestamp e SHA-256.",
};

export default function RightOfReplyPage() {
  return (
    <main className="page-shell shell">
      <DemoBanner />
      <div className="page-heading page-heading--wide">
        <span className="eyebrow">Compliance V3</span>
        <h1>Responder sem reescrever o passado.</h1>
        <p>
          Contestações oficiais são anexadas ao facto correspondente. O original, a resposta, as decisões de revisão e cada alteração mantêm a sua própria impressão digital.
        </p>
      </div>
      <RightOfReplyForm />
    </main>
  );
}
