"use client";

import { useState } from "react";
import { LandmarkIcon, MenuIcon } from "@/components/icons";

const navItems = [
  { href: "/politicos", label: "Políticos" },
  { href: "/atividade-parlamentar", label: "Parlamento" },
  { href: "/promessas", label: "Promessómetro" },
  { href: "/guia-cidadao", label: "Guia do Cidadão" },
  { href: "/metodologia", label: "Metodologia" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="trust-strip">
        <div className="shell trust-strip__inner">
          <span>Prova documental</span>
          <span>Histórico imutável</span>
          <span>Revisão humana</span>
        </div>
      </div>
      <header className="site-header">
        <div className="shell site-header__inner">
          <a href="/" className="brand" aria-label="Transparência Total — início">
            <span className="brand__mark"><LandmarkIcon /></span>
            <span className="brand__text">
              <strong>Transparência</strong>
              <span>Total <small>/ Fator Cívico</small></span>
            </span>
          </a>

          <nav className="desktop-nav" aria-label="Navegação principal">
            {navItems.map((item) => (
              <a key={item.href} href={item.href}>{item.label}</a>
            ))}
          </nav>

          <div className="header-actions">
            <button
              className="icon-button mobile-menu-button"
              type="button"
              aria-label={open ? "Fechar menu" : "Abrir menu"}
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              <MenuIcon />
            </button>
          </div>
        </div>
        {open && (
          <nav className="mobile-nav shell" aria-label="Navegação móvel">
            {navItems.map((item) => (
              <a key={item.href} href={item.href} onClick={() => setOpen(false)}>
                {item.label}
              </a>
            ))}
          </nav>
        )}
      </header>
    </>
  );
}
