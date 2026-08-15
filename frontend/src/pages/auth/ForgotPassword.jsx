import { useState } from "react";
import { Link } from "react-router-dom";
import "../../styles/pages/auth/AuthShared.css";
import "../../styles/pages/auth/Login.css";

import Logo from "../../components/Logo";
import Icon from "../../components/Icon";
import leafSparkleDividedImg from "../../assets/decorations/leafSparkleDivided-trimmed.png";
import * as authService from "../../services/authService";
import { getErrorMessage } from "../../services/apiClient";

// Always shows the same success message regardless of whether the email matches an account, since the backend never reveals that either.
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await authService.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(getErrorMessage(err, "Something went wrong. Please try again."));
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
            <h1 style={{ fontSize: 22 }}>Forgot Password?</h1>
            <p>Enter your email and we&apos;ll send you a reset link.</p>
          </div>

          {submitted ? (
            <p className="form-success-banner" style={{ marginTop: 8 }}>
              <Icon name="check" size={16} />
              If an account exists for that email, a password reset link has been sent.
            </p>
          ) : (
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

              <button type="submit" className="btn btn--primary btn--block" style={{ marginTop: 8 }} disabled={isSubmitting}>
                <Icon name="mail" size={16} />
                <span>{isSubmitting ? "Sending..." : "Send Reset Link"}</span>
              </button>
            </form>
          )}

          <p className="auth-card__footer">
            <Link to="/login" className="link-accent">Back to log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
