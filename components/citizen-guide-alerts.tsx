"use client";

import { FormEvent, useMemo, useState } from "react";
import { BellIcon, CheckIcon, ExternalLinkIcon, ShieldCheckIcon } from "@/components/icons";
import { citizenAlertDemo } from "@/lib/v2-demo-data";

type IrsBracket = "isento" | "baixo" | "medio" | "alto" | "nao_indicar";

export function CitizenGuideAlerts() {
  const [irsBracket, setIrsBracket] = useState<IrsBracket>("nao_indicar");
  const [district, setDistrict] = useState("Lisboa");
  const [children, setChildren] = useState(0);
  const [dependants, setDependants] = useState(0);
  const [employment, setEmployment] = useState("nao_indicar");
  const [hasRun, setHasRun] = useState(false);

  const alerts = useMemo(
    () =>
      citizenAlertDemo.filter(
        (alert) =>
          (alert.districts.includes("Todos") || alert.districts.includes(district)) &&
          alert.profiles.includes(irsBracket),
      ),
    [district, irsBracket],
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setHasRun(true);
  }

  return (
    <section className="citizen-guide-grid" aria-labelledby="citizen-guide-title">
      <form className="citizen-profile-card" onSubmit={submit}>
        <div className="investigator-card__heading">
          <div>
            <span className="eyebrow">Perfil genérico</span>
            <h2 id="citizen-guide-title">O que pode mudar para si?</h2>
          </div>
          <ShieldCheckIcon />
        </div>
        <p className="privacy-first-note">
          Não pedimos nome, NIF, morada, rendimento exato ou filiação política. Esta demonstração corre apenas neste dispositivo.
        </p>

        <div className="citizen-form-grid">
          <label>
            Escalão genérico de IRS
            <select value={irsBracket} onChange={(event) => setIrsBracket(event.target.value as IrsBracket)}>
              <option value="nao_indicar">Prefiro não indicar</option>
              <option value="isento">Isento / sem retenção</option>
              <option value="baixo">Baixo</option>
              <option value="medio">Médio</option>
              <option value="alto">Alto</option>
            </select>
          </label>
          <label>
            Distrito
            <select value={district} onChange={(event) => setDistrict(event.target.value)}>
              <option>Lisboa</option>
              <option>Porto</option>
              <option>Braga</option>
              <option>Coimbra</option>
              <option>Faro</option>
              <option>Outro</option>
            </select>
          </label>
          <label>
            Filhos a cargo
            <input
              type="number"
              min="0"
              max="20"
              value={children}
              onChange={(event) => setChildren(Number(event.target.value))}
            />
          </label>
          <label>
            Outros dependentes
            <input
              type="number"
              min="0"
              max="20"
              value={dependants}
              onChange={(event) => setDependants(Number(event.target.value))}
            />
          </label>
          <label className="citizen-field-wide">
            Situação profissional genérica
            <select value={employment} onChange={(event) => setEmployment(event.target.value)}>
              <option value="nao_indicar">Prefiro não indicar</option>
              <option value="trabalhador_conta_outrem">Trabalho por conta de outrem</option>
              <option value="independente">Trabalho independente</option>
              <option value="reformado">Reformado/a</option>
              <option value="desempregado">Desempregado/a</option>
            </select>
          </label>
        </div>
        <button className="button button--primary" type="submit">Simular impactos verificados</button>
        <small>
          O motor real calcula por regras versionadas; a IA apenas traduz o resultado. Não é aconselhamento fiscal, jurídico ou financeiro.
        </small>
      </form>

      <div className="citizen-alert-panel" aria-live="polite">
        <div className="citizen-alert-panel__top">
          <div>
            <span className="eyebrow">Guia Neutro do Cidadão</span>
            <h2>{hasRun ? `${alerts.length} impactos demonstrativos` : "Pronto para analisar"}</h2>
          </div>
          <span className="v2-demo-chip">IA não executada</span>
        </div>

        {!hasRun ? (
          <div className="guide-empty-state">
            <BellIcon />
            <strong>Escolha apenas categorias genéricas.</strong>
            <p>O painel separa resultado calculado, explicação simples, incertezas e fonte oficial.</p>
          </div>
        ) : alerts.length ? (
          <div className="citizen-alert-list">
            {alerts.map((alert) => (
              <article key={alert.id} className="citizen-alert-card">
                <div className="citizen-alert-card__heading">
                  <span><BellIcon /> {alert.category}</span>
                  <span className="verified-chip"><CheckIcon /> Regra demonstrativa</span>
                </div>
                <h3>{alert.title}</h3>
                <div className="deterministic-result">
                  <span>Resultado do motor de regras</span>
                  <strong>{alert.deterministicResult}</strong>
                </div>
                <div className="ai-explanation">
                  <span>Explicação simples que a IA poderia produzir</span>
                  <p>{alert.plainSummary}</p>
                </div>
                <div className="citizen-alert-card__footer">
                  <span>Vigência: {alert.effectiveDate}</span>
                  <a href={alert.source.url} target="_blank" rel="noreferrer">
                    {alert.source.publisher} · fonte oficial <ExternalLinkIcon />
                  </a>
                </div>
              </article>
            ))}
            <div className="guide-uncertainty">
              <strong>O que não foi possível determinar</strong>
              <p>
                Este protótipo não contém tabelas legais reais. Nenhum valor individual é inferido a partir dos dados escolhidos.
              </p>
            </div>
          </div>
        ) : (
          <div className="guide-empty-state">
            <ShieldCheckIcon />
            <strong>Sem impacto demonstrativo aplicável.</strong>
            <p>Isto não significa ausência de impacto real; significa apenas que não existem regras verificadas nesta amostra.</p>
          </div>
        )}
      </div>
    </section>
  );
}
