import { useState } from "react";

import Icon from "../../components/Icon";
import { StatusBadge } from "../../components/Badge";
import * as adminService from "../../services/adminService";
import { getErrorMessage } from "../../services/apiClient";
import "../../styles/pages/admin/UserManagement.css";
import greenLeafImg from "../../assets/decorations/greenLeaf-trimmed.png";

const ROLE_LABEL = {
  user: "User",
  admin: "Administrator",
};

export default function AddAdmin() {
  const [email, setEmail] = useState("");

  const [isChecking, setIsChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const [checkedAccount, setCheckedAccount] = useState(null);

  const [isPromoting, setIsPromoting] = useState(false);
  const [promoteError, setPromoteError] = useState("");
  const [promoteSuccess, setPromoteSuccess] = useState("");

  // Editing email invalidates the previous check
  function handleEmailChange(value) {
    setEmail(value);
    setCheckedAccount(null);
    setCheckError("");
    setPromoteError("");
    setPromoteSuccess("");
  }

  function handleCheckAccount(event) {
    event.preventDefault();
    const trimmedEmail = email.trim();
    if (!trimmedEmail || isChecking) return;

    setIsChecking(true);
    setCheckError("");
    setCheckedAccount(null);
    setPromoteError("");
    setPromoteSuccess("");
    adminService
      .lookupUserByEmail(trimmedEmail)
      .then((account) => setCheckedAccount(account))
      .catch((err) => setCheckError(getErrorMessage(err, "Couldn't check that email.")))
      .finally(() => setIsChecking(false));
  }

  function handlePromote() {
    if (!checkedAccount || isPromoting) return;

    // Permanent, irreversible, confirm before submitting
    if (
      !window.confirm(
        `Promote "${checkedAccount.email}" to administrator? This grants full admin access and can't be undone from this page.`
      )
    ) {
      return;
    }

    setIsPromoting(true);
    setPromoteError("");
    setPromoteSuccess("");
    adminService
      .promoteToAdmin(checkedAccount.email)
      .then((data) => {
        setPromoteSuccess(data.message);
        // Update checked account in place, avoids a second Check Account round trip
        setCheckedAccount((prev) => (prev ? { ...prev, role: "admin" } : prev));
      })
      .catch((err) => {
        setPromoteError(getErrorMessage(err, "Couldn't promote that account."));
      })
      .finally(() => setIsPromoting(false));
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          Add Administrator
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
        <p className="page-subtitle">
          Promote an existing registered account to administrator by email.
        </p>
      </div>

      <div className="ui-card" style={{ maxWidth: 480 }}>
        <form onSubmit={handleCheckAccount}>
          <div className="form-field">
            <label className="form-label" htmlFor="lookupEmail">Account Email</label>
            <div className="input-wrap">
              <Icon name="mail" size={17} />
              <input
                id="lookupEmail"
                type="email"
                className="text-input"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => handleEmailChange(e.target.value)}
                disabled={isChecking}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn btn--admin"
            disabled={isChecking || !email.trim()}
          >
            <Icon name="search" size={15} />
            <span>{isChecking ? "Checking..." : "Check Account"}</span>
          </button>

          {checkError && (
            <p className="form-error" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="x" size={14} /> {checkError}
            </p>
          )}
        </form>

        {checkedAccount && (
          <div style={{ marginTop: 20 }}>
            <p className="contact-admin-sent" style={{ marginBottom: 10 }}>
              <Icon name="check" size={13} /> Account Found
            </p>

            <div className="view-panel__row">
              <span className="view-panel__label">Full Name</span>
              <span
                className="view-panel__value"
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <Icon name="user" size={16} /> {checkedAccount.full_name}
              </span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Username</span>
              <span className="view-panel__value">{checkedAccount.username}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Email</span>
              <span className="view-panel__value">{checkedAccount.email}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Current Role</span>
              <span className="view-panel__value">
                {ROLE_LABEL[checkedAccount.role] ?? checkedAccount.role}
              </span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Status</span>
              <span className="view-panel__value">
                <StatusBadge
                  status={checkedAccount.account_status}
                  label={checkedAccount.account_status === "active" ? "Active" : "Suspended"}
                />
              </span>
            </div>

            <div style={{ marginTop: 16 }}>
              {checkedAccount.role === "admin" ? (
                <p
                  className="form-error"
                  style={{ display: "flex", alignItems: "center", gap: 6 }}
                >
                  <Icon name="alert-triangle" size={14} /> This account is already an administrator.
                </p>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn btn--admin"
                    disabled={isPromoting}
                    onClick={handlePromote}
                  >
                    <Icon name="shield" size={15} />
                    <span>{isPromoting ? "Promoting..." : "Promote to Administrator"}</span>
                  </button>
                  {promoteError && (
                    <p
                      className="form-error"
                      style={{ display: "flex", alignItems: "center", gap: 6 }}
                    >
                      <Icon name="x" size={14} /> {promoteError}
                    </p>
                  )}
                </>
              )}

              {promoteSuccess && (
                <p className="contact-admin-sent">
                  <Icon name="check" size={13} /> {promoteSuccess}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
