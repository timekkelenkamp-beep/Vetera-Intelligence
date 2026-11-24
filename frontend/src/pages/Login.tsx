import * as React from "react";
import { motion } from "motion/react";
import { Lock, ArrowRight, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { tileStyle } from "@/lib/modules";
import { Button, Notice } from "@/components/ui/primitives";

export default function Login({ configured, onDone }: { configured: boolean; onDone: () => void }) {
  const [pw, setPw] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/auth/login", { password: pw });
      onDone();
    } catch (x: any) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="relative isolate flex min-h-screen items-center justify-center bg-white px-4">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10" style={{ background: "radial-gradient(35% 45% at 30% 30%, rgba(31,111,95,0.16), transparent 70%), radial-gradient(30% 40% at 72% 28%, rgba(10,124,255,0.10), transparent 70%), radial-gradient(28% 38% at 58% 78%, rgba(240,138,0,0.08), transparent 70%)" }} />
      <motion.form onSubmit={submit} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="w-full max-w-[380px] rounded-3xl border border-line bg-white/85 p-8 shadow-[0_24px_80px_rgba(0,0,0,0.10)] backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-[16px] shadow-[0_6px_20px_-6px_rgba(0,0,0,0.35)]" style={tileStyle("#1f4e46")}>
          <svg viewBox="0 0 64 64" className="h-7 w-7"><path d="M14 18l18 30 18-30" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </div>
        <h1 className="mt-5 text-center text-[22px] font-semibold tracking-tightest">Vetera Intelligence</h1>
        <p className="mt-1 text-center text-[13px] text-ink-muted">Log in om verder te gaan</p>
        {!configured ? (
          <Notice tone="caution" icon={<AlertTriangle />} className="mt-6">Deze installatie heeft nog geen wachtwoord en is daarom geblokkeerd. Stel <code>VETERA_APP_PASSWORD</code> in bij de hostingdienst.</Notice>
        ) : (
          <>
            <div className="relative mt-6">
              <Lock className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
              <input id="password" type="password" autoFocus autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Wachtwoord" aria-label="Wachtwoord" className="h-11 w-full rounded-xl border border-line-strong bg-white pl-10 pr-3 text-[14.5px] focus:border-accent focus:shadow-ring focus:outline-none" />
            </div>
            {err && <p className="mt-2 text-[12.5px] text-negative">{err}</p>}
            <Button type="submit" variant="primary" size="lg" className="mt-4 w-full" loading={busy} disabled={!pw}>Inloggen <ArrowRight className="h-4 w-4" /></Button>
          </>
        )}
      </motion.form>
    </div>
  );
}
