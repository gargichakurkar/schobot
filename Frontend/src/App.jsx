import { useState } from "react";
import {
  BrowserRouter,
  Route,
  Routes,
} from "react-router-dom";
import Sidebar from "./components/Sidebar";
import AvailableScholarships from "./pages/AvailableScholarships";
import EligibleScholarships from "./pages/EligibleScholarships";
import MyProfile from "./pages/MyProfile";
import ScholarshipDetails from "./pages/ScholarshipDetails";
import AIAssistant from "./pages/AIAssistant";
import CertificateScanner from "./pages/CertificateScanner";
import "./App.css";

function PlaceholderPage({ title, description }) {
  return (
    <main className="content-page">
      <div className="page-heading">
        <p className="eyebrow">SCHOBOT</p>
        <h1>{title}</h1>
        <p className="page-subtitle">{description}</p>
      </div>
      <section className="placeholder-panel">
        <p>This section is being prepared.</p>
      </section>
    </main>
  );
}

function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar menuOpen={menuOpen} onNavigate={() => setMenuOpen(false)} />
      {menuOpen && (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close navigation menu"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <div className="app-main">
        <header className="mobile-header">
          <button
            className="menu-toggle"
            type="button"
            aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span /><span /><span />
          </button>
          <span className="mobile-brand">Schobot</span>
        </header>
        <Routes>
          <Route path="/" element={<AvailableScholarships />} />
          <Route path="/profile" element={<MyProfile />} />
          <Route path="/eligible" element={<EligibleScholarships />} />
          <Route path="/scholarship/:id" element={<ScholarshipDetails />} />
          <Route path="/assistant" element={<AIAssistant />} />
          <Route path="/documents" element={<CertificateScanner />} />
          <Route
            path="*"
            element={<PlaceholderPage title="Page not found" description="Choose a section from the navigation." />}
          />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}
