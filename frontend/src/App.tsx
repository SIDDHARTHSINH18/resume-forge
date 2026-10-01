import { Link, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { CandidateDetailPage } from "./pages/CandidateDetail";
import { CandidatesPage } from "./pages/Candidates";
import { DashboardPage } from "./pages/Dashboard";
import { ExportsPage } from "./pages/Exports";
import { ProcessingPage } from "./pages/Processing";
import { ProfileDetailPage } from "./pages/ProfileDetail";
import { ProfileFormPage } from "./pages/ProfileForm";
import { ProfilesPage } from "./pages/Profiles";
import { ResumeSourcesPage } from "./pages/ResumeSources";
import { ReviewsPage } from "./pages/Reviews";
import { SettingsPage } from "./pages/Settings";

function NotFound() {
  return (
    <div className="page">
      <div className="empty">
        <div className="empty-title">Page not found</div>
        <div className="empty-desc">The page you are looking for does not exist.</div>
        <Link className="btn btn-secondary" to="/">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/profiles" element={<ProfilesPage />} />
        <Route path="/profiles/new" element={<ProfileFormPage />} />
        <Route path="/profiles/:id" element={<ProfileDetailPage />} />
        <Route path="/profiles/:id/edit" element={<ProfileFormPage />} />
        <Route path="/candidates" element={<CandidatesPage />} />
        <Route path="/candidates/:id" element={<CandidateDetailPage />} />
        <Route path="/sources" element={<ResumeSourcesPage />} />
        <Route path="/processing" element={<ProcessingPage />} />
        <Route path="/reviews" element={<ReviewsPage />} />
        <Route path="/exports" element={<ExportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
