import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { LoginPage } from './pages/LoginPage';
// import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { EbayCallbackPage } from './pages/EbayCallbackPage';
import { EbayConnectionPage } from './pages/EbayConnectionPage';
// import { PasswordResetPage } from './pages/PasswordResetPage';
import { MessagesPage } from './pages/MessagesPage';
import { OrdersPage } from './pages/OrdersPage';
import { EbayTestPage } from './pages/EbayTestPage';
import { OrdersViewPage } from './pages/OrdersViewPage';
import { AnalyticsDashboardPage } from './pages/AnalyticsDashboardPage';
import TodoListPage from './pages/TodoListPage';
import BuyingPage from './pages/BuyingPage';
import InventoryPageV3 from './pages/InventoryPageV3';
import InventoryPageV2 from './pages/InventoryPageV2';
import TransactionsPage from './pages/TransactionsPage';
import FinancialsPage from './pages/FinancialsPage';
import AdminJobsPage from './pages/AdminJobsPage';
import OffersPageV2 from './pages/OffersPageV2';
import AdminDbExplorerPage from './pages/AdminDbExplorerPage';
import EbayNotificationsPage from './pages/EbayNotificationsPage';
import AdminWorkersPage from './pages/AdminWorkersPage';
import SKUPage from './pages/SKUPage';
import ListingPage from './pages/ListingPage';
import ShippingPage from './pages/ShippingPage';
import BulkShippingPage from './pages/BulkShippingPage';
import ReturnsPage from './pages/ReturnsPage';
import CasesPage from './pages/CasesPage';
import AdminPage from './pages/AdminPage';
import AdminTestListingPage from './pages/AdminTestListingPage';
import AdminBinListingPage from './pages/AdminBinListingPage';
import AdminDataMigrationPage from './pages/AdminDataMigrationPage';
import AdminTestComputerAnalyticsGraphPage from './pages/AdminTestComputerAnalyticsGraphPage';
import MyTimesheetPage from './pages/MyTimesheetPage';
import AdminTimesheetsPage from './pages/AdminTimesheetsPage';
import TasksPage from './pages/TasksPage';
import Accounting2Page from './pages/Accounting2Page';
import AdminUITweakPage from './pages/AdminUITweakPage';
import SecurityCenterPage from './pages/SecurityCenterPage';
import AdminUsersPage from './pages/AdminUsersPage';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import SniperPage from './pages/SniperPage';
import AdminAiGridPage from './pages/AdminAiGridPage';
import EbayBrowserPage from './pages/EbayBrowserPage';
import AdminAiRulesPage from './pages/AdminAiRulesPage';
import AdminMonitoringPage from './pages/AdminMonitoringPage';
import AdminModelProfitPage from './pages/AdminModelProfitPage';
import AdminActionsPage from './pages/AdminActionsPage';
import AdminAiCenterPage from './pages/AdminAiCenterPage';
import AdminIntegrationsPage from './pages/AdminIntegrationsPage';
import AdminAiEmailTrainingPage from './pages/AdminAiEmailTrainingPage';
import AdminAiSettingsPage from './pages/AdminAiSettingsPage';
import AdminAiTrainingPage from './pages/AdminAiTrainingPage';
import CameraVisionPage from './pages/CameraVisionPage';
import VisionBrainPage from './pages/VisionBrainPage';
import AdminTestComputerAnalyticsPage from './pages/AdminTestComputerAnalyticsPage';
import './App.css';
import HeroPage from './pages/HeroPage';
import './App.css';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // If backend marks that user must change password, force them onto
  // the change-password screen before accessing the rest of the app.
  if (user.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  return <>{children}</>;
};

