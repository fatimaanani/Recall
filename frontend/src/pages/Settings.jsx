import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import "../styles/pages/Settings.css";

import { useAuth } from "../context/AuthContext";
import Icon from "../components/Icon";
import GenderAvatar from "../components/GenderAvatar";
import { MethodBadge, StatusBadge } from "../components/Badge";
import * as adminService from "../services/adminService";
import * as searchService from "../services/searchService";
import * as userService from "../services/userService";
import { getErrorMessage } from "../services/apiClient";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";

// Accordion sections, "data" filtered out for admins (see render below)
const SECTIONS = [
  { id: "account", title: "Account Information", desc: "View and update your personal information and account details.", icon: "user" },
  { id: "privacy", title: "Privacy & Security", desc: "Manage your privacy preferences and keep your account secure.", icon: "shield" },
  { id: "data", title: "Data Management", desc: "Manage your data, downloads, and storage preferences.", icon: "database" },
  { id: "danger", title: "Danger Zone", desc: "Irreversible and sensitive actions. Please proceed with caution.", icon: "alert-triangle" },
];

const OCCUPATION_OPTIONS = [
  { value: "student", label: "Student" },
  { value: "professional", label: "Professional" },
  { value: "educator", label: "Educator" },
  { value: "other", label: "Other" },
];

function resolveInitialOccupation(statusLabel) {
  const match = OCCUPATION_OPTIONS.find((opt) => opt.label.toLowerCase() === (statusLabel || "").toLowerCase());
  if (match && match.value !== "other") {
    return { occupation: match.value, occupationOther: "" };
  }
  return { occupation: "other", occupationOther: statusLabel || "" };
}

// Must match backend's MIN_REGISTRATION_AGE (app/schemas/user.py).
const MIN_REGISTRATION_AGE = 13;

// Date of birth -> age in whole years
function calculateAge(dateOfBirth) {
  if (!dateOfBirth) return null;
  const dob = new Date(dateOfBirth);
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const hasHadBirthdayThisYear =
    today.getMonth() > dob.getMonth() ||
    (today.getMonth() === dob.getMonth() && today.getDate() >= dob.getDate());
  if (!hasHadBirthdayThisYear) age -= 1;
  return age;
}

