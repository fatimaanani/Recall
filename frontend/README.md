# Frontend ReCall

React + Vite single-page application. See the repository root `README.md` for the project overview; this file covers frontend-specific setup and structure.

## Setup

```
npm install
cp .env.example .env
npm run dev
```

Runs at `http://localhost:5173`. `VITE_API_BASE_URL` in `.env` should point at the running backend (`http://localhost:8000` by default).

## Structure

- `src/main.jsx` -- React root, wraps the app in `BrowserRouter`.
- `src/App.jsx` -- the full route table (public, user, and admin routes).
- `src/context/AuthContext.jsx` -- authentication state backed by the real API (register/login/logout call `src/services/authService.js`); the JWT is kept in `localStorage`, read by `src/services/apiClient.js`.
- `src/services/` -- one thin file per backend resource area (`apiClient.js` is the shared Axios instance every other service file uses): `authService.js`, `userService.js`, `videoService.js`, `categoryService.js`, `searchService.js`, `resultService.js`, `clipService.js`, `analyticsService.js`, `adminService.js`.
- `src/hooks/` -- `useProtectedImage.js` and `useProtectedMedia.js` (fetch an image/video/audio that requires the Bearer auth token, exposing it as a local `blob:` URL, since a plain `<img>`/`<video>`/`<audio>` tag can't send an `Authorization` header itself), `useStagedUploadQueue.js` (the Upload Queue's staging/concurrency logic), `useSearchMethodForm.js`, `useDarkMode.js`.
- `src/routes/` -- `ProtectedRoute.jsx` (any logged-in user) and `AdminRoute.jsx` (admins only).
- `src/layouts/` -- `UserLayout.jsx` and `AdminLayout.jsx`, each rendering a sidebar plus `<Outlet />`.
- `src/pages/` -- one file per page: `Home.jsx`, `Library.jsx`, `LibraryCategories.jsx`, `LibraryCategoryDetail.jsx`, `Uploads.jsx`, `UploadDetails.jsx`, `Search.jsx`, `Results.jsx`, `SceneViewer.jsx`, `Settings.jsx`, `RoleSelection.jsx`, `Splash.jsx`, plus `auth/` (`Login.jsx`, `Register.jsx`, `ForgotPassword.jsx`, `ResetPassword.jsx`) and `admin/` (`AdminLogin.jsx`, `UserManagement.jsx`, `SharedDataset.jsx`, `AdminDataManagement.jsx`, `AddAdmin.jsx`, `AdminUploadDetail.jsx`, `Analytics.jsx`).
- `src/mocks/mockData.js` -- sample data still used by a small number of not-yet-real UI sections (see inline comments at each usage site).
- `src/utils/searchSession.js` -- a small sessionStorage-backed "current search session" so the latest search results and Results' own page/filter/sort state survive a Scene Viewer round trip and a same-tab refresh without becoming permanent data.
- `src/assets/` -- `mascots/`, `avatars/`, `decorations/`, `illustrations/`, `icons/`.
- `src/styles/variables.css` -- design tokens (colors, spacing, fonts). `src/styles/global.css` -- base layout and shared component classes.

## Testing

```
npm run check:logic
```

Runs `scripts/verify-frontend-logic.mjs`, a small dependency-free Node script that exercises pure client-side session logic (`src/utils/searchSession.js`) directly with Node's built-in assertions, independent of React. There is no separate frontend unit-test framework; correctness is otherwise verified through the production build (`npm run build`) and manual testing against the running backend.
