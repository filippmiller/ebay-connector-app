import { useState, useEffect } from 'react';
import { getOrderStats } from '../api/orders';
import { DataGridPage } from '@/components/DataGridPage';
import FixedHeader from '@/components/FixedHeader';
import { Search, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';

interface OrderStats {
  total_orders: number;
  total_revenue: number;
  status_breakdown: Record<string, number>;
}

export const OrdersPage = () => {
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const data = await getOrderStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'PAID':
        return 'bg-yellow-100 text-yellow-800';
      case 'SHIPPED':
        return 'bg-blue-100 text-blue-800';
      case 'COMPLETED':
        return 'bg-green-100 text-green-800';
      case 'CANCELLED':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <FixedHeader />
      {/* Main content area under fixed header: full width, grid fills all available space */}
      <div className="pt-16 flex-1 px-4 py-6 overflow-hidden">
        <div className="w-full h-full flex flex-col">
          <h1 className="text-2xl font-bold mb-4">Orders</h1>

          {stats && (
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-blue-50 p-4 rounded-lg">
                <div className="text-sm text-gray-600">Total Orders</div>
                <div className="text-2xl font-bold">{stats.total_orders || 0}</div>
              </div>
              <div className="bg-green-50 p-4 rounded-lg">
                <div className="text-sm text-gray-600">Total Revenue</div>
                <div className="text-2xl font-bold">{formatCurrency(stats.total_revenue || 0)}</div>
              </div>
              <div className="bg-purple-50 p-4 rounded-lg">
                <div className="text-sm text-gray-600">Status Breakdown</div>
                <div className="flex gap-2 mt-2 flex-wrap">
                  {stats.status_breakdown &&
                    Object.entries(stats.status_breakdown).map(([status, count]) => (
                      <Badge key={status} className={getStatusColor(status)}>
                        {status}: {count}
                      </Badge>
                    ))}
                </div>
              </div>
            </div>
          )}

          <div className="flex gap-4 mt-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Search by order ID, buyer name, or email..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <select
              className="px-4 py-2 border rounded-md"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="">All Statuses</option>
              <option value="PAID">Paid</option>
              <option value="SHIPPED">Shipped</option>
              <option value="COMPLETED">Completed</option>
              <option value="CANCELLED">Cancelled</option>
            </select>

            <Button variant="outline">
              <Download className="h-4 w-4 mr-2" />
              Export
            </Button>
          </div>

          <div className="mt-6 flex-1">
            <DataGridPage gridKey="orders" title="Orders" />
          </div>
        </div>
      </div>
    </div>
  );
};
