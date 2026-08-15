import { Fragment, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import Icon from "../../components/Icon";
import { StatusBadge } from "../../components/Badge";
import AssetPlaceholder from "../../components/AssetPlaceholder";
import * as adminService from "../../services/adminService";
import { getErrorMessage } from "../../services/apiClient";
import { useProtectedImage } from "../../hooks/useProtectedImage";
import "../../styles/pages/admin/UserManagement.css";
import greenLeafImg from "../../assets/decorations/greenLeaf-trimmed.png";

const UPLOAD_STATUS_LABEL = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Processed",
  failed: "Failed",
};

// User upload row, links to admin upload-details page
function UserUploadRow({ upload }) {
  const thumbnailUrl = useProtectedImage(
    upload.has_thumbnail ? adminService.getUploadThumbnailPath(upload.id) : null
  );

  return (
    <Link
      to={`/admin/uploads/${upload.id}`}
      className="view-panel__row"
      style={{ alignItems: "center", gap: 10, textDecoration: "none", color: "inherit" }}
    >
      <span style={{ flexShrink: 0, width: 36, height: 36, borderRadius: 6, overflow: "hidden", display: "flex" }}>
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <AssetPlaceholder path={`assets/thumbnails/${upload.id}.png`} width={36} height={36} />
        )}
      </span>
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {upload.title}
      </span>
      <StatusBadge status={upload.status} label={UPLOAD_STATUS_LABEL[upload.status] ?? upload.status} />
      <span className="text-muted" style={{ flexShrink: 0, fontSize: 12.5 }}>
        {formatDate(upload.uploaded_at)}
      </span>
    </Link>
  );
}

function formatBytes(bytes) {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes > 0) return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  return "0 KB";
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString() : "--";
}

