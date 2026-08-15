import { Link, Navigate } from "react-router-dom";
import "../styles/pages/RoleSelection.css";

import Logo from "../components/Logo";
import Icon from "../components/Icon";
import { hasSplashPlayed } from "../utils/splashGate";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";
import greenLeafUserImg from "../assets/decorations/greenLeaf-trimmed-userTint.png";

// Landing page, pick a portal (admin or user)
export default function RoleSelection() {
  // Hard refresh while logged out, detour through Splash first
  if (!hasSplashPlayed()) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="selection-page">
      <Logo size="lg" />

      <div className="intro">
        <h1 style={{ fontSize: 20, marginTop: 24 }}>
          Welcome to <span className="accent">ReCall</span>
        </h1>
        <p>Discover, search, and explore meaningful moments in your videos using text and audio search.</p>
        <p style={{ color: "var(--color-success)", fontWeight: 500, fontFamily: "var(--font-extended)" }}>Please choose how you want to continue:</p>
      </div>

      <div className="role-cards">
        <div className="role-card role-admin">
          <div className="role-icon-row">
            <img src={greenLeafImg} alt="" className="role-icon-leaf role-icon-leaf--left" />
            <div className="role-icon">
              <Icon name="shield" size={28} />
            </div>
            <img src={greenLeafImg} alt="" className="role-icon-leaf role-icon-leaf--right" />
          </div>
          <div className="role-card__content">
            <h2>Admin</h2>
            <p>Access admin tools to manage users, upload media, process content, and monitor system performance.</p>
            <Link to="/admin/login" className="btn btn--admin btn--block" style={{ marginTop: 8 }}>
              <Icon name="lock" size={16} />
              <span>Continue as Admin</span>
            </Link>
          </div>
        </div>

        <div className="role-card role-user">
          <div className="role-icon-row">
            <img src={greenLeafUserImg} alt="" className="role-icon-leaf role-icon-leaf--left" />
            <div className="role-icon">
              <Icon name="user" size={28} />
            </div>
            <img src={greenLeafUserImg} alt="" className="role-icon-leaf role-icon-leaf--right" />
          </div>
          <div className="role-card__content">
            <h2>User</h2>
            <p>Search and discover scenes using text or audio. View results, save favorites, and manage your library.</p>
            <Link to="/login" className="btn btn--user btn--block" style={{ marginTop: 8 }}>
              <Icon name="user-plus" size={16} />
              <span>Continue as User</span>
            </Link>
          </div>
        </div>
      </div>

      <div className="footer-note">
        <Icon name="shield" size={20} />
        <span>
          Your privacy and data security are our top priorities. Learn more in our{" "}
          <a href="#privacy">Privacy Policy</a>.
        </span>
      </div>

      <p className="legal-links">
        &copy; 2026 ReCall. All rights reserved. &nbsp;
        <a href="#privacy">Privacy Policy</a> &middot; <a href="#terms">Terms of Use</a>
      </p>
    </div>
  );
}
