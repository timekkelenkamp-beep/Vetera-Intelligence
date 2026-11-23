import { Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Sidebar } from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Competitors from "./pages/Competitors";
import CompetitorDetail from "./pages/CompetitorDetail";
import Conditions from "./pages/Conditions";
import PremiumLab from "./pages/PremiumLab";
import MarketMonitor from "./pages/MarketMonitor";
import Radar from "./pages/Radar";
import SuggestionDetail from "./pages/SuggestionDetail";
import Reports from "./pages/Reports";
import ReportView from "./pages/ReportView";
import Sources from "./pages/Sources";
import DocumentDetail from "./pages/DocumentDetail";
import SettingsPage from "./pages/Settings";
import Research from "./pages/Research";
import ProductDetail from "./pages/ProductDetail";

export default function App() {
  const loc = useLocation();
  const printView = loc.pathname.startsWith("/rapportages/") && loc.pathname.endsWith("/print");
  if (printView) {
    return (
      <Routes>
        <Route path="/rapportages/:id/print" element={<ReportView />} />
      </Routes>
    );
  }
  return (
    <div className="min-h-screen bg-white">
      <Sidebar />
      <main className="ml-[248px] min-h-screen">
        <AnimatePresence mode="wait">
          <motion.div
            key={loc.pathname.split("/").slice(0, 2).join("/")}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="mx-auto max-w-[1360px] px-10 pt-10 pb-20"
          >
            <Routes location={loc}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/onderzoek" element={<Research />} />
              <Route path="/concurrenten" element={<Competitors />} />
              <Route path="/concurrenten/:id" element={<CompetitorDetail />} />
              <Route path="/producten/:id" element={<ProductDetail />} />
              <Route path="/voorwaarden" element={<Conditions />} />
              <Route path="/premielab" element={<PremiumLab />} />
              <Route path="/marktmonitor" element={<MarketMonitor />} />
              <Route path="/verbeterradar" element={<Radar />} />
              <Route path="/verbeterradar/:id" element={<SuggestionDetail />} />
              <Route path="/rapportages" element={<Reports />} />
              <Route path="/rapportages/:id" element={<ReportView />} />
              <Route path="/bronnen" element={<Sources />} />
              <Route path="/kwaliteit" element={<Sources initialTab="kwaliteit" />} />
              <Route path="/documenten/:id" element={<DocumentDetail />} />
              <Route path="/instellingen" element={<SettingsPage />} />
              <Route path="*" element={<div className="py-20 text-center text-ink-muted">Pagina niet gevonden.</div>} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
