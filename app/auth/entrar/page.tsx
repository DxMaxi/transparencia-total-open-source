import Link from "next/link";
import { AdminLoginForm } from "@/components/admin-login-form";
import { getSupabasePublicConfig } from "@/lib/supabase/config";

const ERROR_MESSAGES: Record<string, string> = {
  configuracao: "O acesso privado ainda não está configurado neste ambiente.",
  sessao: "A ligação de acesso expirou ou já foi utilizada. Peça uma nova.",
  "sem-acesso": "Esta conta não tem autorização editorial ativa.",
  confirmacao: "Não foi possível confirmar a ligação de acesso. Peça uma nova.",
};

export default async function StaffLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ erro?: string }>;
}) {
  const { erro } = await searchParams;
  const configured = getSupabasePublicConfig() !== null;

  return (
    <main className="private-auth-page">
      <section className="private-auth-card" aria-labelledby="private-login-title">
        <div className="private-auth-brand">
          <span aria-hidden="true">TT</span>
          <div>
            <strong>Transparência Total</strong>
            <small>Painel privado</small>
          </div>
        </div>
        <p className="eyebrow">Acesso reservado</p>
        <h1 id="private-login-title">Administração e revisão editorial</h1>
        <p>
          Apenas contas convidadas podem entrar. O acesso exige uma ligação por email e um segundo
          fator de autenticação.
        </p>
        {erro && ERROR_MESSAGES[erro] ? (
          <p className="private-message private-message--error" role="alert">
            {ERROR_MESSAGES[erro]}
          </p>
        ) : null}
        <AdminLoginForm configured={configured} />
        <aside className="private-principle-note">
          <strong>Aprovar não é publicar</strong>
          <p>
            Todas as recolhas permanecem privadas até existir uma decisão humana e um mecanismo de
            publicação específico para o respetivo domínio.
          </p>
        </aside>
        <Link className="private-back-link" href="/">
          Voltar ao site público
        </Link>
      </section>
    </main>
  );
}
