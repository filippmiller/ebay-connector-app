import { useNavigate, useLocation } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BUILD_NUMBER, BUILD_TIMESTAMP, BUILD_BRANCH, BUILD_COMMIT } from '@/config/build';
import { useAuth } from '@/contexts/AuthContext';

interface HeaderTab {
  name: string;
  path: string;
  icon?: string;
  adminOnly?: boolean;
}

const TABS: HeaderTab[] = [
  { name: 'ORDERS', path: '/orders' },
  { name: 'TRANSACTIONS', path: '/transactions' },
  { name: 'BUYING', path: '/buying' },
  { name: 'SKU', path: '/sku' },
  { name: 'LISTING', path: '/listing' },
  { name: 'INVENTORY', path: '/inventory' },
  { name: 'SHIPPING', path: '/shipping' },
  { name: 'RETURNS', path: '/returns' },
  { name: 'CASES/DISPUTES', path: '/cases' },
  { name: 'MESSAGES', path: '/messages' },
  { name: 'OFFERS', path: '/offers' },
  { name: 'ADMIN', path: '/admin', adminOnly: true }
];

export default function FixedHeader() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const visibleTabs = TABS.filter(tab => !tab.adminOnly || isAdmin);

  const formatBuildTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${month}/${day}/${year} ${hours}:${minutes}`;
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="flex items-center justify-between px-3 py-2">
        <div className="flex items-center gap-1">
          {visibleTabs.map((tab) => {
            const isActive = location.pathname === tab.path;
            return (
              <button
                key={tab.path}
                onClick={() => navigate(tab.path)}
                className={`px-4 py-2 text-sm font-semibold tracking-wide transition-colors rounded-t-md rounded-b-md border-b-2 ${
                  isActive
                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                    : 'text-gray-700 border-transparent hover:bg-blue-50 hover:text-blue-700'
                }`}
              >
                {tab.name}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-gray-500">Build #{BUILD_NUMBER} • {BUILD_BRANCH}@{BUILD_COMMIT} • {formatBuildTime(BUILD_TIMESTAMP)}</span>
          <span className="text-xs text-gray-600">{user?.email}</span>
          <Button
            onClick={handleLogout}
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
          >
            <LogOut className="h-3 w-3 mr-1" />
            Logout
          </Button>
        </div>
      </div>
    </header>
  );
}
