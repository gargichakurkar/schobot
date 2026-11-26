import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Route,
  Routes,
} from "react-router-dom";
import Sidebar from "./components/Sidebar";
import LoginModal from "./components/LoginModal";
import AvailableScholarships from "./pages/AvailableScholarships";
import EligibleScholarships from "./pages/EligibleScholarships";
import MyProfile from "./pages/MyProfile";
import ScholarshipDetails from "./pages/ScholarshipDetails";
import AIAssistant from "./pages/AIAssistant";
import CertificateScanner from "./pages/CertificateScanner";
import { getStudentName, isAuthenticated, logoutStudent } from "./data/profile";
import Icon from "./components/Icon";
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
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState(false);
  const [authed, setAuthed] = useState(isAuthenticated);
  const [studentName, setStudentName] = useState(getStudentName);

  useEffect(() => {
    const updateAuth = () => {
      setAuthed(isAuthenticated());
      setStudentName(getStudentName());
    };
    const handleExpired = () => {
      setSessionExpiredNotice(true);
      setLoginModalOpen(true);
      updateAuth();
    };

    window.addEventListener("schobot-auth-changed", updateAuth);
    window.addEventListener("schobot-profile-updated", updateAuth);
    window.addEventListener("schobot-session-expired", handleExpired);

    return () => {
      window.removeEventListener("schobot-auth-changed", updateAuth);
      window.removeEventListener("schobot-profile-updated", updateAuth);
      window.removeEventListener("schobot-session-expired", handleExpired);
    };
  }, []);

  return (
    <div className="app-shell">
      <Sidebar
        menuOpen={menuOpen}
        onNavigate={() => setMenuOpen(false)}
        onOpenLogin={() => {
          setSessionExpiredNotice(false);
          setLoginModalOpen(true);
        }}
      />
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

          <div className="mobile-header-auth">
            {authed ? (
              <button
                type="button"
                className="mobile-auth-btn mobile-logout-btn"
                title="Sign out"
                onClick={() => logoutStudent()}
              >
                <Icon name="logout" size={16} />
                <span>Sign Out</span>
              </button>
            ) : (
              <button
                type="button"
                className="mobile-auth-btn mobile-login-btn"
                onClick={() => {
                  setSessionExpiredNotice(false);
                  setLoginModalOpen(true);
                }}
              >
                <Icon name="login" size={16} />
                <span>Log In</span>
              </button>
            )}
          </div>
        </header>

        {sessionExpiredNotice && (
          <aside className="session-expired-banner" role="status">
            <span>Your session has expired. Please sign in to resume access to your Document Vault.</span>
            <button
              type="button"
              className="banner-action-btn"
              onClick={() => {
                setSessionExpiredNotice(false);
                setLoginModalOpen(true);
              }}
            >
              Log In Again
            </button>
            <button
              type="button"
              className="banner-close-btn"
              aria-label="Dismiss banner"
              onClick={() => setSessionExpiredNotice(false)}
            >
              ×
            </button>
          </aside>
        )}

        <Routes>
          <Route path="/" element={<AvailableScholarships />} />
          <Route
            path="/profile"
            element={
              <MyProfile
                onOpenLogin={() => {
                  setSessionExpiredNotice(false);
                  setLoginModalOpen(true);
                }}
              />
            }
          />
          <Route path="/eligible" element={<EligibleScholarships />} />
          <Route path="/scholarship/:id" element={<ScholarshipDetails />} />
          <Route path="/assistant" element={<AIAssistant />} />
          <Route
            path="/documents"
            element={
              <CertificateScanner
                onOpenLogin={() => {
                  setSessionExpiredNotice(false);
                  setLoginModalOpen(true);
                }}
              />
            }
          />
          <Route
            path="/login"
            element={
              <main className="content-page">
                <div className="page-heading">
                  <p className="eyebrow">AUTHENTICATION</p>
                  <h1>Student Login</h1>
                  <p className="page-subtitle">Sign in to manage your documents and explore scholarships.</p>
                </div>
                <section className="login-page-card">
                  <p>Click below to sign in with your email or Student ID:</p>
                  <button
                    type="button"
                    className="login-submit-btn"
                    style={{ maxWidth: 300, marginTop: 16 }}
                    onClick={() => setLoginModalOpen(true)}
                  >
                    Open Student Login
                  </button>
                </section>
              </main>
            }
          />
          <Route
            path="*"
            element={<PlaceholderPage title="Page not found" description="Choose a section from the navigation." />}
          />
        </Routes>
      </div>

      <LoginModal
        isOpen={loginModalOpen}
        onClose={() => {
          setLoginModalOpen(false);
          setSessionExpiredNotice(false);
        }}
        onSuccess={() => {
          setSessionExpiredNotice(false);
        }}
      />
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
