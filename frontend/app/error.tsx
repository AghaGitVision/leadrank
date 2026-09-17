"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex max-w-lg flex-col items-center px-6 py-24 text-center">
      <p className="num text-sm text-band-d">Error</p>
      <h1 className="mt-2 text-xl font-semibold tracking-tight text-hi">
        Something broke while rendering this page
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-lo">
        {error.message || "An unexpected error occurred."}
        {error.digest && <span className="block text-[11px] text-lo/70">Ref: {error.digest}</span>}
      </p>
      <div className="mt-6 flex gap-2">
        <button
          onClick={reset}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-surface-0"
        >
          Try again
        </button>
        <a href="/" className="rounded border border-line px-4 py-2 text-sm text-hi">
          Start over
        </a>
      </div>
    </main>
  );
}
