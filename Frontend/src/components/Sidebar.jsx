import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getStudentName, isAuthenticated, logoutStudent } from "../data/profile";
import Icon from "./Icon";

const navigation = [
  { label: "Available Scholarships", to: "/", icon: "book", end: true },
  { label: "My Profile", to: "/profile", icon: "user" },
  { label: "Eligible Scholarships", to: "/eligible", icon: "check" },
  { label: "AI Assistant", to: "/assistant", icon: "assistant" },
  { label: "Certificate Scanner", to: "/documents", icon: "search" },
];

export default function Sidebar({ menuOpen, onNavigate, onOpenLogin }) {
  const [studentName, setStudentName] = useState(getStudentName);
  const [authed, setAuthed] = useState(isAuthenticated);

  useEffect(() => {
    const updateState = () => {
      setStudentName(getStudentName());
      setAuthed(isAuthenticated());
    };
    window.addEventListener("schobot-profile-updated", updateState);
    window.addEventListener("schobot-auth-changed", updateState);
    window.addEventListener("storage", updateState);
    return () => {
      window.removeEventListener("schobot-profile-updated", updateState);
      window.removeEventListener("schobot-auth-changed", updateState);
      window.removeEventListener("storage", updateState);
    };
  }, []);

  return (
    <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`}>
      <NavLink className="sidebar-brand" to="/" onClick={onNavigate}>
        <span className="brand-icon"><Icon name="graduation" size={23} /></span>
        <span>Schobot</span>
      </NavLink>

      <div className="sidebar-caption">MENU</div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {navigation.map(({ label, to, icon, end }) => (
          <NavLink
            className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
            end={end}
            key={to}
            onClick={onNavigate}
            to={to}
          >
            <Icon name={icon} size={19} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {authed ? (
        <div className="sidebar-student" aria-label="Signed-in student">
          <span className="student-avatar">{studentName ? studentName.slice(0, 1).toUpperCase() : "S"}</span>
          <span className="student-copy">
            <strong>{studentName || "Student"}</strong>
            <small>Signed in</small>
          </span>
          <button
            className="sidebar-logout-btn"
            type="button"
            title="Sign out"
            aria-label="Sign out"
            onClick={() => {
              logoutStudent();
            }}
          >
            <Icon name="logout" size={17} />
          </button>
        </div>
      ) : (
        <div className="sidebar-auth-cta">
          <button
            className="sidebar-login-btn"
            type="button"
            onClick={() => {
              onNavigate?.();
              onOpenLogin?.();
            }}
          >
            <Icon name="login" size={18} />
            <span>Student Login</span>
          </button>
        </div>
      )}
    </aside>
  );
}
