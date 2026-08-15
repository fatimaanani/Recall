import { useEffect, useState } from "react";

import apiClient from "../services/apiClient";

// Same authenticated-Blob-to-object-URL technique as useProtectedImage, plus loading/error state since a full clip fetch takes noticeably longer than a thumbnail. Clips are short by construction, so fetching the whole Blob (no HTTP Range/partial playback) is fine.
export function useProtectedMedia(path) {
  const [url, setUrl] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!path) {
      setUrl(null);
      setIsLoading(false);
      setError(null);
      return undefined;
    }

    let objectUrl;
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    apiClient
      .get(path, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (cancelled) return;
        setUrl(null);
        setError(err);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return { url, isLoading, error };
}
