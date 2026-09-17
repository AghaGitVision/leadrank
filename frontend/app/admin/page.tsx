"use client";

import { useEffect, useState } from "react";
import { api, SuppressionEntry } from "@/lib/api";

export default function AdminPage() {
  const [entries, setEntries] = useState<SuppressionEntry[]>([]);
  const [domain, setDomain] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .suppressionList()
      .then(setEntries)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  async function add() {
    const d = domain.trim().toLowerCase();
    if (!d) return;
    setBusy(true);
    setError(null);
    try {
      await api.addSuppression(d, reason.trim());
      setDomain("");
      setReason("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(d: string) {
    setError(null);
    try {
      await api.removeSuppression(d);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-hi">Do-not-contact list</h1>
        <p className="mt-1 max-w-xl text-sm leading-relaxed text-lo">
          Domains here are dropped from every future run, before scoring — for opt-outs,
          existing customers, or anyone who should never show up in a queue again.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded border border-band-d/40 bg-band-d/10 px-4 py-3 text-sm text-band-d">
          {error}
        </div>
      )}

      <section className="mb-8 rounded border border-line bg-surface-1 p-4">
        <h2 className="mb-3 text-sm font-medium text-hi">Add a domain</h2>
        <div className="flex flex-wrap gap-2">
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="acme.com"
            className="min-w-[180px] flex-1 rounded border border-line bg-surface-0 px-3 py-2 text-sm text-hi placeholder:text-lo"
          />
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Reason (optional) — e.g. opted out"
            className="min-w-[220px] flex-[2] rounded border border-line bg-surface-0 px-3 py-2 text-sm text-hi placeholder:text-lo"
          />
          <button
            onClick={add}
            disabled={busy || !domain.trim()}
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-surface-0 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Suppress
          </button>
        </div>
      </section>

      <section className="rounded border border-line bg-surface-1">
        {entries.length === 0 ? (
          <p className="p-6 text-sm text-lo">Nothing suppressed yet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-lo">
                <th className="px-4 py-2 font-normal">Domain</th>
                <th className="px-4 py-2 font-normal">Reason</th>
                <th className="px-4 py-2 font-normal">Added</th>
                <th className="px-4 py-2 font-normal" />
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.domain} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2 text-hi">{e.domain}</td>
                  <td className="px-4 py-2 text-lo">{e.reason || "—"}</td>
                  <td className="px-4 py-2 text-lo">
                    {new Date(e.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => remove(e.domain)}
                      className="text-xs text-lo hover:text-band-d"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
