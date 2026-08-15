import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../../styles/pages/auth/AuthShared.css";
import "../../styles/pages/auth/Register.css";

import { useAuth } from "../../context/AuthContext";
import Logo from "../../components/Logo";
import Icon from "../../components/Icon";
import GenderAvatar from "../../components/GenderAvatar";
import { getErrorMessage } from "../../services/apiClient";
import leafSprigImg from "../../assets/decorations/halfLeafSprinkleForRegAcc-trimmed.png";

// Must match backend's MIN_PASSWORD_LENGTH, checked client-side for instant feedback
const MIN_PASSWORD_LENGTH = 8;
// Must match backend's MIN_REGISTRATION_AGE, checked client-side for instant feedback; the backend re-validates regardless.
const MIN_REGISTRATION_AGE = 13;

// "YYYY-MM-DD" for the date input's `max` attribute, so the native date picker can't offer a too-recent date.
function maxDateOfBirth() {
  const d = new Date();
  d.setFullYear(d.getFullYear() - MIN_REGISTRATION_AGE);
  return d.toISOString().slice(0, 10);
}

// Real year/month/day age check, never naive year subtraction, same rule as Settings.jsx's calculateAge.
function isOldEnough(dateOfBirth) {
  const dob = new Date(dateOfBirth);
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const hasHadBirthdayThisYear =
    today.getMonth() > dob.getMonth() ||
    (today.getMonth() === dob.getMonth() && today.getDate() >= dob.getDate());
  if (!hasHadBirthdayThisYear) age -= 1;
  return age >= MIN_REGISTRATION_AGE;
}

const OCCUPATION_OPTIONS = [
  { value: "student", label: "Student" },
  { value: "professional", label: "Professional" },
  { value: "educator", label: "Educator" },
  { value: "other", label: "Other" },
];

