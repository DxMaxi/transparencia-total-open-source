import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Acesso privado",
  robots: { index: false, follow: false, noarchive: true },
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <div className="private-route-frame">{children}</div>;
}
