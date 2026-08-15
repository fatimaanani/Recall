import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/pages/Search.css";

import { useAuth } from "../context/AuthContext";
import Icon from "../components/Icon";
import AudioFilePill from "../components/AudioFilePill";
import * as searchService from "../services/searchService";
import { getErrorMessage } from "../services/apiClient";
import { startSearchSession } from "../utils/searchSession";
import { useSearchMethodForm } from "../hooks/useSearchMethodForm";
import { SEARCH_METHOD_META } from "../mocks/mockData";

// Same mapping as Home.jsx's method tabs, duplicated here rather than shared.
const METHOD_ICON = {
  exact_text: "type-t",
  semantic: "file-text",
  speech_to_text: "mic",
};

// Search page, explicit method + scope selection
export default function Search() {
  const methodForm = useSearchMethodForm("semantic");
  const [scope, setScope] = useState("both");
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  // Validation and payload shape come from methodForm.buildSubmission(), the same shared logic Home.jsx uses.
  function handleSubmit(event) {
    event.preventDefault();
    setSearchError("");

    const submission = methodForm.buildSubmission();
    if (!submission.ok) {
      setSearchError(submission.error);
      return;
    }

    setIsSearching(true);
    const request =
      submission.kind === "speech"
        ? searchService.searchSpeech({ audioFile: submission.audioFile, search_scope: scope })
        : searchService.searchText({ query_text: submission.query_text, query_type: submission.query_type, search_scope: scope });

    request
      .then((searchResponse) => {
        const queryLabel = submission.kind === "speech" ? submission.audioFile.name : submission.query_text;
        startSearchSession({ searchResponse, queryLabel });
        navigate("/home/results", { state: { searchResponse, queryLabel } });
      })
      .catch((err) =>
        setSearchError(
          getErrorMessage(err, submission.kind === "speech" ? "Couldn't complete the speech search. Please try again." : "Search failed. Please try again.")
        )
      )
      .finally(() => setIsSearching(false));
  }

  return (
    <div className="search-page">
      <div className="page-header">
        <h1 className="page-title">Search</h1>
        <p className="page-subtitle">Choose a method and scope for more control over your search.</p>
      </div>

      <form onSubmit={handleSubmit} className="ui-card search-form-grid">
        <div className="form-field">
          <label className="form-label" htmlFor="query">Query</label>
          <div className="search-bar-wrap">
            <Icon name="search" size={17} className="search-icon" />
            {/* Disabled, not unmounted, while Speech-to-Text is active so the layout stays intact. */}
            <input
              id="query"
              className="search-bar"
              value={methodForm.queryText}
              onChange={(e) => methodForm.setQueryText(e.target.value)}
              placeholder="Type text or describe the scene"
              disabled={methodForm.method === "speech_to_text"}
            />
          </div>
        </div>

        <div className="form-field">
          <span className="form-label">Or upload an audio query (MP3, WAV, FLAC, M4A)</span>
          {methodForm.audioFile ? (
            <AudioFilePill file={methodForm.audioFile} onRemove={methodForm.handleRemoveAudioFile} />
          ) : (
            <label className="action-card" htmlFor="audio-query" style={{ cursor: "pointer" }}>
              <span className="action-icon action-icon-upload">
                <Icon name="upload" size={18} />
              </span>
              <span>
                <strong>Upload Audio</strong>
                <br />
                <span className="text-muted">Search by speech instead of typing</span>
              </span>
              <input
                id="audio-query"
                type="file"
                accept=".mp3,.wav,.flac,.m4a"
                onChange={methodForm.handleAudioFileChange}
                style={{ display: "none" }}
              />
            </label>
          )}
        </div>

        <div className="form-field">
          <span className="form-label">Search method</span>
          <div className="method-tabs">
            {Object.entries(SEARCH_METHOD_META).map(([method, meta]) => (
              <button
                key={method}
                type="button"
                className={`method-tab ${meta.className}${methodForm.method === method ? " active" : ""}`}
                onClick={() => methodForm.setMethod(method)}
              >
                <Icon name={METHOD_ICON[method]} size={15} />
                {meta.label}
              </button>
            ))}
          </div>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="scope">Scope</label>
          <select id="scope" className="select-input" value={scope} onChange={(e) => setScope(e.target.value)} disabled={isAdmin}>
            {!isAdmin && <option value="my_library">My Library</option>}
            <option value="shared_library">Shared Library</option>
            {!isAdmin && <option value="both">Both</option>}
          </select>
        </div>

        <button type="submit" className="btn btn--primary" disabled={isSearching}>
          <Icon name="search" size={16} />
          <span>{isSearching ? "Searching..." : "Search"}</span>
        </button>
        {(searchError || methodForm.fileError) && <p className="form-error">{searchError || methodForm.fileError}</p>}
      </form>
    </div>
  );
}