export default function Register() {
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [gender, setGender] = useState("");
  const [occupation, setOccupation] = useState("");
  const [occupationOther, setOccupationOther] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    // The input's own `required` attribute already blocks an empty submit in practice; this is the same check surfaced as a clear message in case a browser lets it through anyway.
    if (!dateOfBirth) {
      setError("Date of birth is required.");
      return;
    }
    if (!isOldEnough(dateOfBirth)) {
      setError(`You must be at least ${MIN_REGISTRATION_AGE} years old to register.`);
      return;
    }

    setIsSubmitting(true);
    try {
      // Maps local fields onto RegisterRequest, confirmPassword stays client-only
      await register({
        full_name: fullName,
        username,
        email,
        password,
        date_of_birth: dateOfBirth,
        gender: gender || null,
        occupation: occupation === "other" ? occupationOther : occupation || null,
      });
      navigate("/home");
    } catch (err) {
      // getErrorMessage handles both plain-string (409) and array (422) details
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-split register-panel">
      <div className="auth-split__brand-panel">
        <div className="auth-split__brand-inner">
          <Logo />
          <p className="sidebar__tagline" style={{ fontSize: 15, marginTop: 8 }}>
            Find every scene. Every story.
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
        <div className="auth-card auth-card--alt-bg" style={{ maxWidth: 560 }}>
          <div className="auth-card__header">
            <div className="icon-sprinkle-row">
              <img src={leafSprigImg} alt="" className="icon-sprinkle icon-sprinkle-left" />
              <div className="auth-card__icon">
                <Icon name="user-plus" size={22} />
              </div>
              <img src={leafSprigImg} alt="" className="icon-sprinkle icon-sprinkle-right" />
            </div>
            <h1 style={{ fontSize: 22 }}>Create Your Account</h1>
            <p>Join ReCall and start discovering the moments that matter.</p>
          </div>

          <form onSubmit={handleSubmit}>
            {error && (
              <p className="form-error-banner">
                <Icon name="alert-triangle" size={16} />
                {error}
              </p>
            )}
            <div className="form-grid">
              <div className="form-field">
                <label className="form-label" htmlFor="fullName">Full Name</label>
                <div className="input-wrap">
                  <Icon name="user" size={17} />
                  <input id="fullName" className="text-input" placeholder="Enter your full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
                </div>
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor="username">Username</label>
                <div className="input-wrap">
                  <Icon name="user" size={17} />
                  <input id="username" className="text-input" placeholder="Choose a username" value={username} onChange={(e) => setUsername(e.target.value)} required />
                </div>
              </div>

              <div className="form-field field-full">
                <label className="form-label" htmlFor="email">Email Address</label>
                <div className="input-wrap">
                  <Icon name="mail" size={17} />
                  <input id="email" type="email" className="text-input" placeholder="Enter your email" value={email} onChange={(e) => setEmail(e.target.value)} required />
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
                    placeholder="Create a password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={MIN_PASSWORD_LENGTH}
                    required
                  />
                  <button type="button" className="icon-toggle" onClick={() => setShowPassword((v) => !v)} aria-label="Toggle password visibility">
                    <Icon name={showPassword ? "eye-off" : "eye"} size={17} />
                  </button>
                </div>
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor="confirmPassword">Confirm Password</label>
                <div className="input-wrap">
                  <Icon name="lock" size={17} />
                  <input
                    id="confirmPassword"
                    type={showConfirmPassword ? "text" : "password"}
                    className="text-input has-toggle"
                    placeholder="Confirm your password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    minLength={MIN_PASSWORD_LENGTH}
                    required
                  />
                  <button type="button" className="icon-toggle" onClick={() => setShowConfirmPassword((v) => !v)} aria-label="Toggle confirm password visibility">
                    <Icon name={showConfirmPassword ? "eye-off" : "eye"} size={17} />
                  </button>
                </div>
              </div>

              <div className="form-grid-thirds field-full">
                <div className="form-field">
                  <label className="form-label" htmlFor="date-of-birth">Date of Birth</label>
                  <div className="input-wrap">
                    <Icon name="calendar" size={17} />
                    <input
                      id="date-of-birth"
                      type="date"
                      className="text-input"
                      value={dateOfBirth}
                      onChange={(e) => setDateOfBirth(e.target.value)}
                      onKeyDown={(e) => e.preventDefault()}
                      max={maxDateOfBirth()}
                      required
                    />
                  </div>
                </div>

                <div className="form-field">
                  <label className="form-label gender-label-row" htmlFor="gender">
                    Gender
                    <GenderAvatar gender={gender} size={20} className="gender-field-avatar" />
                  </label>
                  <select id="gender" className="select-input" value={gender} onChange={(e) => setGender(e.target.value)} required>
                    <option value="">Select your gender</option>
                    <option value="female">Female</option>
                    <option value="male">Male</option>
                    <option value="other">Other / Prefer not to say</option>
                  </select>
                </div>

                <div className="form-field">
                  <label className="form-label" htmlFor="occupation">Occupation</label>
                  <select id="occupation" className="select-input" value={occupation} onChange={(e) => setOccupation(e.target.value)}>
                    <option value="">Select your occupation</option>
                    {OCCUPATION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {occupation === "other" && (
                <div className="form-field field-full">
                  <label className="form-label" htmlFor="occupationOther">Please specify</label>
                  <div className="input-wrap">
                    <Icon name="briefcase" size={17} />
                    <input
                      id="occupationOther"
                      className="text-input"
                      placeholder="Tell us your occupation"
                      value={occupationOther}
                      onChange={(e) => setOccupationOther(e.target.value)}
                      required
                    />
                  </div>
                </div>
              )}
            </div>

            <label className="checkbox-row" style={{ margin: "8px 0 16px" }}>
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} required />
              I agree to the <a href="#terms" className="link-accent">Terms of Use</a> and <a href="#privacy" className="link-accent">Privacy Policy</a>
            </label>

            <button type="submit" className="btn btn--primary btn--block" disabled={!agreed || isSubmitting}>
              <Icon name="user-plus" size={16} />
              <span>{isSubmitting ? "Creating account..." : "Create Account"}</span>
            </button>
          </form>

          <p className="auth-card__footer">
            Already have an account? <Link to="/login" className="link-accent">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
