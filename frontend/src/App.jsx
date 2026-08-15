import { Routes, Route, Navigate } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./routes/ProtectedRoute";
import AdminRoute from "./routes/AdminRoute";
import UserLayout from "./layouts/UserLayout";
import AdminLayout from "./layouts/AdminLayout";

import Splash from "./pages/Splash";
import RoleSelection from "./pages/RoleSelection";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";
import AdminLogin from "./pages/admin/AdminLogin";

import Home from "./pages/Home";
import Library from "./pages/Library";
import LibraryCategories from "./pages/LibraryCategories";
import LibraryCategoryDetail from "./pages/LibraryCategoryDetail";
import UploadDetails from "./pages/UploadDetails";
import Uploads from "./pages/Uploads";
import Search from "./pages/Search";
import Results from "./pages/Results";
import SceneViewer from "./pages/SceneViewer";
import Settings from "./pages/Settings";

import UserManagement from "./pages/admin/UserManagement";
import AdminUploadDetail from "./pages/admin/AdminUploadDetail";
import AdminDataManagement from "./pages/admin/AdminDataManagement";
import AddAdmin from "./pages/admin/AddAdmin";
import SharedDataset from "./pages/admin/SharedDataset";
import Analytics from "./pages/admin/Analytics";

// Admin My Uploads reuses Library/LibraryCategories/LibraryCategoryDetail/UploadDetails via basePath
const ADMIN_MY_UPLOADS_BASE_PATH = "/admin/my-uploads";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Splash />} />
        <Route path="/role-selection" element={<RoleSelection />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/admin/login" element={<AdminLogin />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<UserLayout />}>
            <Route path="/home" element={<Home />} />
            <Route path="/library" element={<Library />} />
            <Route path="/library/categories" element={<LibraryCategories />} />
            <Route path="/library/categories/:categorySlug" element={<LibraryCategoryDetail />} />
            <Route path="/library/upload-details/:uploadId" element={<UploadDetails />} />
            <Route path="/uploads" element={<Uploads />} />
            <Route path="/search" element={<Search />} />
            <Route path="/home/results" element={<Results />} />
            <Route path="/scene-viewer" element={<SceneViewer />} />
            <Route path="/scene-viewer/:resultId" element={<SceneViewer />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Route>

        <Route element={<AdminRoute />}>
          <Route element={<AdminLayout />}>
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/uploads/:videoId" element={<AdminUploadDetail />} />
            <Route path="/admin/data-management" element={<AdminDataManagement />} />
            <Route path="/admin/add-admin" element={<AddAdmin />} />
            <Route path="/admin/shared-dataset" element={<SharedDataset />} />
            <Route
              path={ADMIN_MY_UPLOADS_BASE_PATH}
              element={<Library basePath={ADMIN_MY_UPLOADS_BASE_PATH} hideSharedScope />}
            />
            <Route
              path={`${ADMIN_MY_UPLOADS_BASE_PATH}/categories`}
              element={<LibraryCategories basePath={ADMIN_MY_UPLOADS_BASE_PATH} />}
            />
            <Route
              path={`${ADMIN_MY_UPLOADS_BASE_PATH}/categories/:categorySlug`}
              element={<LibraryCategoryDetail basePath={ADMIN_MY_UPLOADS_BASE_PATH} />}
            />
            <Route
              path={`${ADMIN_MY_UPLOADS_BASE_PATH}/upload-details/:uploadId`}
              element={<UploadDetails basePath={ADMIN_MY_UPLOADS_BASE_PATH} />}
            />
            <Route path="/admin/analytics" element={<Analytics />} />
            <Route path="/admin/settings" element={<Settings />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/role-selection" replace />} />
      </Routes>
    </AuthProvider>
  );
}
