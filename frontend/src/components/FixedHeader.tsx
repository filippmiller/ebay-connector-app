import { useNavigate, useLocation } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BUILD_NUMBER } from '@/config/build';

interface HeaderTab {
  name: string;
  path: string;
  icon?: string;
  adminOnly?: boolean;
}

const TABS: HeaderTab[] = [
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
  const userEmail = localStorage.getItem('user_email') || '';
  const isAdmin = ['filippmiller@gmail.com', 'mylifeis0plus1@gmail.com', 'nikitin.sergei.v@gmail.com'].includes(userEmail);

  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  const visibleTabs = TABS.filter(tab => !tab.adminOnly || isAdmin);

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
                className={`px-3 py-1.5 text-xs font-medium uppercase tracking-wide transition-colors rounded ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                {tab.name}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-gray-500">Build #{BUILD_NUMBER}</span>
          <span className="text-xs text-gray-600">{userEmail}</span>
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