const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg">Loading...</div>
      </div>
    );
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<HeroPage />} />
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
          {/* Public self-registration and self-service password reset are disabled.
              All user accounts and password resets are managed by administrators
              via the Admin → Users page. */}
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <ChangePasswordPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ebay/callback"
            element={
              <ProtectedRoute>
                <EbayCallbackPage />
              </ProtectedRoute>
            }
          />
          <Route path="/messages" element={<ProtectedRoute><MessagesPage /></ProtectedRoute>} />
          <Route path="/offers" element={<ProtectedRoute><OffersPageV2 /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
          <Route path="/admin/integrations" element={<ProtectedRoute><AdminIntegrationsPage /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsersPage /></ProtectedRoute>} />
          <Route path="/admin/ui-tweak" element={<ProtectedRoute><AdminUITweakPage /></ProtectedRoute>} />
          <Route path="/admin/security" element={<ProtectedRoute><SecurityCenterPage /></ProtectedRoute>} />
          <Route path="/admin/ai-center" element={<ProtectedRoute><AdminAiCenterPage /></ProtectedRoute>} />
          <Route path="/admin/ai-grid" element={<ProtectedRoute><AdminAiGridPage /></ProtectedRoute>} />
          <Route path="/admin/ai-rules" element={<ProtectedRoute><AdminAiRulesPage /></ProtectedRoute>} />
          <Route path="/admin/ai-email-training" element={<ProtectedRoute><AdminAiEmailTrainingPage /></ProtectedRoute>} />
          <Route path="/admin/ai-settings" element={<ProtectedRoute><AdminAiSettingsPage /></ProtectedRoute>} />
          <Route path="/admin/ai-training" element={<ProtectedRoute><AdminAiTrainingPage /></ProtectedRoute>} />
          <Route path="/admin/monitor" element={<ProtectedRoute><AdminMonitoringPage /></ProtectedRoute>} />
          <Route path="/admin/model-profit" element={<ProtectedRoute><AdminModelProfitPage /></ProtectedRoute>} />
          <Route path="/admin/actions" element={<ProtectedRoute><AdminActionsPage /></ProtectedRoute>} />
          <Route path="/admin/ebay-connection" element={<ProtectedRoute><EbayConnectionPage /></ProtectedRoute>} />
          <Route path="/admin/db-explorer" element={<ProtectedRoute><AdminDbExplorerPage /></ProtectedRoute>} />
          <Route path="/admin/data-migration" element={<ProtectedRoute><AdminDataMigrationPage /></ProtectedRoute>} />
          <Route path="/admin/notifications" element={<ProtectedRoute><EbayNotificationsPage /></ProtectedRoute>} />
          <Route path="/admin/workers" element={<ProtectedRoute><AdminWorkersPage /></ProtectedRoute>} />
          <Route path="/admin/bin-listing" element={<ProtectedRoute><AdminBinListingPage /></ProtectedRoute>} />
          <Route path="/admin/test-listing" element={<ProtectedRoute><AdminTestListingPage /></ProtectedRoute>} />
          <Route path="/admin/test-computer-analytics" element={<ProtectedRoute><AdminTestComputerAnalyticsPage /></ProtectedRoute>} />
          <Route path="/admin/test-computer-analytics-graph" element={<ProtectedRoute><AdminTestComputerAnalyticsGraphPage /></ProtectedRoute>} />
          <Route
            path="/orders"
            element={
              <ProtectedRoute>
                <OrdersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/offers"
            element={
              <ProtectedRoute>
                <OffersPageV2 />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ebay/test"
            element={
              <ProtectedRoute>
                <EbayTestPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/orders-view"
            element={
              <ProtectedRoute>
                <OrdersViewPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute>
                <AnalyticsDashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/todolist"
            element={<TodoListPage />}
          />
          <Route
            path="/timesheets/my"
            element={
              <ProtectedRoute>
                <MyTimesheetPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/timesheets/admin"
            element={
              <ProtectedRoute>
                <AdminTimesheetsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/buying"
            element={
              <ProtectedRoute>
                <BuyingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/inventory"
            element={
              <ProtectedRoute>
                <InventoryPageV3 />
              </ProtectedRoute>
            }
          />
          <Route
            path="/inventory-v2"
            element={
              <ProtectedRoute>
                <InventoryPageV2 />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <ProtectedRoute>
                <TasksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/sku"
            element={
              <ProtectedRoute>
                <SKUPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/listing"
            element={
              <ProtectedRoute>
                <ListingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/shipping"
            element={
              <ProtectedRoute>
                <ShippingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/shipping/bulk"
            element={
              <ProtectedRoute>
                <BulkShippingPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/returns"
            element={
              <ProtectedRoute>
                <ReturnsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cases"
            element={
              <ProtectedRoute>
                <CasesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/transactions"
            element={
              <ProtectedRoute>
                <TransactionsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/financials"
            element={
              <ProtectedRoute>
                <FinancialsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/sniper"
            element={
              <ProtectedRoute>
                <SniperPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ebay-browser"
            element={
              <ProtectedRoute>
                <EbayBrowserPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/jobs"
            element={
              <ProtectedRoute>
                <AdminJobsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/accounting2/*"
            element={
              <ProtectedRoute>
                <Accounting2Page />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/camera-vision"
            element={
              <ProtectedRoute>
                <CameraVisionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/vision-brain"
            element={
              <ProtectedRoute>
                <VisionBrainPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