// snake_case enum value -> display label
function formatEnumLabel(value) {
  if (!value) return "--";
  return value
    .split("_")
    .filter(Boolean)
    .map((word, i) => (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(" ");
}

// Account Details date display, with fallback for null
function formatAccountDate(value, fallback) {
  return value ? new Date(value).toLocaleDateString() : fallback;
}

// Admin message timestamp, date + time
function formatMessageTimestamp(value) {
  return new Date(value).toLocaleString();
}

// Same date style as Home.jsx's Recent Searches, since both show the same underlying data.
function formatSearchedAt(isoString) {
  const date = new Date(isoString);
  const datePart = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timePart = date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${datePart} at ${timePart}`;
}

// Same mapping rule as Home.jsx's historyEntryLabel.
function historyEntryLabel(entry) {
  if (entry.query_type === "speech_to_text") {
    return `Audio: ${entry.original_audio_filename}`;
  }
  return `"${entry.query_text}"`;
}

const SETTINGS_HISTORY_LIMIT = 50;

// Password input with show/hide toggle
function PasswordField({ id, label, value, onChange, show, onToggleShow }) {
  return (
    <div className="password-row">
      <label className="form-label" htmlFor={id}>{label}</label>
      <div className="input-wrap">
        <Icon name="lock" size={17} />
        <input
          id={id}
          type={show ? "text" : "password"}
          className="text-input has-toggle"
          placeholder={label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button type="button" className="icon-toggle" onClick={onToggleShow} aria-label={`Toggle ${label} visibility`}>
          <Icon name={show ? "eye-off" : "eye"} size={17} />
        </button>
      </div>
    </div>
  );
}

// Settings page, shared shell for /settings and /admin/settings
export default function Settings() {
  const { currentUser, isAdmin, updateCurrentUser, logout } = useAuth();
  const location = useLocation();
  const [openSection, setOpenSection] = useState(location.state?.openSection ?? null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [visibleHistoryCount, setVisibleHistoryCount] = useState(9);
  const [openRowMenuId, setOpenRowMenuId] = useState(null);
  // Flips the search-history row menu upward only when it would otherwise overflow past the bottom of the viewport.
  const [historyMenuFlipUp, setHistoryMenuFlipUp] = useState(false);
  const historyMenuDropdownRef = useRef(null);

  // Account Information, editable fields (username, occupation, date_of_birth)
  const [username, setUsername] = useState(currentUser?.username ?? "");
  const [dateOfBirth, setDateOfBirth] = useState(currentUser?.date_of_birth ?? "");

  const initialOccupation = resolveInitialOccupation(currentUser?.occupation);
  const [occupation, setOccupation] = useState(initialOccupation.occupation);
  const [occupationOther, setOccupationOther] = useState(initialOccupation.occupationOther);

  const [isSavingProfile, setIsSavingProfile] = useState(false);
  const [profileSaveError, setProfileSaveError] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);
  const profileSavedTimeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (profileSavedTimeoutRef.current) clearTimeout(profileSavedTimeoutRef.current);
    };
  }, []);

  // Derived live from in-progress dateOfBirth field
  const age = calculateAge(dateOfBirth);

  function handleSaveProfile() {
    setProfileSaveError("");
    setProfileSaved(false);

    // Mirrors the backend's validate_date_of_birth for instant feedback; the backend re-validates regardless.
    if (dateOfBirth) {
      const dob = new Date(dateOfBirth);
      const today = new Date();
      if (dob > today) {
        setProfileSaveError("Date of birth cannot be in the future.");
        return;
      }
      if (age !== null && age < MIN_REGISTRATION_AGE) {
        setProfileSaveError(`You must be at least ${MIN_REGISTRATION_AGE} years old.`);
        return;
      }
    }

    setIsSavingProfile(true);
    if (profileSavedTimeoutRef.current) clearTimeout(profileSavedTimeoutRef.current);
    const occupationValue = occupation === "other" ? occupationOther : occupation;
    userService
      .updateProfile({
        username,
        occupation: occupationValue || null,
        date_of_birth: dateOfBirth || null,
      })
      .then((updatedUser) => {
        // Push saved user into AuthContext, reflects everywhere immediately
        updateCurrentUser(updatedUser);
        setUsername(updatedUser.username);
        setDateOfBirth(updatedUser.date_of_birth ?? "");
        const resolved = resolveInitialOccupation(updatedUser.occupation);
        setOccupation(resolved.occupation);
        setOccupationOther(resolved.occupationOther);
        setProfileSaved(true);
        profileSavedTimeoutRef.current = setTimeout(() => setProfileSaved(false), 1500);
      })
      .catch((err) => setProfileSaveError(getErrorMessage(err, "Couldn't save your changes.")))
      .finally(() => setIsSavingProfile(false));
  }

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordChangeError, setPasswordChangeError] = useState("");
  const [passwordChangeSuccess, setPasswordChangeSuccess] = useState(false);
  const passwordChangeSuccessTimeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (passwordChangeSuccessTimeoutRef.current) clearTimeout(passwordChangeSuccessTimeoutRef.current);
    };
  }, []);

  function handleChangePassword() {
    setPasswordChangeError("");
    setPasswordChangeSuccess(false);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordChangeError("Please fill in all password fields.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordChangeError("New password and confirmation don't match.");
      return;
    }

    setIsChangingPassword(true);
    userService
      .changePassword(currentPassword, newPassword)
      .then(() => {
        // Clear fields only after success -- never leave a submitted
        // password sitting in state longer than necessary.
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setPasswordChangeSuccess(true);
        if (passwordChangeSuccessTimeoutRef.current) clearTimeout(passwordChangeSuccessTimeoutRef.current);
        passwordChangeSuccessTimeoutRef.current = setTimeout(() => setPasswordChangeSuccess(false), 1500);
      })
      .catch((err) => setPasswordChangeError(getErrorMessage(err, "Couldn't update your password.")))
      .finally(() => setIsChangingPassword(false));
  }

  const [deletePassword, setDeletePassword] = useState("");
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [deleteAccountError, setDeleteAccountError] = useState("");

  function handleDeleteAccount() {
    setDeleteAccountError("");
    setIsDeletingAccount(true);
    userService
      .deleteAccount(deletePassword)
      .then(() => {
        // No explicit navigate -- ProtectedRoute reacts to isAuthenticated
        // becoming false and redirects, same convention as TopBar's logout.
        logout();
      })
      .catch((err) => {
        setDeleteAccountError(getErrorMessage(err, "Couldn't delete your account."));
        // Never leave a submitted password sitting in state after a failed
        // attempt -- force retyping on retry.
        setDeletePassword("");
      })
      .finally(() => setIsDeletingAccount(false));
  }

  const [contactEmail, setContactEmail] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [contactSent, setContactSent] = useState(false);
  const [showAdminInbox, setShowAdminInbox] = useState(false);
  const [administrators, setAdministrators] = useState([]);
  const [receivedMessages, setReceivedMessages] = useState([]);
  const [isLoadingInbox, setIsLoadingInbox] = useState(true);
  const [inboxError, setInboxError] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [sendError, setSendError] = useState("");

  // Fetched each time the Data Management section opens, same on-open-fetch pattern as the admin message inbox below.
  const [historyEntries, setHistoryEntries] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    if (isAdmin || openSection !== "data") return;
    setIsLoadingHistory(true);
    setHistoryError("");
    searchService
      .listHistory(SETTINGS_HISTORY_LIMIT)
      .then((entries) => setHistoryEntries(entries))
      .catch((err) => setHistoryError(getErrorMessage(err, "Couldn't load search history.")))
      .finally(() => setIsLoadingHistory(false));
  }, [isAdmin, openSection]);

  // Load recipient list + received messages, each time Danger Zone opens
  useEffect(() => {
    if (!isAdmin || openSection !== "danger") return;
    setIsLoadingInbox(true);
    setInboxError("");
    Promise.all([adminService.listMessageAdministrators(), adminService.listReceivedMessages()])
      .then(([admins, messages]) => {
        setAdministrators(admins);
        setReceivedMessages(messages);
      })
      .catch((err) => setInboxError(getErrorMessage(err, "Couldn't load admin messages.")))
      .finally(() => setIsLoadingInbox(false));
  }, [isAdmin, openSection]);

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!event.target.closest(".menu-wrap")) {
        setOpenRowMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  // No positioning library in this project, so this is a manual viewport-edge measurement.
  useEffect(() => {
    if (openRowMenuId === null) {
      setHistoryMenuFlipUp(false);
      return;
    }
    const dropdownEl = historyMenuDropdownRef.current;
    if (!dropdownEl) return;
    const rect = dropdownEl.getBoundingClientRect();
    setHistoryMenuFlipUp(rect.bottom > window.innerHeight);
  }, [openRowMenuId]);

  function toggleSection(id) {
    setOpenSection((current) => (current === id ? null : id));
  }

  function closeDeleteModal() {
    setConfirmDeleteOpen(false);
    setDeleteConfirmText("");
    setDeletePassword("");
    setDeleteAccountError("");
  }

  function handleContactEmailChange(value) {
    setContactEmail(value);
    setContactSent(false);
    setSendError("");
  }

  function handleContactMessageChange(value) {
    setContactMessage(value);
    setContactSent(false);
    setSendError("");
  }

  // Resolve typed email to administrator id, case-insensitive
  function resolveAdministratorId(email) {
    const normalized = email.trim().toLowerCase();
    const match = administrators.find((admin) => admin.email.toLowerCase() === normalized);
    return match ? match.id : null;
  }

  function handleSendAdminMessage() {
    const recipientId = resolveAdministratorId(contactEmail);
    if (recipientId === null) {
      setSendError("Please choose an administrator from the list.");
      return;
    }

    setSendError("");
    setIsSendingMessage(true);
    adminService
      .sendAdminMessage(recipientId, contactMessage)
      .then(() => {
        setContactSent(true);
        setContactEmail("");
        setContactMessage("");
        // Refresh inbox/badge in case a message arrived meanwhile
        return adminService.listReceivedMessages().then(setReceivedMessages);
      })
      .catch((err) => setSendError(getErrorMessage(err, "Couldn't send your message.")))
      .finally(() => setIsSendingMessage(false));
  }

  const visibleHistory = historyEntries.slice(0, visibleHistoryCount);
  const hasMoreHistory = visibleHistoryCount < historyEntries.length;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          Settings
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
        <p className="page-subtitle">Manage your account, preferences, and data.</p>
      </div>

      {SECTIONS.filter((section) => !(isAdmin && section.id === "data")).map((section) => {
        const isOpen = openSection === section.id;
        return (
          <div key={section.id} className={`ui-card section-card section-card-${section.id}`}>
            <button
              type="button"
              className="section-header"
              aria-expanded={isOpen}
              onClick={() => toggleSection(section.id)}
            >
              <span className="section-icon">
                <Icon name={section.icon} size={22} />
              </span>
              <span>
                <p className="section-title">{section.title}</p>
                <p className="section-desc">{section.desc}</p>
              </span>
              <span className="chevron-icon">
                <Icon name={isOpen ? "chevron-down" : "chevron-right"} size={18} />
              </span>
            </button>

            {isOpen && (
              <div className="section-body">
                {section.id === "account" && (
                  <>
                    <div className="info-grid">
                      <div className="info-avatar-col">
                        <GenderAvatar gender={currentUser?.gender} size={96} />
                      </div>
                      <div className="info-rows">
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="user" size={16} /></span>
                          <span className="info-row-label">Username</span>
                          <span className="info-row-value">
                            <input
                              className="text-input"
                              value={username}
                              onChange={(e) => setUsername(e.target.value)}
                            />
                          </span>
                        </div>
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="user" size={16} /></span>
                          <span className="info-row-label">Full Name</span>
                          <span className="info-row-value">{currentUser?.full_name || "--"}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="mail" size={16} /></span>
                          <span className="info-row-label">Email</span>
                          <span className="info-row-value">{currentUser?.email}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="calendar" size={16} /></span>
                          <span className="info-row-label">Date of Birth</span>
                          <span className="info-row-value">
                            <input
                              type="date"
                              className="text-input"
                              value={dateOfBirth || ""}
                              onChange={(e) => setDateOfBirth(e.target.value)}
                            />
                          </span>
                        </div>
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="calendar" size={16} /></span>
                          <span className="info-row-label">Age</span>
                          <span className="info-row-value">{age ?? "--"}</span>
                        </div>
                        <div className="info-row">
                          <span className="info-row-icon"><Icon name="gender" size={16} /></span>
                          <span className="info-row-label">Gender</span>
                          <span className="info-row-value">{formatEnumLabel(currentUser?.gender)}</span>
                        </div>
                        {!isAdmin && (
                          <div className="info-row">
                            <span className="info-row-icon"><Icon name="briefcase" size={16} /></span>
                            <span className="info-row-label">Occupation</span>
                            <span className="info-row-value">
                              <select className="select-input" value={occupation} onChange={(e) => setOccupation(e.target.value)}>
                                {OCCUPATION_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                              </select>
                              {occupation === "other" && (
                                <input
                                  className="text-input"
                                  style={{ marginTop: 8 }}
                                  placeholder="Tell us your occupation"
                                  value={occupationOther}
                                  onChange={(e) => setOccupationOther(e.target.value)}
                                />
                              )}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="section-divider" />
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={isSavingProfile}
                      onClick={handleSaveProfile}
                    >
                      <Icon name="check" size={15} />
                      <span>{isSavingProfile ? "Saving..." : "Save Changes"}</span>
                    </button>
                    {profileSaveError && <p className="form-error">{profileSaveError}</p>}
                    {profileSaved && (
                      <p className="contact-admin-sent">
                        <Icon name="check" size={13} /> Saved.
                      </p>
                    )}
                  </>
                )}

                {section.id === "privacy" && (
                  <>
                    <div className="ui-card" style={{ position: "relative" }}>
                      <div className="subcard-header" style={{ background: "var(--settings-privacy-bg)", color: "var(--settings-privacy-fg)" }}>
                        Change Password
                      </div>
                      <PasswordField id="currentPassword" label="Current Password" value={currentPassword} onChange={setCurrentPassword} show={showCurrentPassword} onToggleShow={() => setShowCurrentPassword((v) => !v)} />
                      <PasswordField id="newPassword" label="New Password" value={newPassword} onChange={setNewPassword} show={showNewPassword} onToggleShow={() => setShowNewPassword((v) => !v)} />
                      <PasswordField id="confirmNewPassword" label="Confirm Password" value={confirmPassword} onChange={setConfirmPassword} show={showConfirmPassword} onToggleShow={() => setShowConfirmPassword((v) => !v)} />
                      <button
                        type="button"
                        className="btn btn--user"
                        style={{ marginTop: 4 }}
                        disabled={isChangingPassword}
                        onClick={handleChangePassword}
                      >
                        <Icon name="lock" size={15} />
                        <span>{isChangingPassword ? "Updating..." : "Update Password"}</span>
                      </button>
                      {passwordChangeError && <p className="form-error">{passwordChangeError}</p>}
                      {passwordChangeSuccess && (
                        <p className="contact-admin-sent">
                          <Icon name="check" size={13} /> Password updated.
                        </p>
                      )}
                    </div>

                    <div className="ui-card" style={{ position: "relative" }}>
                      <div className="subcard-header" style={{ background: "var(--settings-privacy-bg)", color: "var(--settings-privacy-fg)" }}>
                        Account Details
                      </div>
                      <table className="details-table">
                        <tbody>
                          <tr>
                            <td>Account Created</td>
                            <td>{formatAccountDate(currentUser?.created_at, "--")}</td>
                          </tr>
                          <tr>
                            <td>Last Login</td>
                            <td>{formatAccountDate(currentUser?.last_login, "Never")}</td>
                          </tr>
                          <tr>
                            <td>Email Verified</td>
                            <td>
                              {currentUser?.email_verified ? (
                                <StatusBadge status="ready" label="Verified" />
                              ) : (
                                <StatusBadge status="failed" label="Not Verified" />
                              )}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                {section.id === "data" && !isAdmin && (
                  <>
                    <div className="page-header-row" style={{ margin: "0 0 16px" }}>
                      <h4 style={{ margin: 0 }}>Search History ({historyEntries.length})</h4>
                      <button
                        type="button"
                        className="btn btn--danger-outline btn--sm"
                        disabled
                        title="Clearing search history isn't available yet."
                      >
                        <Icon name="trash-2" size={14} />
                        <span>Clear Search History</span>
                      </button>
                    </div>
                    <div className="table-scroll" style={{ maxHeight: 420, overflowY: "auto", scrollBehavior: "smooth" }}>
                      <table className="data-table data-table--bordered data-table--stacked">
                        <thead>
                          <tr>
                            <th>Query</th>
                            <th>Search Type</th>
                            <th>Results Found</th>
                            <th>Searched At</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {isLoadingHistory ? (
                            <tr><td colSpan={5} className="text-muted">Loading search history...</td></tr>
                          ) : historyError ? (
                            <tr><td colSpan={5} className="form-error">{historyError}</td></tr>
                          ) : visibleHistory.length === 0 ? (
                            <tr><td colSpan={5} className="text-muted">No search history yet.</td></tr>
                          ) : (
                            visibleHistory.map((entry) => (
                              <tr key={entry.id} className="history-row">
                                <td data-label="Query">{historyEntryLabel(entry)}</td>
                                <td data-label="Search Type"><MethodBadge method={entry.query_type} /></td>
                                <td data-label="Results Found">{entry.results_found}</td>
                                <td data-label="Searched At">{formatSearchedAt(entry.created_at)}</td>
                                <td className="history-actions">
                                  <div className="menu-wrap">
                                    <button
                                      type="button"
                                      className="menu-trigger"
                                      onClick={() => setOpenRowMenuId((current) => (current === entry.id ? null : entry.id))}
                                      aria-label="Row actions"
                                    >
                                      <Icon name="more-vertical" size={16} />
                                    </button>
                                    {openRowMenuId === entry.id && (
                                      <div
                                        className={`menu-dropdown${historyMenuFlipUp ? " menu-dropdown--up" : ""}`}
                                        ref={historyMenuDropdownRef}
                                      >
                                        <button type="button" disabled title="Hiding a search isn't available yet.">Hide Search</button>
                                        <button type="button" className="danger" disabled title="Deleting a search isn't available yet.">Delete Search</button>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                    {hasMoreHistory && (
                      <button
                        type="button"
                        className="btn btn--outline btn--sm"
                        style={{ marginTop: 16 }}
                        onClick={() => setVisibleHistoryCount((count) => count + 5)}
                      >
                        View More
                      </button>
                    )}
                  </>
                )}

                {section.id === "danger" && !isAdmin && (
                  <div className="danger-card">
                    <div className="danger-header">
                      <Icon name="alert-triangle" size={24} style={{ color: "var(--settings-danger-fg)" }} />
                      <h2>Danger Zone</h2>
                    </div>
                    <p className="text-muted" style={{ margin: 0 }}>
                      Irreversible and sensitive actions. Please proceed with caution.
                    </p>

                    <div className="danger-row">
                      <span className="danger-row-icon">
                        <Icon name="trash-2" size={24} />
                      </span>
                      <div className="danger-row-text">
                        <strong style={{ color: "var(--settings-danger-fg)" }}>Delete Account</strong>
                        <p style={{ margin: "4px 0 0" }}>Once you delete your account, there is no going back. This action is permanent.</p>
                      </div>
                      <button type="button" className="btn btn--danger" onClick={() => setConfirmDeleteOpen(true)}>
                        <Icon name="trash-2" size={15} />
                        <span>Delete Account</span>
                      </button>
                    </div>

                    <h4 style={{ marginBottom: 12 }}>What Will Be Deleted?</h4>
                    <ul className="danger-list">
                      <li><Icon name="user" size={16} /> Your account and profile information</li>
                      <li><Icon name="clock" size={16} /> All search history and queries</li>
                      <li><Icon name="film" size={16} /> Uploaded media and generated clips</li>
                      <li><Icon name="settings" size={16} /> All settings and preferences</li>
                    </ul>

                    <div className="safety-card">
                      <span className="safety-card-icon">
                        <Icon name="shield" size={20} />
                      </span>
                      <p style={{ margin: 0, fontSize: 13 }}>
                        Your privacy matters to us. If you're having an issue with your account, we recommend contacting support before deleting -- most problems can be resolved without losing your data.
                      </p>
                    </div>
                  </div>
                )}
                {section.id === "danger" && isAdmin && (
                  <div className="danger-card">
                    <div className="danger-header">
                      <Icon name="alert-triangle" size={24} style={{ color: "var(--settings-danger-fg)" }} />
                      <h2>Danger Zone</h2>
                    </div>
                    <p className="text-muted" style={{ margin: 0 }}>
                      Irreversible and sensitive actions. Please proceed with caution.
                    </p>

                    <div className="danger-row">
                      <span className="danger-row-icon">
                        <Icon name="shield" size={24} />
                      </span>
                      <div className="danger-row-text">
                        <strong style={{ color: "var(--settings-danger-fg)" }}>Account Deletion</strong>
                        <p style={{ margin: "4px 0 0" }}>
                          Administrator accounts cannot delete themselves through this page.
                          Please contact another administrator by a message below
                          and ask them to remove this account from User Management instead.
                        </p>
                      </div>
                    </div>

                    <div className="admin-inbox">
                      <button
                        type="button"
                        className="admin-inbox__toggle"
                        aria-expanded={showAdminInbox}
                        onClick={() => setShowAdminInbox((v) => !v)}
                      >
                        <span>
                          <Icon name="bell" size={16} />
                          Messages from Admins
                          {receivedMessages.length > 0 && (
                            <span className="admin-inbox__count">{receivedMessages.length}</span>
                          )}
                        </span>
                        <Icon name={showAdminInbox ? "chevron-down" : "chevron-right"} size={16} />
                      </button>
                      {showAdminInbox && (
                        <div className="admin-inbox__list">
                          {isLoadingInbox ? (
                            <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>Loading messages...</p>
                          ) : inboxError ? (
                            <p className="form-error" style={{ margin: 0 }}>{inboxError}</p>
                          ) : receivedMessages.length > 0 ? (
                            receivedMessages.map((msg) => (
                              <div key={msg.id} className="admin-inbox__item">
                                <strong>{msg.sender_full_name}</strong>
                                <p>{msg.message}</p>
                                <span className="admin-inbox__item-time">{formatMessageTimestamp(msg.created_at)}</span>
                              </div>
                            ))
                          ) : (
                            <p className="text-muted" style={{ margin: 0, fontSize: 13 }}>No messages yet.</p>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="ui-card contact-admin-card" style={{ position: "relative" }}>
                      <div className="subcard-header" style={{ background: "var(--settings-danger-bg)", color: "var(--settings-danger-fg)" }}>
                        Contact an Administrator
                      </div>
                      <div className="form-field">
                        <label className="form-label" htmlFor="contactAdminEmail">Admin's Email</label>
                        <div className="input-wrap">
                          <Icon name="mail" size={17} />
                          <input
                            id="contactAdminEmail"
                            type="email"
                            className="text-input"
                            placeholder="admin@example.com"
                            value={contactEmail}
                            onChange={(e) => handleContactEmailChange(e.target.value)}
                            list="adminEmailOptions"
                            autoComplete="off"
                          />
                          {/* Native datalist, suggests active admins' emails */}
                          <datalist id="adminEmailOptions">
                            {administrators.map((admin) => (
                              <option key={admin.id} value={admin.email} />
                            ))}
                          </datalist>
                        </div>
                      </div>
                      <div className="form-field">
                        <label className="form-label" htmlFor="contactAdminMessage">Message</label>
                        <textarea
                          id="contactAdminMessage"
                          className="text-input"
                          placeholder="Explain what you'd like this admin to do..."
                          value={contactMessage}
                          onChange={(e) => handleContactMessageChange(e.target.value)}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn--danger"
                        disabled={!contactEmail.trim() || !contactMessage.trim() || isSendingMessage}
                        onClick={handleSendAdminMessage}
                      >
                        <Icon name="send" size={14} />
                        <span>{isSendingMessage ? "Sending..." : "Send Message"}</span>
                      </button>
                      {sendError && <p className="form-error">{sendError}</p>}
                      {contactSent && (
                        <p className="contact-admin-sent">
                          <Icon name="check" size={13} /> Message sent.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {confirmDeleteOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card">
            <button type="button" className="modal-close" onClick={closeDeleteModal} aria-label="Close">
              <Icon name="x" size={18} />
            </button>
            <div className="modal-icon">
              <Icon name="alert-triangle" size={26} />
            </div>
            <h3>Delete Account?</h3>
            <p>Are you sure you want to delete your account? This action cannot be undone.</p>
            <input
              className="text-input"
              placeholder="Type DELETE to confirm"
              style={{ marginBottom: 12 }}
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              disabled={isDeletingAccount}
            />
            <input
              type="password"
              className="text-input"
              placeholder="Enter your password"
              style={{ marginBottom: 12 }}
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              disabled={isDeletingAccount}
              autoComplete="current-password"
            />
            {deleteAccountError && <p className="form-error">{deleteAccountError}</p>}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn--secondary btn--block"
                onClick={closeDeleteModal}
                disabled={isDeletingAccount}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--danger btn--block"
                disabled={deleteConfirmText !== "DELETE" || !deletePassword || isDeletingAccount}
                onClick={handleDeleteAccount}
              >
                {isDeletingAccount ? "Deleting..." : "Delete My Account"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
