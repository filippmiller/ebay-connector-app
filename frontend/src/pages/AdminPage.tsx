import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { useNavigate } from 'react-router-dom';

export default function AdminPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <h1 className="text-2xl font-bold mb-4">Admin Dashboard</h1>
        
        <div className="grid grid-cols-3 gap-4">
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/jobs')}>
            <h2 className="text-lg font-semibold">Background Jobs</h2>
            <p className="text-sm text-gray-600 mt-1">Monitor sync jobs and background tasks</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/settings')}>
            <h2 className="text-lg font-semibold">Settings</h2>
            <p className="text-sm text-gray-600 mt-1">Configure eBay API and system settings</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/users')}>
            <h2 className="text-lg font-semibold">Users</h2>
            <p className="text-sm text-gray-600 mt-1">Manage user accounts and permissions</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ebay-connection')}>
            <h2 className="text-lg font-semibold">eBay Connection</h2>
            <p className="text-sm text-gray-600 mt-1">Manage eBay API connections</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/migration')}>
            <h2 className="text-lg font-semibold">Data Migration</h2>
            <p className="text-sm text-gray-600 mt-1">Run database migrations and data imports</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/todolist')}>
            <h2 className="text-lg font-semibold">Todo List</h2>
            <p className="text-sm text-gray-600 mt-1">View development progress</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
