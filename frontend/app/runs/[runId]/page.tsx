"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  Explain,
  Lead,
  LearningProposal,
  Run,
  api,
  money,
  quadrantLabel,
} from "@/lib/api";
import { BandChip, ConfidenceBar, QuadrantGrid, Waterfall } from "@/components/Explain";

const BANDS = ["A", "B", "C", "D"];

export default function TriagePage({ params }: { params: { runId: string } }) {
  const { runId } = params;

  const [run, setRun] = useState<Run | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState(0);
  const [detail, setDetail] = useState<Explain | null>(null);
  const [bands, setBands] = useState<string[]>([]);
  const [quadrant, setQuadrant] = useState("");
  const [state, setState] = useState("pending");
  const [learning, setLearning] = useState<{
    eligible: boolean;
    reason: string;
    sample_size: number;
    proposals: LearningProposal[];
  } | null>(null);
  const [alerts, setAlerts] = useState<{ id: string; kind: string; detail: string; severity: string }[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // --- run progress over SSE ------------------------------------------------
  useEffect(() => {
    api.run(runId).then(setRun).catch(() => {});
    const es = new EventSource(`${API_BASE}/api/v1/runs/${runId}/events`);
    es.onmessage = (ev) => {
      const payload = JSON.parse(ev.data);
      setRun((prev) => (prev ? { ...prev, ...payload } : prev));
      if (payload.status === "complete" || payload.status === "failed") es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId]);

  const loadLeads = useCallback(async () => {
    const res = await api.leads(runId, {
      limit: 300,
      band: bands.join(","),
      quadrant,
      state,
      sort: "score",
    });
    setLeads(res.items);
    setTotal(res.total);
    setCursor(0);
  }, [runId, bands, quadrant, state]);

  useEffect(() => {
    if (run?.status === "complete") loadLeads();
  }, [run?.status, loadLeads]);

  const current = leads[cursor];

  useEffect(() => {
    if (!current) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api.explain(current.id).then((d) => !cancelled && setDetail(d));
    return () => {
      cancelled = true;
    };
    // Intentionally keyed on the id, not the whole lead object — refetching
    // explain data on every unrelated re-render would thrash the network.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id]);

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 1800);
  };

  const decide = useCallback(
    async (nextState: "accepted" | "rejected") => {
      if (!current) return;
      await api.review(current.id, nextState);
      setLeads((prev) => prev.filter((l) => l.id !== current.id));
      setCursor((c) => Math.min(c, Math.max(0, leads.length - 2)));
      setTotal((t) => Math.max(0, t - 1));
      flash(nextState === "accepted" ? "Accepted" : "Rejected");
    },
    [current, leads.length],
  );

  const undo = useCallback(async () => {
    const res = await api.leads(runId, { limit: 1, state: "accepted", sort: "score" });
    const last = res.items[0];
    if (!last) return flash("Nothing to undo");
    await api.review(last.id, "pending");
    await loadLeads();
    flash("Restored to the queue");
  }, [runId, loadLeads]);

  // --- keyboard triage ------------------------------------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const k = e.key.toLowerCase();
      if (k === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, leads.length - 1));
      } else if (k === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (k === "a") {
        decide("accepted");
      } else if (k === "x") {
        decide("rejected");
      } else if (k === "e" && current) {
        api.enrich(current.id).then(() => flash("Marked for enrichment"));
      } else if (k === "u") {
        undo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [leads.length, decide, undo, current]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const quadrantCounts = useMemo(() => run?.stats?.quadrants ?? {}, [run]);

  if (!run) return <Shell><p className="text-sm text-lo">Loading run…</p></Shell>;

  if (run.status !== "complete") {
    return (
      <Shell>
        <div className="max-w-md">
          <h2 className="text-sm font-medium text-hi">
            {run.status === "failed" ? "This run failed" : "Scoring your list"}
          </h2>
          {run.status === "failed" ? (
            <p className="mt-2 text-sm text-band-d">
              {run.stats?.error ?? "The pipeline stopped before it finished."} Upload the file again
              once the cause is fixed.
            </p>
          ) : (
            <>
              <div className="mt-4 h-1 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full bg-primary transition-all" style={{ width: `${run.progress * 100}%` }} />
              </div>
              <p className="mt-2 text-xs text-lo">
                {run.status} · {run.row_count} companies
              </p>
            </>
          )}
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-hi">{run.filename}</h1>
          <p className="text-xs text-lo">
            {run.stats.input_rows} rows in · {(run.stats.exact_merges ?? 0) + (run.stats.fuzzy_merges ?? 0)} duplicates merged ·{" "}
            {run.row_count} scored
            {run.stats.suppressed ? ` · ${run.stats.suppressed} suppressed` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={api.exportUrl(runId, "hubspot", "accepted")}
            className="rounded border border-line px-3 py-1.5 text-xs text-hi hover:border-primary"
          >
            Export accepted (HubSpot)
          </a>
          <a
            href={api.exportUrl(runId, "csv", "accepted")}
            className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-surface-0"
          >
            Export accepted (CSV)
          </a>
        </div>
      </header>

      <div className="mb-4 grid gap-3 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-wrap items-center gap-2">
          {BANDS.map((b) => (
            <button
              key={b}
              onClick={() => setBands((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]))}
              className={`rounded border px-2.5 py-1 text-xs ${
                bands.includes(b) ? "border-primary bg-primary/15 text-hi" : "border-line bg-surface-1 text-lo"
              }`}
            >
              {b} · {run.stats.bands?.[b] ?? 0}
            </button>
          ))}
          <select
            value={state}
            onChange={(e) => setState(e.target.value)}
            className="rounded border border-line bg-surface-1 px-2 py-1 text-xs text-hi"
          >
            <option value="pending">Unreviewed</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="">All</option>
          </select>
          <button
            onClick={() => api.rescan(runId).then((r) => { flash(`Rescanned ${r.rescanned}, ${r.changes} changes`); api.alerts(runId).then(setAlerts); })}
            className="rounded border border-line px-2.5 py-1 text-xs text-lo hover:text-hi"
          >
            Rescan &amp; diff
          </button>
          <button
            onClick={() => api.learning(runId).then(setLearning)}
            className="rounded border border-line px-2.5 py-1 text-xs text-lo hover:text-hi"
          >
            Tune from my decisions
          </button>
        </div>
        <QuadrantGrid counts={quadrantCounts} active={quadrant} onPick={setQuadrant} />
      </div>

      {learning && (
        <div className="mb-4 rounded border border-line bg-surface-1 p-4">
          <h3 className="text-sm font-medium text-hi">Learned weights</h3>
          {!learning.eligible ? (
            <p className="mt-1 text-xs text-lo">{learning.reason}. Keep triaging and try again.</p>
          ) : (
            <>
              <p className="mt-1 text-xs text-lo">
                From {learning.sample_size} of your decisions. Separation is how well each dimension
                predicted your own accepts against your rejects.
              </p>
              <table className="mt-3 w-full text-xs">
                <thead className="text-lo">
                  <tr>
                    <th className="pb-1 text-left font-normal">Dimension</th>
                    <th className="pb-1 text-right font-normal">Now</th>
                    <th className="pb-1 text-right font-normal">Proposed</th>
                    <th className="pb-1 text-right font-normal">Separation</th>
                  </tr>
                </thead>
                <tbody className="num">
                  {learning.proposals.map((p) => (
                    <tr key={p.dimension} className="border-t border-line/60">
                      <td className="py-1 text-hi">{p.dimension.replace(/_/g, " ")}</td>
                      <td className="py-1 text-right text-lo">{(p.current * 100).toFixed(0)}%</td>
                      <td className={`py-1 text-right ${p.delta > 0 ? "text-band-a" : "text-lo"}`}>
                        {(p.proposed * 100).toFixed(0)}%
                      </td>
                      <td className="py-1 text-right text-lo">{p.separation.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button
                onClick={async () => {
                  const weights = Object.fromEntries(learning.proposals.map((p) => [p.dimension, p.proposed]));
                  await api.rescore(runId, { weights });
                  const fresh = await api.run(runId);
                  setRun(fresh);
                  await loadLeads();
                  flash("Rescored with learned weights");
                }}
                className="mt-3 rounded bg-primary px-3 py-1.5 text-xs font-medium text-surface-0"
              >
                Rescore with these
              </button>
            </>
          )}
        </div>
      )}

      {alerts.length > 0 && (
        <div className="mb-4 rounded border border-line bg-surface-1 p-4">
          <h3 className="mb-2 text-sm font-medium text-hi">What changed since the last scan</h3>
          <ul className="space-y-1 text-xs">
            {alerts.slice(0, 8).map((a) => (
              <li key={a.id} className={a.severity === "warning" ? "text-band-d" : "text-lo"}>
                {a.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(320px,420px)_1fr]">
        <div
          ref={listRef}
          className="max-h-[70vh] overflow-y-auto rounded border border-line bg-surface-1"
          role="listbox"
          aria-label="Lead queue"
        >
          {leads.length === 0 ? (
            <p className="p-6 text-sm text-lo">
              Nothing left in this view. Widen the band filter, or switch the review filter to see
              what you have accepted.
            </p>
          ) : (
            leads.map((l, i) => (
              <button
                key={l.id}
                data-index={i}
                onClick={() => setCursor(i)}
                aria-selected={i === cursor}
                role="option"
                className={`flex w-full items-center gap-3 border-b border-line/60 px-3 py-2 text-left ${
                  i === cursor ? "bg-surface-2" : "hover:bg-surface-2/60"
                }`}
              >
                <span className="num w-10 shrink-0 text-right text-sm text-hi">{l.score.toFixed(0)}</span>
                <BandChip band={l.band} />
                <span className="flex-1 truncate text-sm text-hi">{l.company_name}</span>
                <span className="w-20 shrink-0 truncate text-[11px] text-lo">{l.city ?? "—"}</span>
              </button>
            ))
          )}
        </div>

        <div className="rounded border border-line bg-surface-1 p-5">
          {!current || !detail ? (
            <p className="text-sm text-lo">Select a lead to see why it ranked where it did.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-hi">{current.company_name}</h2>
                  <p className="text-xs text-lo">
                    {[current.domain, current.industry, [current.city, current.country].filter(Boolean).join(", ")]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="text-right">
                  <div className="num text-2xl font-semibold text-hi">{current.score.toFixed(0)}</div>
                  <div className="mt-1 flex items-center justify-end gap-2">
                    <BandChip band={current.band} />
                    <ConfidenceBar value={current.confidence} />
                  </div>
                </div>
              </div>

              <p className="mt-3 rounded border border-line bg-surface-2 px-3 py-2 text-xs leading-relaxed text-hi">
                {current.narrative}
              </p>

              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
                <Fact label="Employees" value={current.employee_count ?? "—"} />
                <Fact label="Revenue est." value={money(current.revenue_estimate)} />
                <Fact label="Contact" value={current.owner_name ?? "—"} />
                <Fact
                  label="Email"
                  value={current.email ?? "—"}
                  hint={current.email ? current.email_status : undefined}
                />
                <Fact label="Phone" value={current.phone ?? "—"} />
                <Fact label="Site scan" value={current.scan_status.replace(/_/g, " ")} />
              </div>

              {detail.merged_from.length > 0 && (
                <p className="mt-3 text-[11px] text-lo">
                  Merged from duplicate rows: {detail.merged_from.filter(Boolean).join(", ")}
                </p>
              )}

              <div className="mt-5">
                <h3 className="mb-2 text-xs font-medium text-hi">
                  How this score was built — {quadrantLabel[current.quadrant]}
                </h3>
                <Waterfall data={detail} />
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => decide("accepted")}
                  className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-surface-0"
                >
                  Accept <Key>A</Key>
                </button>
                <button
                  onClick={() => decide("rejected")}
                  className="rounded border border-line px-3 py-1.5 text-xs text-hi"
                >
                  Reject <Key>X</Key>
                </button>
                <button
                  onClick={() => api.enrich(current.id).then(() => flash("Marked for enrichment"))}
                  className="rounded border border-line px-3 py-1.5 text-xs text-hi"
                  title="Spend a credit on this one"
                >
                  Enrich <Key>E</Key>
                </button>
                <button onClick={undo} className="rounded px-2 py-1.5 text-xs text-lo hover:text-hi">
                  Undo <Key>U</Key>
                </button>
                <span className="ml-auto text-[11px] text-lo">
                  <Key>J</Key>/<Key>K</Key> to move · {cursor + 1} of {total}
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded border border-line bg-surface-2 px-4 py-2 text-xs text-hi shadow-lg"
        >
          {toast}
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-[1400px] px-6 py-8">{children}</main>;
}

function Fact({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div>
      <div className="text-[11px] text-lo">{label}</div>
      <div className="truncate text-hi" title={String(value)}>
        {value}
        {hint && <span className="ml-1 text-[11px] text-lo">({hint})</span>}
      </div>
    </div>
  );
}

function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="ml-1 rounded border border-line bg-surface-0 px-1 text-[10px] text-lo">{children}</kbd>
  );
}
