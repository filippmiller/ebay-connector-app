import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { LogOut, Clock, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { BUILD_NUMBER, BUILD_TIMESTAMP, BUILD_BRANCH, BUILD_COMMIT } from '@/config/build';
import { useAuth } from '@/contexts/AuthContext';
import TaskNotificationsBell from '@/components/TaskNotificationsBell';

interface HeaderTab {
  name: string;
  path: string;
  icon?: string;
  adminOnly?: boolean;
}

const TABS: HeaderTab[] = [
  { name: 'ORDERS', path: '/orders' },
  { name: 'TXN', path: '/transactions' },
  { name: 'FINANCES', path: '/financials' },
  { name: 'BUYING', path: '/buying' },
  { name: 'SKU', path: '/sku' },
  { name: 'LISTING', path: '/listing' },
  { name: 'INVENTORY', path: '/inventory' },
  { name: 'SHIPPING', path: '/shipping' },
  { name: 'RETURNS', path: '/returns' },
  { name: 'CASES', path: '/cases' },
  { name: 'MSG', path: '/messages' },
  { name: 'SNIPER', path: '/sniper' },
  { name: 'OFFERS', path: '/offers' },
  { name: 'TASKS', path: '/tasks' },
  { name: 'eBROWSER', path: '/ebay-browser' },
  { name: 'ACCT2', path: '/accounting2', adminOnly: true },
  { name: 'ADMIN', path: '/admin', adminOnly: true }
];

export default function FixedHeader() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleTimesheetClick = () => {
    navigate('/timesheets/my');
  };

  const visibleTabs = TABS.filter((tab) => !tab.adminOnly || isAdmin);
  const activeTab = visibleTabs.find((tab) => location.pathname === tab.path) || visibleTabs[0];

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
    <header className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
      <div className="flex items-center justify-between px-2 py-1">
        <div className="flex items-center gap-1 min-w-0 flex-1">
          {/* Mobile: hamburger trigger + current tab label */}
          <div className="flex items-center gap-2 md:hidden">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Open navigation"
              className="h-8 w-8"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </Button>
            {activeTab && (
              <span className="text-xs font-semibold tracking-wide truncate max-w-[10rem]">
                {activeTab.name}
              </span>
            )}
          </div>

          {/* Desktop: full tab row */}
          <div className="hidden md:flex items-center gap-0.5 flex-wrap">
            {visibleTabs.map((tab) => {
              const isActive = location.pathname === tab.path;
              return (
                <button
                  key={tab.path}
                  onClick={() => navigate(tab.path)}
                  className={`ui-nav-tab font-medium tracking-tight rounded border-b-2 transition-colors ${
                    isActive
                      ? 'ui-nav-tab--active border-blue-600 shadow-sm'
                      : 'ui-nav-tab--inactive border-transparent hover:bg-blue-50 hover:text-blue-700'
                  }`}
                >
                  {tab.name}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={handleTimesheetClick}
            className="rounded-full p-1 hover:bg-blue-50 text-gray-600 hover:text-blue-700"
            title="My timesheet"
          >
            <Clock className="h-3 w-3" />
          </button>
          <TaskNotificationsBell />
          <span 
            className="hidden lg:inline text-[9px] font-mono text-gray-400" 
            title={`Build #${BUILD_NUMBER} ${BUILD_BRANCH}@${BUILD_COMMIT} ${formatBuildTime(BUILD_TIMESTAMP)}`}
          >
            #{BUILD_NUMBER}
          </span>
          <span 
            className="text-[10px] text-gray-500 truncate max-w-[80px]" 
            title={user?.email}
          >
            {user?.email?.split('@')[0]}
          </span>
          <Button onClick={handleLogout} variant="ghost" size="sm" className="h-5 px-1.5 text-[10px]">
            <LogOut className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Mobile navigation sheet */}
      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetHeader className="border-b px-4 py-3">
            <SheetTitle className="text-sm font-semibold tracking-wide">Navigation</SheetTitle>
          </SheetHeader>
          <nav className="py-2">
            {visibleTabs.map((tab) => {
              const isActive = location.pathname === tab.path;
              return (
                <button
                  key={tab.path}
                  type="button"
                  onClick={() => {
                    navigate(tab.path);
                    setMobileNavOpen(false);
                  }}
                  className={`block w-full text-left px-4 py-2 text-sm ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-semibold'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {tab.name}
                </button>
              );
            })}
          </nav>
        </SheetContent>
      </Sheet>
    </header>
  );
}
