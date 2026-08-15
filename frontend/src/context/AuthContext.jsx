import { createContext, useContext, useEffect, useMemo, useState } from "react";

import * as authService from "../services/authService";
import { ACCESS_TOKEN_STORAGE_KEY } from "../services/apiClient";
import { clearSearchSession } from "../utils/searchSession";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  // True until the first token-validity check settles, route guards wait on this
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    authService
      .getCurrentUser()
      .then((user) => setCurrentUser(user))
      .catch(() => setCurrentUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  function storeSession({ access_token, user }) {
    sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, access_token);
    setCurrentUser(user);
    return user;
  }

  async function register(payload) {
    const data = await authService.register(payload);
    return storeSession(data);
  }

  async function login(email, password) {
    const data = await authService.login({ email, password });
    return storeSession(data);
  }

  function logout() {
    sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    // Clear the search session so the next login on this tab never sees a previous user's results.
    clearSearchSession();
    setCurrentUser(null);
  }

  function updateCurrentUser(user) {
    setCurrentUser(user);
  }

  const value = useMemo(
    () => ({
      currentUser,
      isLoading,
      isAuthenticated: currentUser !== null,
      isAdmin: currentUser?.role === "admin",
      register,
      login,
      logout,
      updateCurrentUser,
    }),
    [currentUser, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
