"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

type MfaState = {
  factorId: string;
  qrCode: string | null;
  secret: string | null;
  existing: boolean;
};

function safeNext(value: string): string {
  return value.startsWith("/admin/") && !value.startsWith("//")
    ? value
    : "/admin/revisao";
}

export function AdminMfaSetup({ configured, next }: { configured: boolean; next: string }) {
  const router = useRouter();
  const prepared = useRef(false);
  const [state, setState] = useState<MfaState | null>(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState(
    configured
      ? "A validar a conta…"
      : "O acesso privado ainda não está configurado neste ambiente.",
  );
  const [busy, setBusy] = useState(configured);

  useEffect(() => {
    if (!configured || prepared.current) return;
    prepared.current = true;

    async function prepare() {
      const supabase = createBrowserSupabaseClient();
      const claims = await supabase.auth.getClaims();
      if (claims.error || !claims.data?.claims) {
        router.replace("/auth/entrar?erro=sessao");
        return;
      }
      const session = await supabase.auth.getSession();
      const accessToken = session.data.session?.access_token;
      if (!accessToken) {
        router.replace("/auth/entrar?erro=sessao");
        return;
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
      if (!apiUrl) throw new Error("API privada não configurada");
      const staffResponse = await fetch(`${apiUrl}/api/v1/editorial/session`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      });
      if (staffResponse.status === 401 || staffResponse.status === 403) {
        await supabase.auth.signOut({ scope: "local" });
        router.replace("/auth/entrar?erro=sem-acesso");
        return;
      }
      if (!staffResponse.ok) throw new Error("Não foi possível validar o acesso editorial");

      const assurance = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
      if (assurance.error) throw assurance.error;
      if (assurance.data.currentLevel === "aal2") {
        router.replace(safeNext(next));
        router.refresh();
        return;
      }

      const factors = await supabase.auth.mfa.listFactors();
      if (factors.error) throw factors.error;
      const verifiedFactor = factors.data.totp[0];
      if (verifiedFactor) {
        setState({
          factorId: verifiedFactor.id,
          qrCode: null,
          secret: null,
          existing: true,
        });
        setMessage("Introduza o código atual da sua aplicação autenticadora.");
      } else {
        const staleTotpFactors = factors.data.all.filter(
          (factor) => factor.factor_type === "totp" && factor.status === "unverified",
        );
        for (const factor of staleTotpFactors) {
          const removal = await supabase.auth.mfa.unenroll({ factorId: factor.id });
          if (removal.error) throw removal.error;
        }
        const enrollment = await supabase.auth.mfa.enroll({
          factorType: "totp",
          friendlyName: "Transparência Total",
          issuer: "Transparência Total",
        });
        if (enrollment.error) throw enrollment.error;
        setState({
          factorId: enrollment.data.id,
          qrCode: `data:image/svg+xml;utf-8,${encodeURIComponent(enrollment.data.totp.qr_code)}`,
          secret: enrollment.data.totp.secret,
          existing: false,
        });
        setMessage("Digitalize o código QR e confirme com o código de seis algarismos.");
      }
      setBusy(false);
    }

    prepare().catch(() => {
      setBusy(false);
      setMessage("Não foi possível preparar o segundo fator. Tente novamente.");
    });
  }, [configured, next, router]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state || busy) return;
    setBusy(true);
    setMessage("A confirmar o segundo fator…");
    try {
      const supabase = createBrowserSupabaseClient();
      const challenge = await supabase.auth.mfa.challenge({ factorId: state.factorId });
      if (challenge.error) throw challenge.error;
      const verification = await supabase.auth.mfa.verify({
        factorId: state.factorId,
        challengeId: challenge.data.id,
        code: code.replace(/\s/g, ""),
      });
      if (verification.error) throw verification.error;
      router.replace(safeNext(next));
      router.refresh();
    } catch {
      setMessage("O código não foi aceite. Confirme a hora do dispositivo e tente novamente.");
      setBusy(false);
    }
  }

  return (
    <div className="private-mfa-flow">
      <p className="private-message" role="status">
        {message}
      </p>
      {state?.qrCode ? (
        <div className="private-mfa-enrolment">
          {/* O QR contém o segredo TOTP e nunca é enviado para o backend editorial. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={state.qrCode} alt="Código QR para configurar a aplicação autenticadora" />
          <div>
            <strong>Se não conseguir digitalizar</strong>
            <p>Introduza manualmente esta chave na aplicação autenticadora:</p>
            <code>{state.secret}</code>
          </div>
        </div>
      ) : null}
      {state ? (
        <form className="private-auth-form" onSubmit={verify}>
          <label htmlFor="mfa-code">Código de seis algarismos</label>
          <input
            id="mfa-code"
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            minLength={6}
            maxLength={6}
            required
            disabled={busy}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          />
          <button className="button button--primary" type="submit" disabled={busy || code.length !== 6}>
            {state.existing ? "Confirmar acesso" : "Ativar segundo fator"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
