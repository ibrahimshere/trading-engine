import { lazy, Suspense, useState } from "react";
import { BacktestingTabSkeleton } from "@/shared/ui/page-skeletons";

type Tab = "backtests" | "reports" | "saved" | "configs" | "optimizations" | "coverage" | "risk-engine" | "regime" | "news";

const TAB_LABELS: Record<Tab, string> = {
  backtests: "Backtests",
  reports: "Reports",
  saved: "Saved",
  configs: "Configs",
  optimizations: "Optimizations",
  coverage: "Coverage",
  "risk-engine": "Risk Engine",
  regime: "Regime",
  news: "News",
};

const BacktestDashboard = lazy(() =>
  import("@/backtesting/components/BacktestDashboard").then((module) => ({ default: module.BacktestDashboard })),
);
const ReportsDashboard = lazy(() =>
  import("@/backtesting/components/ReportsDashboard").then((module) => ({ default: module.ReportsDashboard })),
);
const SavedStrategiesDashboard = lazy(() =>
  import("@/backtesting/components/SavedStrategiesDashboard").then((module) => ({ default: module.SavedStrategiesDashboard })),
);
const ConfigsDashboard = lazy(() =>
  import("@/backtesting/components/ConfigsDashboard").then((module) => ({ default: module.ConfigsDashboard })),
);
const OptimizeDashboard = lazy(() =>
  import("@/backtesting/components/OptimizeDashboard").then((module) => ({ default: module.OptimizeDashboard })),
);
const CoverageDashboard = lazy(() =>
  import("@/backtesting/components/CoverageDashboard").then((module) => ({ default: module.CoverageDashboard })),
);
const RiskEngineDashboard = lazy(() =>
  import("@/backtesting/components/RiskEngineDashboard").then((module) => ({ default: module.RiskEngineDashboard })),
);
const RegimeDashboard = lazy(() =>
  import("@/backtesting/components/RegimeDashboard").then((module) => ({ default: module.RegimeDashboard })),
);
const NewsDashboard = lazy(() =>
  import("@/backtesting/components/NewsDashboard").then((module) => ({ default: module.NewsDashboard })),
);

export function BacktestApp() {
  const [activeTab, setActiveTab] = useState<Tab>("backtests");

  return (
    <>
      {/* Tab bar */}
      <div className="gc-section-header px-4 py-2 sm:px-6 lg:px-8">
        <div className="gc-route-tabs mx-auto max-w-7xl">
          {(["backtests", "reports", "saved", "configs", "optimizations", "coverage", "risk-engine", "regime", "news"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`gc-tab-button ${activeTab === tab ? "is-active" : ""}`}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>
      </div>

      <Suspense fallback={<BacktestingTabSkeleton tab={activeTab} />}>
        {activeTab === "backtests" && <BacktestDashboard />}
        {activeTab === "reports" && <ReportsDashboard />}
        {activeTab === "saved" && <SavedStrategiesDashboard />}
        {activeTab === "configs" && <ConfigsDashboard />}
        {activeTab === "optimizations" && <OptimizeDashboard />}
        {activeTab === "coverage" && <CoverageDashboard />}
        {activeTab === "risk-engine" && <RiskEngineDashboard />}
        {activeTab === "regime" && <RegimeDashboard />}
        {activeTab === "news" && <NewsDashboard />}
      </Suspense>
    </>
  );
}
