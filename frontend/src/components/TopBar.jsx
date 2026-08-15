import { useEffect, useState } from "react";
import "./TopBar.css";

import Icon from "./Icon";
import GenderAvatar from "./GenderAvatar";
import { useAuth } from "../context/AuthContext";

// Top-right identity strip, avatar + welcome text + logout dropdown
export default function TopBar() {
  const { logout, currentUser } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  // Gender is a real persisted User column, so this always matches Settings' Account Information.
  const avatarKey = currentUser?.gender;

  useEffect(() => {
    if (!menuOpen) return undefined;
    function handleClickOutside(event) {
      if (!event.target.closest(".topbar__menu-wrapper")) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  return (
    <div className="topbar">
      <div className="topbar__menu-wrapper">
        <button
          type="button"
          className="topbar__identity"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
        >
          <GenderAvatar gender={avatarKey} size={40} className="topbar__avatar" />
          <span className="topbar__text">
            <span className="topbar__greeting">Welcome back,</span>
            <span className="topbar__name">{currentUser?.username}</span>
          </span>
          <Icon name="chevron-down" size={16} />
        </button>

        {menuOpen && (
          <div className="topbar__dropdown">
            <button type="button" className="topbar__dropdown-item" onClick={logout}>
              <Icon name="log-out" size={16} />
              Log out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