// User Management page, view/suspend/reactivate/delete regular-user accounts
export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  // Row mid-request, disables that row's own buttons only
  const [busyUserId, setBusyUserId] = useState(null);

  // Only one row's delete-confirm open at a time
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteConfirmError, setDeleteConfirmError] = useState("");

  // View side panel, holds the user object it's showing, null when closed
  const [viewUser, setViewUser] = useState(null);
  const [viewUserUploads, setViewUserUploads] = useState([]);
  const [isLoadingViewUserUploads, setIsLoadingViewUserUploads] = useState(false);

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    refreshUsers();
  }, []);

  // Fetch this user's uploads when View panel opens for a different user
  useEffect(() => {
    if (!viewUser) {
      setViewUserUploads([]);
      return;
    }
    setIsLoadingViewUserUploads(true);
    adminService
      .getUserUploads(viewUser.id)
      .then(setViewUserUploads)
      .catch(() => setViewUserUploads([]))
      .finally(() => setIsLoadingViewUserUploads(false));
  }, [viewUser?.id]);

  // Reopen View panel after returning from AdminUploadDetail's delete action
  useEffect(() => {
    const reopenUserId = location.state?.reopenUserId;
    if (!reopenUserId || users.length === 0) return;
    const match = users.find((u) => u.id === reopenUserId);
    if (match) setViewUser(match);
    navigate(location.pathname, { replace: true, state: {} });
  }, [users, location.state, location.pathname, navigate]);

  useEffect(() => {
    if (!viewUser) return undefined;
    function handleOutsideClick(event) {
      if (!event.target.closest(".view-panel") && !event.target.closest(".view-panel-trigger")) {
        setViewUser(null);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [viewUser]);

  function refreshUsers() {
    setIsLoading(true);
    adminService
      .listUsers()
      .then((data) => {
        setUsers(data);
        setErrorMessage("");
      })
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't load users.")))
      .finally(() => setIsLoading(false));
  }

  function handleToggleSuspend(user) {
    setBusyUserId(user.id);
    const action =
      user.account_status === "suspended" ? adminService.reactivateUser : adminService.suspendUser;

    action(user.id)
      .then((updated) => {
        setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
        setViewUser((prev) => (prev && prev.id === updated.id ? updated : prev));
      })
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't update that account.")))
      .finally(() => setBusyUserId(null));
  }

  function openDeleteConfirm(userId) {
    setDeleteConfirmId(userId);
    setDeleteConfirmText("");
    setDeleteConfirmError("");
  }

  function closeDeleteConfirm() {
    setDeleteConfirmId(null);
    setDeleteConfirmText("");
    setDeleteConfirmError("");
  }

  function handleConfirmDelete(user) {
    setBusyUserId(user.id);
    setDeleteConfirmError("");
    adminService
      .deleteUser(user.id, deleteConfirmText)
      .then(() => {
        setUsers((prev) => prev.filter((u) => u.id !== user.id));
        if (viewUser?.id === user.id) setViewUser(null);
        closeDeleteConfirm();
      })
      .catch((err) => {
        setDeleteConfirmError(getErrorMessage(err, "Couldn't delete that account."));
      })
      .finally(() => setBusyUserId(null));
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          User Management
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
        <p className="page-subtitle">Manage regular-user accounts. Administrator accounts are not shown here.</p>
      </div>

      {errorMessage && <p className="form-error" style={{ marginBottom: 12 }}>{errorMessage}</p>}

      <div className="ui-card ui-card--flush ui-card--alt-bg">
        <table className="data-table data-table--stacked">
          <thead>
            <tr>
              <th>Full Name</th>
              <th>Username</th>
              <th>Email</th>
              <th>Storage Used</th>
              <th>Uploads</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="text-muted" style={{ padding: "var(--space-md)" }}>
                  Loading users...
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-muted" style={{ padding: "var(--space-md)" }}>
                  No regular-user accounts yet.
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <Fragment key={user.id}>
                  <tr>
                    <td data-label="Full Name">{user.full_name}</td>
                    <td data-label="Username">{user.username}</td>
                    <td data-label="Email">{user.email}</td>
                    <td data-label="Storage Used">{formatBytes(user.storage_used_bytes)}</td>
                    <td data-label="Uploads">{user.upload_count}</td>
                    <td data-label="Status">
                      <StatusBadge
                        status={user.account_status}
                        label={user.account_status === "active" ? "Active" : "Suspended"}
                      />
                    </td>
                    <td className="table-actions" data-label="Actions">
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm view-panel-trigger"
                        onClick={() => setViewUser(user)}
                      >
                        <Icon name="eye" size={13} />
                        <span>View</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm"
                        disabled={busyUserId === user.id}
                        onClick={() => handleToggleSuspend(user)}
                      >
                        <Icon name={user.account_status === "suspended" ? "check" : "shield"} size={13} />
                        <span>{user.account_status === "suspended" ? "Reactivate" : "Suspend"}</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn--danger-outline btn--sm"
                        disabled={busyUserId === user.id}
                        onClick={() =>
                          deleteConfirmId === user.id ? closeDeleteConfirm() : openDeleteConfirm(user.id)
                        }
                      >
                        <Icon name="trash-2" size={13} />
                        <span>Delete</span>
                      </button>
                    </td>
                  </tr>
                  {deleteConfirmId === user.id && (
                    <tr>
                      <td colSpan={7}>
                        <div className="delete-confirm-row">
                          <p className="delete-confirm-row__prompt">
                            Type <strong>{user.username}</strong> to permanently delete this account. This can&apos;t be undone.
                          </p>
                          <div className="delete-confirm-row__controls">
                            <input
                              type="text"
                              className="delete-confirm-row__input"
                              value={deleteConfirmText}
                              onChange={(e) => setDeleteConfirmText(e.target.value)}
                              placeholder={user.username}
                              autoFocus
                            />
                            <button
                              type="button"
                              className="btn btn--danger-outline btn--sm"
                              disabled={busyUserId === user.id || deleteConfirmText.length === 0}
                              onClick={() => handleConfirmDelete(user)}
                            >
                              Confirm Delete
                            </button>
                            <button type="button" className="btn btn--secondary btn--sm" onClick={closeDeleteConfirm}>
                              Cancel
                            </button>
                          </div>
                          {deleteConfirmError && <p className="form-error">{deleteConfirmError}</p>}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      {viewUser && (
        <div className="view-panel">
          <div className="view-panel__header">
            <h3 style={{ margin: 0, fontSize: 15 }}>Account Details</h3>
            <button
              type="button"
              className="view-panel__close"
              aria-label="Close"
              onClick={() => setViewUser(null)}
            >
              <Icon name="x" size={18} />
            </button>
          </div>
          <div className="view-panel__body">
            <div className="view-panel__row">
              <span className="view-panel__label">Full Name</span>
              <span className="view-panel__value">{viewUser.full_name}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Username</span>
              <span className="view-panel__value">{viewUser.username}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Email</span>
              <span className="view-panel__value">{viewUser.email}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Status</span>
              <span className="view-panel__value">
                <StatusBadge
                  status={viewUser.account_status}
                  label={viewUser.account_status === "active" ? "Active" : "Suspended"}
                />
              </span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Storage Used</span>
              <span className="view-panel__value">{formatBytes(viewUser.storage_used_bytes)}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Uploads</span>
              <span className="view-panel__value">{viewUser.upload_count}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Occupation</span>
              <span className="view-panel__value">{viewUser.occupation || "--"}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Gender</span>
              <span className="view-panel__value" style={{ textTransform: "capitalize" }}>{viewUser.gender || "--"}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Date of Birth</span>
              <span className="view-panel__value">{formatDate(viewUser.date_of_birth)}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Account Created</span>
              <span className="view-panel__value">{formatDate(viewUser.created_at)}</span>
            </div>

            <h4 style={{ margin: "var(--space-md) 0 4px" }}>Uploads ({viewUser.upload_count})</h4>
            {isLoadingViewUserUploads ? (
              <p className="text-muted" style={{ margin: 0 }}>Loading uploads...</p>
            ) : viewUserUploads.length === 0 ? (
              <p className="text-muted" style={{ margin: 0 }}>This user hasn&apos;t uploaded anything yet.</p>
            ) : (
              viewUserUploads.map((upload) => <UserUploadRow key={upload.id} upload={upload} />)
            )}
          </div>
        </div>
      )}
    </div>
  );
}
