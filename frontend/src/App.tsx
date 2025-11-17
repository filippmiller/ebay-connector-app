import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { DashboardPage } from './pages/DashboardPage';
import { EbayCallbackPage } from './pages/EbayCallbackPage';
import { EbayConnectionPage } from './pages/EbayConnectionPage';
import { PasswordResetPage } from './pages/PasswordResetPage';
import { MessagesPage } from './pages/MessagesPage';
import { OrdersPage } from './pages/OrdersPage';
import { EbayTestPage } from './pages/EbayTestPage';
import { OrdersViewPage } from './pages/OrdersViewPage';
import { AnalyticsDashboardPage } from './pages/AnalyticsDashboardPage';
import TodoListPage from './pages/TodoListPage';
import BuyingPage from './pages/BuyingPage';
import InventoryPageV3 from './pages/InventoryPageV3';
import TransactionsPage from './pages/TransactionsPage';
import FinancialsPage from './pages/FinancialsPage';
import AdminJobsPage from './pages/AdminJobsPage';
import OffersPageV2 from './pages/OffersPageV2';
import AdminDbExplorerPage from './pages/AdminDbExplorerPage';
import SKUPage from './pages/SKUPage';
import ListingPage from './pages/ListingPage';
import ShippingPage from './pages/ShippingPage';
import ReturnsPage from './pages/ReturnsPage';
import CasesPage from './pages/CasesPage';
import AdminPage from './pages/AdminPage';
import AdminDataMigrationPage from './pages/AdminDataMigrationPage';
import MyTimesheetPage from './pages/MyTimesheetPage';
import AdminTimesheetsPage from './pages/AdminTimesheetsPage';
import './App.css';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

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
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
          <Route
            path="/register"
            element={
              <PublicRoute>
                <RegisterPage />
              </PublicRoute>
            }
          />
          <Route
            path="/password-reset"
            element={
              <PublicRoute>
                <PasswordResetPage />
              </PublicRoute>
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
          <Route path="/admin/ebay-connection" element={<ProtectedRoute><EbayConnectionPage /></ProtectedRoute>} />
          <Route path="/admin/db-explorer" element={<ProtectedRoute><AdminDbExplorerPage /></ProtectedRoute>} />
          <Route path="/admin/data-migration" element={<ProtectedRoute><AdminDataMigrationPage /></ProtectedRoute>} />
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
            path="/admin/jobs"
            element={
              <ProtectedRoute>
                <AdminJobsPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
