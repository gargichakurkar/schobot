import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getStudentName } from "../data/profile";
import Icon from "./Icon";

const navigation = [
  { label: "Available Scholarships", to: "/", icon: "book", end: true },
  { label: "My Profile", to: "/profile", icon: "user" },
  { label: "Eligible Scholarships", to: "/eligible", icon: "check" },
  { label: "AI Assistant", to: "/assistant", icon: "assistant" },
];

export default function Sidebar({ menuOpen, onNavigate }) {
  const [studentName, setStudentName] = useState(getStudentName);

  useEffect(() => {
    const updateName = () => setStudentName(getStudentName());
    window.addEventListener("schobot-profile-updated", updateName);
    window.addEventListener("storage", updateName);
    return () => {
      window.removeEventListener("schobot-profile-updated", updateName);
      window.removeEventListener("storage", updateName);
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

      <div className="sidebar-student" aria-label="Signed-in student">
        <span className="student-avatar">{studentName ? studentName.slice(0, 1).toUpperCase() : "?"}</span>
        <span className="student-copy">
          <strong>{studentName || "Student"}</strong>
          <small>Student</small>
        </span>
        <span className="student-chevron"><Icon name="chevron" size={15} /></span>
      </div>
    </aside>
  );
}
