import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-lg flex-col items-center px-6 py-24 text-center">
      <p className="num text-sm text-primary">404</p>
      <h1 className="mt-2 text-xl font-semibold tracking-tight text-hi">
        Nothing scored at this address
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-lo">
        The page you&rsquo;re looking for doesn&rsquo;t exist, or the run behind it was never created.
      </p>
      <Link
        href="/"
        className="mt-6 rounded bg-primary px-4 py-2 text-sm font-medium text-surface-0"
      >
        Start a new run
      </Link>
    </main>
  );
}
