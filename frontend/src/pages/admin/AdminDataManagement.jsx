import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import * as adminService from "../../services/adminService";
import { getErrorMessage } from "../../services/apiClient";
import "../../styles/pages/admin/UserManagement.css";
import greenLeafImg from "../../assets/decorations/greenLeaf-trimmed.png";

// Upload timestamp display
function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "--";
}

// Global upload management, every regular user's uploads
export default function AdminDataManagement() {
  const navigate = useNavigate();

  const [uploads, setUploads] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    setIsLoading(true);
    adminService
      .listUploads()
      .then((data) => {
        setUploads(data);
        setErrorMessage("");
      })
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't load uploads.")))
      .finally(() => setIsLoading(false));
  }, []);

  function goToUpload(uploadId) {
    navigate(`/admin/uploads/${uploadId}`);
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          Data Management
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
        <p className="page-subtitle">Every regular user&apos;s upload, across the whole system.</p>
      </div>

      {errorMessage && <p className="form-error" style={{ marginBottom: 12 }}>{errorMessage}</p>}

      <div className="ui-card ui-card--flush ui-card--alt-bg">
        <table className="data-table data-table--stacked">
          <thead>
            <tr>
              <th>Username</th>
              <th>File Name</th>
              <th>File Type</th>
              <th>Date and Time of Upload</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={4} className="text-muted" style={{ padding: "var(--space-md)" }}>
                  Loading uploads...
                </td>
              </tr>
            ) : uploads.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-muted" style={{ padding: "var(--space-md)" }}>
                  No regular-user uploads yet.
                </td>
              </tr>
            ) : (
              uploads.map((upload) => (
                <tr
                  key={upload.id}
                  role="button"
                  tabIndex={0}
                  style={{ cursor: "pointer" }}
                  onClick={() => goToUpload(upload.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      goToUpload(upload.id);
                    }
                  }}
                >
                  <td data-label="Username">{upload.username}</td>
                  <td data-label="File Name">{upload.file_name}</td>
                  <td data-label="File Type">{upload.file_type}</td>
                  <td data-label="Date and Time of Upload">{formatDate(upload.uploaded_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
