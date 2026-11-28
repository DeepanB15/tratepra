import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/layout/Layout";
import History from "./pages/History";
import Dossier from "./pages/Dossier";
import Home from "./pages/Home";
import Research from "./pages/Research";
import Runs from "./pages/Runs";
import Saved from "./pages/Saved";
import Sources from "./pages/Sources";
import Settings from "./pages/Settings";
import TrendDetail from "./pages/TrendDetail";
import Trends from "./pages/Trends";
import MonitorOverview from "./pages/monitor/MonitorOverview";
import Watchlist from "./pages/monitor/Watchlist";
import Activity from "./pages/monitor/Activity";
import Notifications from "./pages/monitor/Notifications";
import MonitorSettings from "./pages/monitor/MonitorSettings";
import TrendMonitor from "./pages/monitor/TrendMonitor";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/research" element={<Research />} />
        <Route path="/research/:id" element={<Research />} />
        <Route path="/dossiers/:id" element={<Dossier />} />
        <Route path="/trends" element={<Trends />} />
        <Route path="/trends/:id" element={<TrendDetail />} />
        <Route path="/monitor" element={<MonitorOverview />} />
        <Route path="/monitor/watchlist" element={<Watchlist />} />
        <Route path="/monitor/activity" element={<Activity />} />
        <Route path="/monitor/notifications" element={<Notifications />} />
        <Route path="/monitor/settings" element={<MonitorSettings />} />
        <Route path="/monitor/trends/:id" element={<TrendMonitor />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/history" element={<History />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
