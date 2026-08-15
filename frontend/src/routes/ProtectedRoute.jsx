import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { hasSplashPlayed } from "../utils/splashGate";

// Regular-user route guard
export default function ProtectedRoute() {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();

  // Still checking stored token, wait rather than redirect
  if (isLoading) {
    return null;
  }
  if (!isAuthenticated) {
    return <Navigate to={hasSplashPlayed() ? "/role-selection" : "/"} replace />;
  }
  if (isAdmin) {
    return <Navigate to="/admin/users" replace />;
  }
  return <Outlet />;
}
