"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

export function AdminSignOut() {
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function signOut() {
    setBusy(true);
    try {
      await createBrowserSupabaseClient().auth.signOut({ scope: "local" });
    } finally {
      router.replace("/auth/entrar");
      router.refresh();
    }
  }

  return (
    <button className="private-link-button" type="button" disabled={busy} onClick={signOut}>
      {busy ? "A terminar…" : "Terminar sessão"}
    </button>
  );
}
