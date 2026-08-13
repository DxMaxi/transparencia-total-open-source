import type { Metadata } from "next";
import { RightOfReplyForm } from "@/components/right-of-reply-form";

export const metadata: Metadata = {
  title: "Direito de resposta auditável",
  description: "Canal de resposta e retificação com histórico, timestamp e SHA-256.",
  alternates: { canonical: "/direito-de-resposta" },
};

export default function RightOfReplyPage() {
  return (
    <main className="page-shell shell">
      <div className="page-heading page-heading--wide">
        <span className="eyebrow">Retificação e contraditório</span>
        <h1>Responder sem reescrever o passado.</h1>
        <p>
          Contestações oficiais são anexadas ao facto correspondente. O original, a resposta, as decisões de revisão e cada alteração mantêm a sua própria impressão digital.
        </p>
      </div>
      <RightOfReplyForm />
    </main>
  );
}
