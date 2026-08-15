import { useEffect, useState } from "react";

// Dark mode preference, shared by UserLayout and AdminLayout
const DARK_MODE_STORAGE_KEY = "recallDarkMode";

// Read persisted preference, localStorage (survives browser close, unlike sessionStorage)
function readStoredPreference() {
  return localStorage.getItem(DARK_MODE_STORAGE_KEY) === "true";
}

export function useDarkMode() {
  const [darkMode, setDarkMode] = useState(readStoredPreference);

  useEffect(() => {
    document.documentElement.classList.toggle("dark-mode", darkMode);
    localStorage.setItem(DARK_MODE_STORAGE_KEY, String(darkMode));
  }, [darkMode]);

  return [darkMode, setDarkMode];
}
