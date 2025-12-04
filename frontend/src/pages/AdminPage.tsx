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

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/workers')}>
            <h2 className="text-lg font-semibold">eBay Workers</h2>
            <p className="text-sm text-gray-600 mt-1">Configure and run background eBay sync jobs</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/db-explorer')}>
            <h2 className="text-lg font-semibold">DB Explorer</h2>
            <p className="text-sm text-gray-600 mt-1">Browse Supabase tables and recent rows (read-only)</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/data-migration')}>
            <h2 className="text-lg font-semibold">Data Migration</h2>
            <p className="text-sm text-gray-600 mt-1">Explore external MSSQL DB and prepare migration</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/notifications')}>
            <h2 className="text-lg font-semibold">Notifications</h2>
            <p className="text-sm text-gray-600 mt-1">View eBay notification inbox & webhook events</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/security')}>
            <h2 className="text-lg font-semibold">Security Center</h2>
            <p className="text-sm text-gray-600 mt-1">Login protection, security events, and policies</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-settings')}>
            <h2 className="text-lg font-semibold">AI Settings</h2>
            <p className="text-sm text-gray-600 mt-1">OpenAI ключ и модель по умолчанию</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ui-tweak')}>
            <h2 className="text-lg font-semibold">UI Tweak</h2>
            <p className="text-sm text-gray-600 mt-1">Adjust navigation, text size, and grid density</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-center')}>
            <h2 className="text-lg font-semibold">AI & Automation Center</h2>
            <p className="text-sm text-gray-600 mt-1">Обзор всех AI-правил, воркеров и кандидатов</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-grid')}>
            <h2 className="text-lg font-semibold">AI Grid Playground</h2>
            <p className="text-sm text-gray-600 mt-1">Test AI-запросы и живой грид в админке</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-rules')}>
            <h2 className="text-lg font-semibold">AI Rules</h2>
            <p className="text-sm text-gray-600 mt-1">Определить правила "хорошей покупки" и окупаемости</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/ai-email-training')}>
            <h2 className="text-lg font-semibold">AI Email Training</h2>
            <p className="text-sm text-gray-600 mt-1">Просмотр и модерация email-пар для обучения AI</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/monitor')}>
            <h2 className="text-lg font-semibold">Monitoring Candidates</h2>
            <p className="text-sm text-gray-600 mt-1">Кандидаты на покупку из eBay мониторинга по моделям</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/model-profit')}>
            <h2 className="text-lg font-semibold">Model Profitability</h2>
            <p className="text-sm text-gray-600 mt-1">Просмотр профилей прибыльности моделей и max_buy_price</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/actions')}>
            <h2 className="text-lg font-semibold">Auto-Offer / Auto-Buy Actions</h2>
            <p className="text-sm text-gray-600 mt-1">Планировщик действий (draft / ready / executed / failed)</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/timesheets/admin')}>
            <h2 className="text-lg font-semibold">Timesheets</h2>
            <p className="text-sm text-gray-600 mt-1">Admin timesheet overview & corrections</p>
          </Card>
          
          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/admin/integrations')}>
            <h2 className="text-lg font-semibold">Integrations</h2>
            <p className="text-sm text-gray-600 mt-1">Подключение Gmail и других внешних провайдеров</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer" onClick={() => navigate('/todolist')}>
            <h2 className="text-lg font-semibold">Todo List</h2>
            <p className="text-sm text-gray-600 mt-1">View development progress</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer border-2 border-purple-200 bg-purple-50" onClick={() => navigate('/admin/camera-vision')}>
            <h2 className="text-lg font-semibold text-purple-700">📷 Camera Vision</h2>
            <p className="text-sm text-gray-600 mt-1">DJI Osmo Pocket 3 + YOLO + OCR pipeline</p>
          </Card>

          <Card className="p-4 hover:shadow-lg cursor-pointer border-2 border-cyan-200 bg-cyan-50" onClick={() => navigate('/admin/vision-brain')}>
            <h2 className="text-lg font-semibold text-cyan-700">🧠 Vision Brain</h2>
            <p className="text-sm text-gray-600 mt-1">AI-powered vision analysis with OpenAI</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
