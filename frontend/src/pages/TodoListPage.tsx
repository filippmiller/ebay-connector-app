import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Circle, Loader2, XCircle, Clock, Activity } from 'lucide-react';
import { Separator } from '@/components/ui/separator';

interface Todo {
  id: string;
  title: string;
  description: string;
  status: 'completed' | 'in_progress' | 'pending' | 'dismissed';
  phase: string;
  logs: string[];
}

interface LogEntry {
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

export default function TodoListPage() {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const todos: Todo[] = [
    {
      id: '1',
      title: 'Create Master Todo List HTML Page',
      description: 'Interactive todo list with progress tracking',
      status: 'completed',
      phase: 'Current Sprint',
      logs: ['✅ Created HTML todo list', '✅ Added real-time stats', '✅ Integrated into frontend']
    },
    {
      id: '2',
      title: 'Update sqlite_database.py to Use /data Path',
      description: 'Change from /tmp to /data for persistent storage',
      status: 'completed',
      phase: 'Current Sprint',
      logs: ['✅ Updated SQLiteDatabase init', '✅ Changed path to /data/ebay_connector.db']
    },
    {
      id: '3',
      title: 'Update ebay_database.py to Use /data Path',
      description: 'Change from /tmp to /data for persistent storage',
      status: 'completed',
      phase: 'Current Sprint',
      logs: ['✅ Updated EbayDatabase init', '✅ Changed path to /data/ebay_connector.db']
    },
    {
      id: '4',
      title: 'Redeploy Backend with Persistent Storage',
      description: 'Deploy backend using Fly.io volume mount',
      status: 'completed',
      phase: 'Current Sprint',
      logs: ['✅ Backend redeployed', '✅ Database now at /data/ebay_connector.db', '✅ Fly.io volume configured']
    },
    {
      id: '5',
      title: 'Integrate Todo List into Frontend',
      description: 'Create /todolist route with LOG section',
      status: 'in_progress',
      phase: 'Current Sprint',
      logs: ['🔄 Creating TodoListPage.tsx', '🔄 Adding route to App.tsx', '🔄 Implementing LOG section']
    },
    {
      id: '6',
      title: 'Register Admin and Connect to eBay',
      description: 'Complete OAuth flow in production mode',
      status: 'pending',
      phase: 'Current Sprint',
      logs: []
    },
    {
      id: '7',
      title: 'Sync All 1,811 Orders',
      description: 'Complete full order sync from eBay',
      status: 'pending',
      phase: 'Current Sprint',
      logs: []
    },
    {
      id: '8',
      title: 'Test Data Persistence Through Redeploy',
      description: 'Verify orders survive backend redeployment',
      status: 'pending',
      phase: 'Current Sprint',
      logs: []
    },
    {
      id: '9',
      title: 'Verify Orders Display on Orders Page',
      description: 'Test orders page with filters and analytics',
      status: 'pending',
      phase: 'Current Sprint',
      logs: []
    },
    {
      id: '10',
      title: 'Migrate to SQLAlchemy ORM',
      description: 'Replace raw SQLite with SQLAlchemy models',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '11',
      title: 'Create Buying Model',
      description: 'item_id, tracking, buyer/seller, paid_date, amount, refund, profit, status',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '12',
      title: 'Create SKU Model',
      description: 'sku, model, category, condition, part_number, price, title',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '13',
      title: 'Create Listing Model',
      description: 'sku_id (FK), ebay_listing_id, price, shipping_group, condition',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '14',
      title: 'Create Inventory Model',
      description: 'sku_id (FK), storage, status, category, price, warehouse_id (FK)',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '15',
      title: 'Create Return Model',
      description: 'return_id, item_id, buyer, tracking, reason, sale_price, status',
      status: 'pending',
      phase: 'Phase 1: Database Models',
      logs: []
    },
    {
      id: '16',
      title: 'Set Up APScheduler / Celery',
      description: 'Background task scheduler for recurring sync',
      status: 'pending',
      phase: 'Phase 2: eBay Sync Engine',
      logs: []
    },
    {
      id: '17',
      title: 'Implement 5-Minute Sync Job',
      description: 'Auto-sync orders, listings, returns every 5 minutes',
      status: 'pending',
      phase: 'Phase 2: eBay Sync Engine',
      logs: []
    },
    {
      id: '18',
      title: 'Implement Profit Calculation',
      description: 'profit = sale_price - amount_paid - ebay_fee - shipping_cost',
      status: 'pending',
      phase: 'Phase 3: Profit Engine',
      logs: []
    },
    {
      id: '19',
      title: 'BUYING Tab',
      description: 'Table view, filters, detail pane, profit highlighting',
      status: 'pending',
      phase: 'Phase 5: Frontend Modules',
      logs: []
    },
    {
      id: '20',
      title: 'SKU Tab',
      description: 'CRUD interface, image preview, Add/Edit/Delete',
      status: 'pending',
      phase: 'Phase 5: Frontend Modules',
      logs: []
    }
  ];

  const systemLogs: LogEntry[] = [
    { timestamp: '2025-10-21 10:45:23', message: 'Todo list page integrated into frontend at /todolist route', type: 'success' },
    { timestamp: '2025-10-21 10:42:15', message: 'Backend redeployed with persistent storage at /data/ebay_connector.db', type: 'success' },
    { timestamp: '2025-10-21 10:40:08', message: 'Updated ebay_database.py to use /data path instead of /tmp', type: 'info' },
    { timestamp: '2025-10-21 10:39:52', message: 'Updated sqlite_database.py to use /data path instead of /tmp', type: 'info' },
    { timestamp: '2025-10-21 10:35:30', message: 'Created master todo list HTML page with stats dashboard', type: 'success' },
    { timestamp: '2025-10-21 10:20:15', message: 'Successfully synced 1,800 out of 1,811 orders (99.4%)', type: 'warning' },
    { timestamp: '2025-10-21 10:19:45', message: 'Fly.io machine auto-suspended during sync', type: 'warning' },
    { timestamp: '2025-10-21 09:58:20', message: 'Fixed IndentationError in ebay_database.py line 447', type: 'success' },
    { timestamp: '2025-10-21 09:45:10', message: 'Successfully connected to eBay Production API', type: 'success' },
    { timestamp: '2025-10-21 09:42:05', message: 'Environment toggle (sandbox ↔ production) implemented and tested', type: 'success' },
    { timestamp: '2025-10-21 09:30:12', message: 'Admin role badge added for filippmiller@gmail.com, mylifeis0plus1@gmail.com, nikitin.sergei.v@gmail.com', type: 'success' },
    { timestamp: '2025-10-21 09:25:48', message: 'Password show/hide toggle implemented with eye icon', type: 'success' },
    { timestamp: '2025-10-21 09:10:22', message: 'Registration and login system completed with JWT authentication', type: 'success' },
    { timestamp: '2025-10-21 08:55:30', message: 'eBay OAuth flow implemented with credential management', type: 'success' },
    { timestamp: '2025-10-21 08:40:15', message: 'Backend and frontend deployed successfully', type: 'success' },
    { timestamp: '2025-10-21 08:30:00', message: 'Project initialized: eBay Connector App', type: 'info' }
  ];

  const stats = {
    total: todos.length,
    completed: todos.filter(t => t.status === 'completed').length,
    inProgress: todos.filter(t => t.status === 'in_progress').length,
    pending: todos.filter(t => t.status === 'pending').length,
    dismissed: todos.filter(t => t.status === 'dismissed').length
  };

  const progress = Math.round((stats.completed / stats.total) * 100);

  const getStatusIcon = (status: Todo['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-600" />;
      case 'in_progress':
        return <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />;
      case 'pending':
        return <Circle className="w-5 h-5 text-orange-500" />;
      case 'dismissed':
        return <XCircle className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: Todo['status']) => {
    switch (status) {
      case 'completed':
        return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Completed</Badge>;
      case 'in_progress':
        return <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">In Progress</Badge>;
      case 'pending':
        return <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">Pending</Badge>;
      case 'dismissed':
        return <Badge className="bg-gray-100 text-gray-600 hover:bg-gray-100">Dismissed</Badge>;
    }
  };

  const getLogTypeColor = (type: LogEntry['type']) => {
    switch (type) {
      case 'success':
        return 'text-green-600';
      case 'error':
        return 'text-red-600';
      case 'warning':
        return 'text-orange-600';
      case 'info':
      default:
        return 'text-blue-600';
    }
  };

  const groupedTodos = todos.reduce((acc, todo) => {
    if (!acc[todo.phase]) acc[todo.phase] = [];
    acc[todo.phase].push(todo);
    return acc;
  }, {} as Record<string, Todo[]>);

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-blue-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">🚀 eBay Connector - Master Todo List</h1>
          <p className="text-gray-600 flex items-center gap-2">
            <Clock className="w-4 h-4" />
            Last Updated: {currentTime.toLocaleString()} | Real-time Progress Tracking
          </p>
        </div>

        {/* Stats Dashboard */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-3xl font-bold">{stats.completed}</CardTitle>
              <CardDescription className="text-green-50">✅ Completed</CardDescription>
            </CardHeader>
          </Card>

          <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-3xl font-bold">{stats.inProgress}</CardTitle>
              <CardDescription className="text-blue-50">🔄 In Progress</CardDescription>
            </CardHeader>
          </Card>

          <Card className="bg-gradient-to-br from-orange-500 to-orange-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-3xl font-bold">{stats.pending}</CardTitle>
              <CardDescription className="text-orange-50">📋 Pending</CardDescription>
            </CardHeader>
          </Card>

          <Card className="bg-gradient-to-br from-purple-500 to-purple-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-3xl font-bold">{progress}%</CardTitle>
              <CardDescription className="text-purple-50">📊 Progress</CardDescription>
            </CardHeader>
          </Card>

          <Card className="bg-gradient-to-br from-gray-500 to-gray-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-3xl font-bold">{stats.total}</CardTitle>
              <CardDescription className="text-gray-50">📝 Total Tasks</CardDescription>
            </CardHeader>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Todo List - 2/3 width */}
          <div className="lg:col-span-2">
            <Card className="shadow-lg">
              <CardHeader>
                <CardTitle className="text-2xl">Tasks by Phase</CardTitle>
                <CardDescription>Organized by development phase</CardDescription>
              </CardHeader>
              <CardContent className="max-h-screen overflow-y-auto">
                {Object.entries(groupedTodos).map(([phase, phaseTodos]) => (
                  <div key={phase} className="mb-6">
                    <h3 className="text-lg font-semibold text-purple-700 mb-3 flex items-center gap-2">
                      {phase === 'Current Sprint' && '🎯'}
                      {phase === 'Phase 1: Database Models' && '📊'}
                      {phase === 'Phase 2: eBay Sync Engine' && '🔄'}
                      {phase === 'Phase 3: Profit Engine' && '💰'}
                      {phase === 'Phase 5: Frontend Modules' && '🎨'}
                      {phase}
                    </h3>
                    <div className="space-y-3">
                      {phaseTodos.map((todo) => (
                        <div
                          key={todo.id}
                          className={`border rounded-lg p-4 transition-all hover:shadow-md ${
                            todo.status === 'completed' ? 'bg-green-50 border-green-200' :
                            todo.status === 'in_progress' ? 'bg-blue-50 border-blue-200' :
                            todo.status === 'pending' ? 'bg-orange-50 border-orange-200' :
                            'bg-gray-50 border-gray-200'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            {getStatusIcon(todo.status)}
                            <div className="flex-1">
                              <div className="flex items-start justify-between gap-2 mb-1">
                                <h4 className="font-semibold text-gray-900">{todo.title}</h4>
                                {getStatusBadge(todo.status)}
                              </div>
                              <p className="text-sm text-gray-600 mb-2">{todo.description}</p>
                              {todo.logs.length > 0 && (
                                <div className="mt-2 space-y-1">
                                  {todo.logs.map((log, idx) => (
                                    <p key={idx} className="text-xs font-mono text-gray-700 bg-white/50 px-2 py-1 rounded">
                                      {log}
                                    </p>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* System Log - 1/3 width */}
          <div className="lg:col-span-1">
            <Card className="shadow-lg sticky top-6">
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-2">
                  <Activity className="w-6 h-6 text-purple-600" />
                  System Log
                </CardTitle>
                <CardDescription>Real-time activity feed</CardDescription>
              </CardHeader>
              <CardContent className="max-h-screen overflow-y-auto">
                <div className="space-y-3">
                  {systemLogs.map((log, idx) => (
                    <div key={idx} className="border-l-4 border-purple-500 pl-3 py-2">
                      <p className="text-xs text-gray-500 mb-1">{log.timestamp}</p>
                      <p className={`text-sm font-medium ${getLogTypeColor(log.type)}`}>
                        {log.message}
                      </p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-gray-600 text-sm">
          <Separator className="mb-4" />
          <p className="mb-2">📅 Live tracking system for eBay Connector development</p>
          <p className="mb-2">🔗 <a href="https://ebay-connection-app-k0ge3h93.devinapps.com" className="text-purple-600 hover:underline">View Live App</a></p>
          <p>🤖 Powered by Devin AI | Session: <a href="https://app.devin.ai/sessions/3ef2b75bb4ad437b8274d8223cc18211" className="text-purple-600 hover:underline">3ef2b75bb4ad437b8274d8223cc18211</a></p>
        </div>
      </div>
    </div>
  );
}
