import Link from "next/link";
import { AdminMfaSetup } from "@/components/admin-mfa-setup";
import { getSupabasePublicConfig } from "@/lib/supabase/config";

function safeNext(value: string | undefined): string {
  return value?.startsWith("/admin/") && !value.startsWith("//")
    ? value
    : "/admin/revisao";
}

export default async function StaffMfaPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  return (
    <main className="private-auth-page">
      <section className="private-auth-card private-auth-card--wide" aria-labelledby="mfa-title">
        <p className="eyebrow">Segunda verificação</p>
        <h1 id="mfa-title">Proteja as decisões editoriais</h1>
        <p>
          Use uma aplicação autenticadora compatível com TOTP. O código muda a cada 30 segundos e
          é obrigatório antes de consultar ou alterar dados privados.
        </p>
        <AdminMfaSetup
          configured={getSupabasePublicConfig() !== null}
          next={safeNext(next)}
        />
        <Link className="private-back-link" href="/auth/entrar">
          Recomeçar o acesso
        </Link>
      </section>
    </main>
  );
}
