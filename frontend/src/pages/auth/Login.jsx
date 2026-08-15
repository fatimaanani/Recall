import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../../styles/pages/auth/AuthShared.css";
import "../../styles/pages/auth/Login.css";

import { useAuth } from "../../context/AuthContext";
import Logo from "../../components/Logo";
import Icon from "../../components/Icon";
import leafSparkleDividedImg from "../../assets/decorations/leafSparkleDivided-trimmed.png";

// Regular-user login
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate("/home");
    } catch (err) {
      // 401 wrong credentials, 403 suspended account
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
            Find every scene.
          </p>
        </div>
        <div className="auth-split__badge">
          <Icon name="shield" size={16} />
          <span>
            <span className="auth-split__badge-title">Secure &bull; Private &bull; Reliable</span>
            <span className="auth-split__badge-subtitle">Your data is encrypted and safe with us.</span>
          </span>
        </div>
      </div>

      <div className="auth-split__form-panel">
        <div className="auth-card">
          <div className="auth-card__header">
            <img src={leafSparkleDividedImg} alt="" className="auth-card__decoration" />
            <h1 style={{ fontSize: 22 }}>Welcome Back!</h1>
            <p>Log in to continue your search.</p>
          </div>

          <form onSubmit={handleSubmit}>
            {error && (
              <p className="form-error-banner">
                <Icon name="alert-triangle" size={16} />
                {error}
              </p>
            )}
            <div className="form-field">
              <label className="form-label" htmlFor="email">Email</label>
              <div className="input-wrap">
                <Icon name="mail" size={17} />
                <input
                  id="email"
                  type="email"
                  className="text-input"
                  placeholder="Enter your email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="password">Password</label>
              <div className="input-wrap">
                <Icon name="lock" size={17} />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  className="text-input has-toggle"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button type="button" className="icon-toggle" onClick={() => setShowPassword((v) => !v)} aria-label="Toggle password visibility">
                  <Icon name={showPassword ? "eye-off" : "eye"} size={17} />
                </button>
              </div>
              <Link to="/forgot-password" className="link-accent" style={{ fontSize: 12.5, alignSelf: "flex-end" }}>
                Forgot password?
              </Link>
            </div>

            <button type="submit" className="btn btn--primary btn--block" style={{ marginTop: 8 }} disabled={isSubmitting}>
              <Icon name="log-in" size={16} />
              <span>{isSubmitting ? "Logging in..." : "Log In"}</span>
            </button>
          </form>

          <p className="auth-card__footer">
            Don&apos;t have an account? <Link to="/register" className="link-accent">Sign up</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
