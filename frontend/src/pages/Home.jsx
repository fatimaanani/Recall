import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/pages/Home.css";

import Icon from "../components/Icon";
import AudioFilePill from "../components/AudioFilePill";
import * as searchService from "../services/searchService";
import { getErrorMessage } from "../services/apiClient";
import { startSearchSession } from "../utils/searchSession";
import { useSearchMethodForm } from "../hooks/useSearchMethodForm";
import { SEARCH_METHOD_META } from "../mocks/mockData";

const METHOD_ORDER = ["exact_text", "semantic", "speech_to_text"];
const METHOD_ICON = {
  exact_text: "type-t",
  semantic: "file-text",
  speech_to_text: "mic",
};
const RECENT_SEARCHES_LIMIT = 4;

// Matches the short-month date format used elsewhere in the app (see MediaCard.jsx), plus a time-of-day.
function formatSearchedAt(isoString) {
  const date = new Date(isoString);
  const datePart = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timePart = date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${datePart} at ${timePart}`;
}

// Same field mapping as Settings: typed searches show the query text in quotes, speech_to_text shows the filename.
function historyEntryLabel(entry) {
  if (entry.query_type === "speech_to_text") {
    return `Audio: ${entry.original_audio_filename}`;
  }
  return `"${entry.query_text}"`;
}

export default function Home() {
  const methodForm = useSearchMethodForm("exact_text");
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [recentSearches, setRecentSearches] = useState([]);
  const [isLoadingRecent, setIsLoadingRecent] = useState(true);
  const [recentError, setRecentError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    setIsLoadingRecent(true);
    setRecentError("");
    searchService
      .listHistory(RECENT_SEARCHES_LIMIT)
      .then((entries) => setRecentSearches(entries))
      .catch((err) => setRecentError(getErrorMessage(err, "Couldn't load recent searches.")))
      .finally(() => setIsLoadingRecent(false));
  }, []);

  // Validation and payload shape come from methodForm.buildSubmission(), which branches on the active method tab, not on whether a file is attached.
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
        ? searchService.searchSpeech({ audioFile: submission.audioFile, search_scope: "both" })
        : searchService.searchText({ query_text: submission.query_text, query_type: submission.query_type, search_scope: "both" });

    request
      .then((searchResponse) => {
        const queryLabel = submission.kind === "speech" ? submission.audioFile.name : submission.query_text;
        // sessionStorage is what survives a refresh or a Scene Viewer round trip; route state is just an immediate-render optimization.
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

  function goToRecentSearches() {
    navigate("/settings", { state: { openSection: "data" } });
  }

  return (
    <div className="home-page">
      <h1>
        Find a scene from <span style={{ color: "var(--method-text)" }}>a quote</span>,
        <br />
        an <span style={{ color: "var(--method-speech)" }}>audio</span> clip, or a{" "}
        <span style={{ color: "var(--method-semantic)" }}>memory</span>.
      </h1>
      <p>Search across your media collection using text, meaning, or audio.</p>

      <form onSubmit={handleSubmit} className="search-bar-wrap">
        <Icon name="search" size={18} className="search-icon" />
        {methodForm.audioFile ? (
          <div className="search-bar search-bar--file-mode">
            <AudioFilePill file={methodForm.audioFile} onRemove={methodForm.handleRemoveAudioFile} />
          </div>
        ) : (
          <input
            className="search-bar"
            placeholder="Search for a quote, dialogue, or keyword..."
            value={methodForm.queryText}
            onChange={(e) => methodForm.setQueryText(e.target.value)}
          />
        )}
        <button type="submit" className="btn btn--primary" aria-label="Search" disabled={isSearching}>
          <Icon name="search" size={16} />
          <span>{isSearching ? "Searching..." : "Search"}</span>
        </button>
      </form>
      {(searchError || methodForm.fileError) && (
        <p className="form-error" style={{ textAlign: "center", maxWidth: 720, margin: "8px auto 0" }}>
          {searchError || methodForm.fileError}
        </p>
      )}

      <div className="method-tabs">
        <span style={{ alignSelf: "center", fontSize: 13, color: "var(--color-text-secondary)" }}>Search by:</span>
        {METHOD_ORDER.map((method) => (
          <button
            key={method}
            type="button"
            className={`method-tab ${SEARCH_METHOD_META[method].className}${methodForm.method === method ? " active" : ""}`}
            onClick={() => methodForm.setMethod(method)}
          >
            <Icon name={METHOD_ICON[method]} size={15} />
            {SEARCH_METHOD_META[method].label}
          </button>
        ))}
      </div>

      <div className="quick-actions">
        <label className="action-card" style={{ cursor: "pointer" }}>
          <span className="action-icon action-icon-upload">
            <Icon name="upload" size={18} />
          </span>
          <span>
            <strong>Upload Audio</strong>
            <br />
            <span className="text-muted">Upload an audio file to search</span>
          </span>
          <input type="file" accept=".mp3,.wav,.flac,.m4a" onChange={methodForm.handleAudioFileChange} style={{ display: "none" }} />
        </label>
        <button type="button" className="action-card" disabled title="Microphone recording is coming soon">
          <span className="action-icon action-icon-record">
            <Icon name="mic" size={18} />
          </span>
          <span>
            <strong>Record Audio</strong>
            <br />
            <span className="text-muted">Coming soon</span>
          </span>
        </button>
      </div>

      <div className="recent-header">
        <h3>Recent Searches</h3>
        <button type="button" className="view-all-link" onClick={goToRecentSearches}>
          View All <Icon name="arrow-right" size={13} />
        </button>
      </div>
      {isLoadingRecent ? (
        <p className="text-muted">Loading recent searches...</p>
      ) : recentError ? (
        <p className="form-error">{recentError}</p>
      ) : recentSearches.length === 0 ? (
        <p className="text-muted">You haven't searched anything yet.</p>
      ) : (
        <div className="recent-grid">
          {recentSearches.map((entry) => (
            <div key={entry.id} className="recent-card">
              <div className="recent-card-top">
                <span className="recent-card-icon">
                  <Icon name={METHOD_ICON[entry.query_type]} size={15} />
                </span>
                <span className="recent-card-text">{historyEntryLabel(entry)}</span>
              </div>
              <span className="recent-card-meta">{entry.results_found} results &middot; {formatSearchedAt(entry.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
