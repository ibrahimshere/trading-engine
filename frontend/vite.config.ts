import { defineConfig, type Plugin, type ViteDevServer } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import fs from "fs";
import path from "path";
import type { IncomingMessage, ServerResponse } from "http";

const EXECUTION_API_TARGET = process.env.EXECUTION_API_TARGET ?? "https://143.110.148.234.nip.io";
const EXECUTION_WS_TARGET = process.env.EXECUTION_WS_TARGET ?? "wss://143.110.148.234.nip.io";
const BACKTESTING_API_TARGET = process.env.BACKTESTING_API_TARGET ?? "https://143.110.148.234.nip.io";

function isLoopbackTarget(target: string) {
  try {
    const { hostname } = new URL(target);
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0" || hostname === "::1";
  } catch {
    return false;
  }
}

function rewritePrefixedApiPath(prefix: string, target: string) {
  return isLoopbackTarget(target)
    ? (requestPath: string) => requestPath.replace(new RegExp(`^${prefix}`), "/api")
    : undefined;
}

function researchReportsPlugin(): Plugin {
  const reportsDir = path.resolve(__dirname, "../backtesting/learnings/reports");

  const contentTypeFor = (filePath: string) => {
    if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
    if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
    if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
    return "text/plain; charset=utf-8";
  };

  const serveReport = (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const rawUrl = req.url?.split("?")[0] ?? "";
    if (!rawUrl.startsWith("/research-reports")) {
      next();
      return;
    }
    const rel = decodeURIComponent(rawUrl.replace(/^\/research-reports\/?/, ""));
    const target = path.resolve(reportsDir, rel || "STRATEGY_RESULTS_OVERVIEW.html");
    const relative = path.relative(reportsDir, target);
    if (relative.startsWith("..") || path.isAbsolute(relative) || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      res.statusCode = 404;
      res.end("Research report not found");
      return;
    }
    res.setHeader("Content-Type", contentTypeFor(target));
    fs.createReadStream(target).pipe(res);
  };

  const attach = (server: Pick<ViteDevServer, "middlewares">) => {
    server.middlewares.use(serveReport);
  };

  const copyHtmlReports = (outDir: string) => {
    fs.mkdirSync(outDir, { recursive: true });
    for (const name of fs.readdirSync(reportsDir)) {
      if (!name.endsWith(".html")) continue;
      fs.copyFileSync(path.join(reportsDir, name), path.join(outDir, name));
    }
  };

  return {
    name: "research-reports",
    configureServer: attach,
    configurePreviewServer: attach,
    closeBundle() {
      copyHtmlReports(path.resolve(__dirname, "dist/research-reports"));
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), researchReportsPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Execution API — WebSocket must come before HTTP catch-all
      "/exec-api/ws": {
        target: EXECUTION_WS_TARGET,
        changeOrigin: true,
        secure: true,
        ws: true,
        rewrite: rewritePrefixedApiPath("/exec-api", EXECUTION_WS_TARGET),
      },
      "/exec-api": {
        target: EXECUTION_API_TARGET,
        changeOrigin: true,
        secure: true,
        rewrite: rewritePrefixedApiPath("/exec-api", EXECUTION_API_TARGET),
      },
      // Backtesting API — use the configured target; local targets need the /bt-api -> /api rewrite.
      "/bt-api": {
        target: BACKTESTING_API_TARGET,
        changeOrigin: true,
        secure: true,
        rewrite: rewritePrefixedApiPath("/bt-api", BACKTESTING_API_TARGET),
      },
    },
  },
});
