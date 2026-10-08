import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "../api";
import { CommandBar } from "./CommandBar";
import { Icon, type IconName } from "./Icon";

const NAV: { section?: string; items: { to: string; label: string; icon: IconName; end?: boolean }[] }[] = [
  {
    items: [{ to: "/", label: "Dashboard", icon: "dashboard", end: true }],
  },
  {
    section: "Hiring",
    items: [
      { to: "/candidates", label: "Candidates", icon: "candidates" },
      { to: "/processing", label: "Jobs", icon: "processing" },
      { to: "/reviews", label: "Reviews", icon: "reviews" },
    ],
  },
  {
    section: "Setup",
    items: [
      { to: "/profiles", label: "Profiles", icon: "profiles" },
      { to: "/sources", label: "Sources", icon: "download" },
      { to: "/library", label: "Library", icon: "file" },
      { to: "/settings", label: "Settings", icon: "settings" },
    ],
  },
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
    <header className="page-header">
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
      <CommandBar reviewer={reviewer} />
      <div className="app-body">
        <aside className="sidebar">
          <nav className="nav" aria-label="Main navigation">
            {NAV.map((group, index) => (
              <div key={index} style={{ display: "contents" }}>
                {group.section && <div className="nav-section">{group.section}</div>}
                {group.items.map((item) => (
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
              </div>
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
          <Outlet />
        </main>
      </div>
    </div>
  );
}
