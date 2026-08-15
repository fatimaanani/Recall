import { Outlet } from "react-router-dom";
import "./AppShell.css";

import Logo from "../components/Logo";
import AdminNavigation from "../components/navigation/AdminNavigation";
import TopBar from "../components/TopBar";
import Icon from "../components/Icon";
import { useDarkMode } from "../hooks/useDarkMode";

// Admin shell, same sidebar/topbar pattern as UserLayout
export default function AdminLayout() {
  const [darkMode, setDarkMode] = useDarkMode();

  return (
    <div className="app-shell app-shell--admin">
      <aside className="sidebar">
        <div className="sidebar__brand-wrap">
          <Logo size="sm" />
        </div>

        <AdminNavigation />

        <div className="sidebar-spacer" />

        <div className="dark-mode-row">
          <span>
            <Icon name="moon" size={15} /> Dark Mode
          </span>
          <button
            type="button"
            className={`toggle-switch${darkMode ? " on" : ""}`}
            aria-pressed={darkMode}
            onClick={() => setDarkMode((v) => !v)}
          />
        </div>
      </aside>

      <main className="app-content">
        <TopBar />
        <Outlet />
      </main>
    </div>
  );
}
