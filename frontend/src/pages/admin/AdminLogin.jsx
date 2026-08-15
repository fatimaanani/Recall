import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "../../styles/pages/auth/AuthShared.css";

import { useAuth } from "../../context/AuthContext";
import Logo from "../../components/Logo";
import Icon from "../../components/Icon";
import leafSparkleDividedImg from "../../assets/decorations/leafSparkleDivided-trimmed.png";

// Admin login, role check rejects a non-admin account after authenticating
export default function AdminLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login, logout } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const user = await login(email, password);
      if (user.role !== "admin") {
        logout();
        setError("This login is for administrators only.");
        return;
      }
      navigate("/admin/users");
    } catch (err) {
      setError(err.response?.data?.detail ?? "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-split login-panel">
      <div className="auth-split__brand-panel">
        <div className="auth-split__brand-inner">
          <Logo />
          <p className="sidebar__tagline" style={{ fontSize: 15, marginTop: 8 }}>
            Administrator portal
          </p>
        </div>
        <div className="auth-split__badge">
          <Icon name="shield" size={16} />
          <span>
            <span className="auth-split__badge-title">Restricted access.</span>
            <span className="auth-split__badge-subtitle">Administrator accounts are provisioned, not self-registered.</span>
          </span>
        </div>
      </div>

      <div className="auth-split__form-panel">
        <div className="auth-card">
          <div className="auth-card__header">
            <img src={leafSparkleDividedImg} alt="" className="auth-card__decoration" />
            <h1 style={{ fontSize: 22 }}>Administrator Login</h1>
            <p>Sign in with your administrator credentials.</p>
          </div>

          <form onSubmit={handleSubmit}>
            {error && (
              <p className="form-error-banner">
                <Icon name="alert-triangle" size={16} />
                {error}
              </p>
            )}
            <div className="form-field">
              <label className="form-label" htmlFor="admin-email">Email</label>
              <div className="input-wrap">
                <Icon name="mail" size={17} />
                <input id="admin-email" type="email" className="text-input" placeholder="Enter your email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-password">Password</label>
              <div className="input-wrap">
                <Icon name="lock" size={17} />
                <input id="admin-password" type="password" className="text-input" placeholder="Enter your password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
            </div>

            <button type="submit" className="btn btn--admin btn--block" style={{ marginTop: 8 }} disabled={isSubmitting}>
              <Icon name="log-in" size={16} />
              <span>{isSubmitting ? "Logging in..." : "Log In"}</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
