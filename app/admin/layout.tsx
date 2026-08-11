import type { Metadata } from "next";
import Link from "next/link";
import { AdminSignOut } from "@/components/admin-sign-out";
import { getEditorialContext } from "@/lib/editorial-api";

export const metadata: Metadata = {
  title: "Painel editorial",
  robots: { index: false, follow: false, noarchive: true },
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const { staff } = await getEditorialContext();
  return (
    <div className="private-route-frame admin-workspace">
      <header className="admin-header">
        <div className="admin-header__brand">
          <span aria-hidden="true">TT</span>
          <div>
            <strong>Painel editorial</strong>
            <small>Privado · MFA ativo</small>
          </div>
        </div>
        <nav aria-label="Navegação do painel">
          <Link href="/admin/revisao">Revisão</Link>
          <Link href="/admin/revisao/parlamento">Parlamento</Link>
          <Link href="/admin/revisao/novo">Novo processo</Link>
          <Link href="/auth/mfa?next=/admin/revisao">Segurança</Link>
        </nav>
        <div className="admin-identity">
          <span>
            {staff.public_alias} · {staff.role === "ADMIN" ? "Administrador" : "Revisor"}
          </span>
          <AdminSignOut />
        </div>
      </header>
      <main className="admin-main">{children}</main>
      <footer className="admin-footer">
        Aprovação editorial não publica dados. Todas as decisões ficam no histórico imutável.
      </footer>
    </div>
  );
}
