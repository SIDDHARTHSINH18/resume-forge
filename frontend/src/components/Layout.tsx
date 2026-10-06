import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "../api";
import { Icon, type IconName } from "./Icon";

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: "dashboard", end: true },
  { to: "/profiles", label: "Jobs", icon: "profiles" },
  { to: "/candidates", label: "Candidates", icon: "candidates" },
  { to: "/sources", label: "Sources", icon: "download" },
  { to: "/processing", label: "Processing", icon: "processing" },
  { to: "/reviews", label: "Review Queue", icon: "reviews" },
  { to: "/exports", label: "Reports", icon: "exports" },
  { to: "/settings", label: "Settings", icon: "settings" },
];

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle && <div className="topbar-sub">{subtitle}</div>}
      </div>
      {actions && <div className="topbar-actions">{actions}</div>}
    </header>
  );
}

export function Layout() {
  const [reviewer, setReviewer] = useState("Local Reviewer");

  useEffect(() => {
    let active = true;
    api
      .settings()
      .then((data) => {
        if (active && data.reviewer?.name) setReviewer(data.reviewer.name);
      })
      .catch(() => {
        /* the sidebar falls back to the default reviewer name */
      });
    return () => {
      active = false;
    };
  }, []);

  const initials = reviewer
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="funnel" size={16} />
          </span>
          <span className="brand-text">
            <span className="brand-name">MeritOS</span>
            <br />
            <span className="brand-sub">HIRING INTELLIGENCE</span>
          </span>
        </div>
        <nav className="nav" aria-label="Main navigation">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={item.label}
              aria-label={item.label}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <Icon name={item.icon} size={16} />
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip">
            <span className="avatar">{initials || "LR"}</span>
            <span className="user-text">
              <span className="user-name" style={{ display: "block" }}>
                {reviewer}
              </span>
              <span className="user-role">Human reviewer</span>
            </span>
          </div>
          <p className="local-note">Local-first. Resumes and decisions stay on this machine.</p>
        </div>
      </aside>
      <main className="main" id="main-content" tabIndex={-1}>
        <div className="workspace-frame">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
