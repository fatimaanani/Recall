import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

// Admin route guard
export default function AdminRoute() {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();

  // Still checking stored token, wait rather than redirect
  if (isLoading) {
    return null;
  }
  if (!isAuthenticated || !isAdmin) {
    return <Navigate to="/admin/login" replace />;
  }
  return <Outlet />;
}
