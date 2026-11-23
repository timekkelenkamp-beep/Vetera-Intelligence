import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import App from "./App";
import { TooltipProvider } from "./components/ui/primitives";
import { SourceViewerProvider } from "./components/SourceViewer";
import "./index.css";

const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5_000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <TooltipProvider>
          <SourceViewerProvider>
            <App />
            <Toaster position="bottom-right" toastOptions={{ className: "!rounded-xl !text-[13px] !shadow-lift !border-line" }} />
          </SourceViewerProvider>
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
