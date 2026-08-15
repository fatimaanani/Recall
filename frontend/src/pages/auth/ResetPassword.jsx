import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import "../../styles/pages/auth/AuthShared.css";
import "../../styles/pages/auth/Login.css";

import Logo from "../../components/Logo";
import Icon from "../../components/Icon";
import leafSparkleDividedImg from "../../assets/decorations/leafSparkleDivided-trimmed.png";
import * as authService from "../../services/authService";
import { getErrorMessage } from "../../services/apiClient";

// Must match backend's MIN_PASSWORD_LENGTH, checked client-side for instant feedback; same constant Register.jsx duplicates for the same reason.
const MIN_PASSWORD_LENGTH = 8;

// Reads ?token= from the reset-link URL.
export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await authService.resetPassword(token, newPassword);
      setSuccess(true);
    } catch (err) {
      // 400 invalid/expired token, from the backend's own generic message
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
            <h1 style={{ fontSize: 22 }}>Reset Password</h1>
            <p>Choose a new password for your account.</p>
          </div>

          {!token && (
            <p className="form-error-banner">
              <Icon name="alert-triangle" size={16} />
              This reset link is missing its token. Please use the link from your email.
            </p>
          )}

          {success ? (
            <>
              <p className="form-success-banner">
                <Icon name="check" size={16} />
                Your password has been reset. You can now log in.
              </p>
              <button
                type="button"
                className="btn btn--primary btn--block"
                style={{ marginTop: 8 }}
                onClick={() => navigate("/login")}
              >
                <Icon name="log-in" size={16} />
                <span>Go to Log In</span>
              </button>
            </>
          ) : (
            <form onSubmit={handleSubmit}>
              {error && (
                <p className="form-error-banner">
                  <Icon name="alert-triangle" size={16} />
                  {error}
                </p>
              )}
              <div className="form-field">
                <label className="form-label" htmlFor="new-password">New Password</label>
                <div className="input-wrap">
                  <Icon name="lock" size={17} />
                  <input
                    id="new-password"
                    type={showPassword ? "text" : "password"}
                    className="text-input has-toggle"
                    placeholder="Enter a new password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                  <button type="button" className="icon-toggle" onClick={() => setShowPassword((v) => !v)} aria-label="Toggle password visibility">
                    <Icon name={showPassword ? "eye-off" : "eye"} size={17} />
                  </button>
                </div>
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor="confirm-password">Confirm Password</label>
                <div className="input-wrap">
                  <Icon name="lock" size={17} />
                  <input
                    id="confirm-password"
                    type={showPassword ? "text" : "password"}
                    className="text-input"
                    placeholder="Confirm your new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="btn btn--primary btn--block"
                style={{ marginTop: 8 }}
                disabled={isSubmitting || !token}
              >
                <Icon name="check" size={16} />
                <span>{isSubmitting ? "Resetting..." : "Reset Password"}</span>
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
