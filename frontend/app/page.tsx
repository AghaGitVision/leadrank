"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Mode, Profile, WeightSchema } from "@/lib/api";

type Preview = Awaited<ReturnType<typeof api.preview>>;

export default function SetupPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("buy");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [schema, setSchema] = useState<WeightSchema | null>(null);
  const [profileId, setProfileId] = useState<string>("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [showWeights, setShowWeights] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.profiles(), api.weightSchema()])
      .then(([p, s]) => {
        setProfiles(p);
        setSchema(s);
      })
      .catch((e) => setError(`Can't reach the API at ${process.env.NEXT_PUBLIC_API_BASE}. ${e.message}`));
  }, []);

  const modeProfiles = useMemo(() => profiles.filter((p) => p.mode === mode), [profiles, mode]);

  useEffect(() => {
    const first = modeProfiles[0];
    if (first) {
      setProfileId(first.id);
      setWeights(first.weights);
    }
  }, [modeProfiles]);

  const dimensions = schema?.[mode]?.dimensions ?? [];
  const weightTotal = Object.values(weights).reduce((a, b) => a + b, 0) || 1;

  async function onFile(f: File) {
    setFile(f);
    setError(null);
    try {
      setPreview(await api.preview(f));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function start() {
    if (!file || !profileId) return;
    setBusy(true);
    setError(null);
    try {
      let targetProfile = profileId;
      const base = profiles.find((p) => p.id === profileId);
      const changed =
        base && Object.keys(weights).some((k) => Math.abs((base.weights[k] ?? 0) - weights[k]) > 0.001);
      if (changed && base) {
        const created = await api.createProfile({
          name: `${base.name} (tuned)`,
          mode: base.mode,
          weights,
          targeting: base.targeting,
        });
        targetProfile = created.id;
      }
      const run = await api.createRun(file, targetProfile, preview?.mapping);
      router.push(`/runs/${run.id}`);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10">
        <h1 className="text-2xl font-semibold tracking-tight">LeadRank</h1>
        <p className="mt-1 max-w-xl text-sm leading-relaxed text-lo">
          A list is not a pipeline. Score what you scraped, see why each company ranked where it
          did, and work the queue in order.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded border border-band-d/40 bg-band-d/10 px-4 py-3 text-sm text-band-d">
          {error}
        </div>
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-hi">What are you looking for?</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              {
                id: "sell" as Mode,
                title: "Customers to sell to",
                body: "Rewards reachable decision-makers, modern operations and growth signals.",
              },
              {
                id: "buy" as Mode,
                title: "Businesses to buy",
                body: "Rewards owner-operated, durable companies that are under-digitized.",
              },
            ]
          ).map((opt) => (
            <button
              key={opt.id}
              onClick={() => setMode(opt.id)}
              aria-pressed={mode === opt.id}
              className={`rounded border px-4 py-4 text-left transition-colors ${
                mode === opt.id
                  ? "border-primary bg-primary/10"
                  : "border-line bg-surface-1 hover:border-surface-3"
              }`}
            >
              <div className="text-sm font-medium text-hi">{opt.title}</div>
              <div className="mt-1 text-xs leading-relaxed text-lo">{opt.body}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <label className="mb-2 block text-sm font-medium text-hi">Scoring profile</label>
        <select
          value={profileId}
          onChange={(e) => {
            setProfileId(e.target.value);
            const p = profiles.find((x) => x.id === e.target.value);
            if (p) setWeights(p.weights);
          }}
          className="w-full rounded border border-line bg-surface-1 px-3 py-2 text-sm text-hi"
        >
          {modeProfiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        <button
          onClick={() => setShowWeights((v) => !v)}
          className="mt-3 text-xs text-primary hover:underline"
        >
          {showWeights ? "Hide" : "Adjust"} dimension weights
        </button>

        {showWeights && (
          <div className="mt-4 space-y-4 rounded border border-line bg-surface-1 p-4">
            {dimensions.map((d) => {
              const v = weights[d.key] ?? 0;
              return (
                <div key={d.key}>
                  <div className="mb-1 flex items-baseline justify-between text-xs">
                    <span className="text-hi">{d.label}</span>
                    <span className="num text-lo">{Math.round((v / weightTotal) * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={0.6}
                    step={0.01}
                    value={v}
                    onChange={(e) =>
                      setWeights({ ...weights, [d.key]: Number(e.target.value) })
                    }
                    className="w-full accent-primary"
                    aria-label={d.label}
                  />
                  <p className="mt-1 text-[11px] leading-snug text-lo">
                    {d.signals.map((s) => s.label).join(" · ")}
                  </p>
                </div>
              );
            })}
            <p className="text-[11px] text-lo">
              Weights are normalised on save. Changing them here creates a tuned copy — the
              built-in profile stays as shipped.
            </p>
          </div>
        )}
      </section>

      <section className="mb-8">
        <label className="mb-2 block text-sm font-medium text-hi">Lead list</label>
        <label
          className="flex cursor-pointer flex-col items-center justify-center rounded border border-dashed border-line bg-surface-1 px-6 py-10 text-center hover:border-primary/60"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f) onFile(f);
          }}
        >
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
          />
          <span className="text-sm text-hi">
            {file ? file.name : "Drop a CSV here, or click to choose one"}
          </span>
          <span className="mt-1 text-xs text-lo">
            Any export with a company name works. Columns are matched automatically.
          </span>
        </label>
      </section>

      {preview && (
        <section className="mb-8 rounded border border-line bg-surface-1 p-4">
          <h3 className="mb-3 text-sm font-medium text-hi">Column mapping</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(preview.mapping).map(([header, field]) => (
              <div key={header} className="flex items-center gap-2 text-xs">
                <span className="truncate text-lo">{header}</span>
                <span className="text-lo">→</span>
                <span className="text-hi">{field.replace(/_/g, " ")}</span>
              </div>
            ))}
          </div>
          {preview.unmapped.length > 0 && (
            <p className="mt-3 text-xs text-lo">
              Kept as-is and carried through to export: {preview.unmapped.join(", ")}
            </p>
          )}
          {preview.missing_required.length > 0 && (
            <p className="mt-3 text-xs text-band-d">
              No company name column found. Rename a column to &quot;Company Name&quot; and upload again.
            </p>
          )}
        </section>
      )}

      <button
        onClick={start}
        disabled={!file || busy || (preview?.missing_required.length ?? 0) > 0}
        className="rounded bg-primary px-5 py-2.5 text-sm font-medium text-surface-0 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Starting…" : "Score this list"}
      </button>
    </main>
  );
}
