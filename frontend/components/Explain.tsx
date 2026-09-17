"use client";

import { Explain, Signal, bandColor, quadrantLabel } from "@/lib/api";

export function BandChip({ band }: { band: string }) {
  return (
    <span
      className={`inline-flex h-5 w-5 items-center justify-center rounded border text-[11px] font-semibold ${bandColor[band] ?? ""}`}
      title={`Band ${band}`}
    >
      {band}
    </span>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-16 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full bg-primary" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="num text-xs text-lo">{Math.round(value * 100)}%</span>
    </div>
  );
}

/**
 * The waterfall is the one place this interface spends its boldness. Every
 * other surface stays quiet so the reasoning is what draws the eye.
 */
export function Waterfall({ data }: { data: Explain }) {
  const gained = data.gained.filter((g) => g.contribution > 0.4).slice(0, 8);
  const lost = data.lost.filter((l) => l.forgone > 0.4).slice(0, 4);
  const max = Math.max(...gained.map((g) => g.contribution), ...lost.map((l) => l.forgone), 1);

  return (
    <div>
      <div className="space-y-1.5">
        {gained.map((s) => (
          <Row key={s.signal_key + s.dimension} signal={s} value={s.contribution} max={max} positive />
        ))}
      </div>

      {lost.length > 0 && (
        <>
          <p className="mb-1.5 mt-4 text-[11px] uppercase tracking-wide text-lo">Points not earned</p>
          <div className="space-y-1.5">
            {lost.map((s) => (
              <Row key={"l" + s.signal_key + s.dimension} signal={s} value={s.forgone} max={max} />
            ))}
          </div>
        </>
      )}

      {data.missing.length > 0 && (
        <p className="mt-4 text-[11px] leading-relaxed text-lo">
          Not observed, so it lowered confidence rather than the score:{" "}
          {data.missing.map((m) => m.label.toLowerCase()).join(", ")}.
        </p>
      )}
    </div>
  );
}

function Row({
  signal,
  value,
  max,
  positive = false,
}: {
  signal: Signal;
  value: number;
  max: number;
  positive?: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="num w-12 shrink-0 text-right text-xs text-hi">
        {positive ? "+" : "−"}
        {value.toFixed(1)}
      </div>
      <div className="h-4 flex-1 overflow-hidden rounded-sm bg-surface-2">
        <div
          className={positive ? "h-full bg-primary/70" : "h-full bg-surface-3"}
          style={{ width: `${Math.max(2, (value / max) * 100)}%` }}
        />
      </div>
      <div className="w-[46%] shrink-0 truncate text-xs text-lo" title={signal.label}>
        {signal.label}
      </div>
    </div>
  );
}

export function QuadrantGrid({
  counts,
  active,
  onPick,
}: {
  counts: Record<string, number>;
  active: string;
  onPick: (q: string) => void;
}) {
  const cells: { key: string; label: string; hint: string }[] = [
    { key: "act", label: quadrantLabel.act, hint: "high score · high confidence" },
    { key: "verify", label: quadrantLabel.verify, hint: "high score · low confidence" },
    { key: "pass", label: quadrantLabel.pass, hint: "low score · high confidence" },
    { key: "recheck", label: quadrantLabel.recheck, hint: "low score · low confidence" },
  ];
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line">
      {cells.map((c) => (
        <button
          key={c.key}
          onClick={() => onPick(active === c.key ? "" : c.key)}
          className={`px-3 py-2 text-left transition-colors ${
            active === c.key ? "bg-primary/15" : "bg-surface-1 hover:bg-surface-2"
          }`}
        >
          <div className="num text-sm font-semibold text-hi">{counts[c.key] ?? 0}</div>
          <div className="text-[11px] text-hi">{c.label}</div>
          <div className="text-[10px] text-lo">{c.hint}</div>
        </button>
      ))}
    </div>
  );
}
