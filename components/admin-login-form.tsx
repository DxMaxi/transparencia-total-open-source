"use client";

import { FormEvent, useState } from "react";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

export function AdminLoginForm({ configured }: { configured: boolean }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!configured || busy) return;
    setBusy(true);
    setMessage(null);
    try {
      const supabase = createBrowserSupabaseClient();
      const redirectTo = new URL("/auth/confirmar", window.location.origin);
      redirectTo.searchParams.set("next", "/auth/mfa?next=/admin/revisao");
      const { error } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: {
          emailRedirectTo: redirectTo.toString(),
          shouldCreateUser: false,
        },
      });
      if (error) throw error;
      setMessage(
        "Se esta conta tiver convite ativo, receberá uma ligação de acesso. Verifique também o spam.",
      );
      setEmail("");
    } catch {
      // A mesma resposta evita revelar se um endereço pertence à equipa.
      setMessage(
        "Se esta conta tiver convite ativo, receberá uma ligação de acesso. Verifique também o spam.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="private-auth-form" onSubmit={submit}>
      <label htmlFor="staff-email">Email do convite</label>
      <input
        id="staff-email"
        name="email"
        type="email"
        autoComplete="email"
        required
        disabled={!configured || busy}
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <button className="button button--primary" type="submit" disabled={!configured || busy}>
        {busy ? "A enviar…" : "Receber ligação segura"}
      </button>
      {!configured ? (
        <p className="private-message private-message--error" role="alert">
          O acesso privado ainda não está configurado neste ambiente.
        </p>
      ) : null}
      {message ? (
        <p className="private-message" role="status">
          {message}
        </p>
      ) : null}
    </form>
  );
}
