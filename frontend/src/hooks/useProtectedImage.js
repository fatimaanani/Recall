import { useEffect, useState } from "react";

import apiClient from "../services/apiClient";

// Authenticated image fetch, returns a blob URL for <img src>
export function useProtectedImage(path) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    if (!path) {
      setUrl(null);
      return undefined;
    }

    let objectUrl;
    let cancelled = false;

    apiClient
      .get(path, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setUrl(null);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return url;
}
