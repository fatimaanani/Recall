import { NavLink } from "react-router-dom";

import Icon from "../Icon";
import "./Navigation.css";

// Admin sidebar items
const ADMIN_NAV_ITEMS = [
  { label: "User Management", to: "/admin/users", icon: "users" },
  { label: "Data Management", to: "/admin/data-management", icon: "grid" },
  { label: "My Uploads", to: "/admin/my-uploads", icon: "folder" },
  { label: "Shared Dataset", to: "/admin/shared-dataset", icon: "database" },
  { label: "Analytics", to: "/admin/analytics", icon: "bar-chart" },
  { label: "Settings", to: "/admin/settings", icon: "settings" },
];

export default function AdminNavigation() {
  return (
    <ul className="nav-list">
      <li>
        <NavLink
          to="/admin/add-admin"
          className={({ isActive }) => `nav-item sidebar__admin-badge${isActive ? " active" : ""}`}
        >
          <Icon name="shield" size={18} /> Administrator
        </NavLink>
      </li>
      {ADMIN_NAV_ITEMS.map((item) => (
        <li key={item.to}>
          <NavLink to={item.to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
            <Icon name={item.icon} size={18} />
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}
