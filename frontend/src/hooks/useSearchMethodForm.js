import { useState } from "react";

// Shared search-method state machine for Home.jsx and Search.jsx: the visibly active method is the single source of truth, and a file can only be present while method === "speech_to_text" (switching methods always clears the other field).
const ALLOWED_AUDIO_EXTENSIONS = ["mp3", "wav", "flac", "m4a"];

function getExtension(fileName) {
  return fileName.split(".").pop()?.toLowerCase() ?? "";
}

export function useSearchMethodForm(defaultMethod = "exact_text") {
  const [method, setMethodRaw] = useState(defaultMethod);
  const [queryText, setQueryText] = useState("");
  const [audioFile, setAudioFile] = useState(null);
  const [fileError, setFileError] = useState("");

  function setMethod(nextMethod) {
    setFileError("");
    if (nextMethod === "speech_to_text") {
      setQueryText("");
    } else {
      setAudioFile(null);
    }
    setMethodRaw(nextMethod);
  }

  // Extension check is a fast client-side fail only, the backend re-validates by magic bytes. Resetting the input value lets selecting the same file again still fire onChange.
  function handleAudioFileChange(event) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) return;
    setFileError("");
    if (!ALLOWED_AUDIO_EXTENSIONS.includes(getExtension(file.name))) {
      setFileError("Unsupported audio format. Use MP3, WAV, FLAC, or M4A.");
      return;
    }
    setAudioFile(file);
    setQueryText("");
    setMethodRaw("speech_to_text");
  }

  // Removes the file but leaves the method as Speech-to-Text; submit-time validation below catches "no file yet".
  function handleRemoveAudioFile() {
    setAudioFile(null);
  }

  // Submit-time validation + payload, branching only on the active method.
  function buildSubmission() {
    if (method === "speech_to_text") {
      if (!audioFile) {
        return { ok: false, error: "Select an audio file to search by speech." };
      }
      return { ok: true, kind: "speech", audioFile };
    }
    const trimmed = queryText.trim();
    if (!trimmed) {
      return { ok: false, error: "Type something to search for." };
    }
    return { ok: true, kind: "text", query_text: trimmed, query_type: method };
  }

  return {
    method,
    setMethod,
    queryText,
    setQueryText,
    audioFile,
    fileError,
    handleAudioFileChange,
    handleRemoveAudioFile,
    buildSubmission,
  };
}
