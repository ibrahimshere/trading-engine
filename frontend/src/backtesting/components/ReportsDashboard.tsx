import { useMemo, useState } from "react";

const RESEARCH_REPORTS = [
  {
    id: "overview",
    title: "Strategy results overview",
    blurb: "ALPHA_V1 exact 5Y book, GO/NO-GO board, and links to every HTML report.",
    href: "/research-reports/STRATEGY_RESULTS_OVERVIEW.html",
  },
  {
    id: "live-execution",
    title: "Live execution results",
    blurb: "Full production trade history since March 2026. ALPHA_V1-A live vs dry-run books.",
    href: "/research-reports/LIVE_EXECUTION_RESULTS.html",
  },
  {
    id: "council-20260403-083956",
    title: "Prop-firm payout farming",
    blurb: "Original ALPHA_V1 four-leg keep/cut recommendation.",
    href: "/research-reports/council-report-20260403-083956.html",
  },
  {
    id: "council-20260403-093017",
    title: "Candidate re-evaluation",
    blurb: "Second pass over the research candidate list.",
    href: "/research-reports/council-report-20260403-093017.html",
  },
  {
    id: "council-20260403-144421",
    title: "Discovery vs ALPHA_V1",
    blurb: "Whether discovery legs should replace the live book.",
    href: "/research-reports/council-report-20260403-144421.html",
  },
  {
    id: "council-20260403-200758",
    title: "ALPHA_V1 & TESTING audit",
    blurb: "Config audit of the live and testing profiles.",
    href: "/research-reports/council-report-20260403-200758.html",
  },
  {
    id: "council-20260412-195951",
    title: "ORB/LSI next-step allocation",
    blurb: "Where to spend the next research cycle.",
    href: "/research-reports/council-report-20260412-195951.html",
  },
  {
    id: "council-20260403-110838",
    title: "Discovery candidate evaluation",
    blurb: "Promotion and cut calls on discovery rows.",
    href: "/research-reports/council-report-20260403-110838.html",
  },
  {
    id: "council-20260403-103125",
    title: "Regime gate implementation",
    blurb: "Live-gate implementation review.",
    href: "/research-reports/council-report-20260403-103125.html",
  },
  {
    id: "council-20260402-102407",
    title: "Regime gate lookahead",
    blurb: "Whether regime gates leak future information.",
    href: "/research-reports/council-report-20260402-102407.html",
  },
  {
    id: "council-20260331-221500",
    title: "PBO/DSR implementation",
    blurb: "Overfitting-gate design.",
    href: "/research-reports/council-report-20260331-221500.html",
  },
] as const;

export function ReportsDashboard() {
  const [activeId, setActiveId] = useState<string>(RESEARCH_REPORTS[0].id);
  const active = useMemo(
    () => RESEARCH_REPORTS.find((report) => report.id === activeId) ?? RESEARCH_REPORTS[0],
    [activeId],
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-lg font-semibold text-text-primary">Research reports</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-muted">
            Static HTML from the learnings library. The interactive ALPHA_V1-A 5Y exact replay stays on the Backtests tab.
          </p>
        </div>
        <a
          href={active.href}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card-hover"
        >
          Open in new tab
        </a>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(16rem,20rem)_minmax(0,1fr)]">
        <aside className="max-h-[calc(100vh-12rem)] overflow-y-auto rounded-lg border border-border bg-bg-card">
          {RESEARCH_REPORTS.map((report) => {
            const selected = report.id === active.id;
            return (
              <button
                key={report.id}
                type="button"
                onClick={() => setActiveId(report.id)}
                className={`block w-full border-b border-border px-3 py-3 text-left last:border-b-0 ${
                  selected ? "bg-bg-tertiary" : "hover:bg-bg-card-hover"
                }`}
              >
                <div className={`text-sm font-medium ${selected ? "text-text-primary" : "text-text-secondary"}`}>
                  {report.title}
                </div>
                <div className="mt-1 text-[11px] leading-4 text-text-muted">{report.blurb}</div>
              </button>
            );
          })}
        </aside>

        <section className="min-h-[70vh] overflow-hidden rounded-lg border border-border bg-bg-card">
          <iframe
            key={active.href}
            title={active.title}
            src={active.href}
            className="h-[calc(100vh-12rem)] min-h-[70vh] w-full bg-bg-primary"
          />
        </section>
      </div>
    </div>
  );
}
