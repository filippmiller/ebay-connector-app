import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Alert, AlertDescription } from '../components/ui/alert';
import { LogOut, ArrowLeft, Search, Download, Filter } from 'lucide-react';
import { apiClient } from '../api/client';

export const OrdersViewPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  
  const [filters, setFilters] = useState({
    buyer_username: '',
    order_status: '',
    start_date: '',
    end_date: ''
  });

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const fetchOrders = async () => {
    setError('');
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.buyer_username) params.append('buyer_username', filters.buyer_username);
      if (filters.order_status) params.append('order_status', filters.order_status);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
      params.append('limit', '100');
      
      const url = filters.buyer_username || filters.order_status || filters.start_date || filters.end_date
        ? `/ebay/orders/filter?${params}`
        : '/ebay/orders?limit=100';
      
      const data = await apiClient.get(url) as any;
      setOrders(data.orders || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch orders');
    } finally {
      setLoading(false);
    }
  };

  const exportData = async () => {
    try {
      const data = await apiClient.get('/ebay/export/all');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ebay-export-${new Date().toISOString()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export data');
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/dashboard')}
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Dashboard
              </Button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Orders</h1>
                <p className="text-sm text-gray-600">{total} total orders in database</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Button variant="outline" size="sm" onClick={exportData}>
                <Download className="w-4 h-4 mr-2" />
                Export All Data
              </Button>
              <div className="text-sm text-gray-600">
                {user?.email}
              </div>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Filter className="w-5 h-5" />
              Filter Orders
            </CardTitle>
            <CardDescription>
              Search and filter your eBay orders
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium mb-2 block">Buyer Username</label>
                <Input
                  placeholder="Search buyer..."
                  value={filters.buyer_username}
                  onChange={(e) => setFilters({...filters, buyer_username: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Payment Status</label>
                <Input
                  placeholder="e.g., PAID"
                  value={filters.order_status}
                  onChange={(e) => setFilters({...filters, order_status: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Start Date</label>
                <Input
                  type="date"
                  value={filters.start_date}
                  onChange={(e) => setFilters({...filters, start_date: e.target.value})}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">End Date</label>
                <Input
                  type="date"
                  value={filters.end_date}
                  onChange={(e) => setFilters({...filters, end_date: e.target.value})}
                />
              </div>
            </div>
            <div className="mt-4 flex gap-2">
              <Button onClick={fetchOrders} disabled={loading}>
                <Search className="w-4 h-4 mr-2" />
                {loading ? 'Searching...' : 'Search'}
              </Button>
              <Button 
                variant="outline" 
                onClick={() => {
                  setFilters({buyer_username: '', order_status: '', start_date: '', end_date: ''});
                  setTimeout(fetchOrders, 0);
                }}
              >
                Clear Filters
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Orders ({orders.length} shown)</CardTitle>
            <CardDescription>
              Showing {orders.length} of {total} total orders
            </CardDescription>
          </CardHeader>
          <CardContent>
            {orders.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                No orders found. Try adjusting your filters or sync orders from eBay.
              </div>
            ) : (
              <div className="space-y-4">
                {orders.map((order) => {
                  const orderData = order.order_data;
                  return (
                    <Card key={order.order_id} className="border-l-4 border-l-blue-500">
                      <CardContent className="pt-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <p className="text-sm font-medium text-gray-500">Order ID</p>
                            <p className="text-lg font-semibold">{order.order_id}</p>
                            <p className="text-sm text-gray-600 mt-1">
                              {new Date(order.creation_date).toLocaleDateString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-500">Buyer</p>
                            <p className="text-base">{order.buyer_username || 'N/A'}</p>
                            <p className="text-sm text-gray-600">{order.buyer_email || ''}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-500">Total Amount</p>
                            <p className="text-lg font-semibold">
                              {order.total_currency} {order.total_amount || '0.00'}
                            </p>
                            <div className="flex gap-2 mt-1">
                              <span className="text-xs px-2 py-1 rounded bg-green-100 text-green-800">
                                {order.order_payment_status || 'UNKNOWN'}
                              </span>
                              <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-800">
                                {order.order_fulfillment_status || 'UNKNOWN'}
                              </span>
                            </div>
                          </div>
                        </div>
                        
                        {orderData && orderData.lineItems && Array.isArray(orderData.lineItems) && orderData.lineItems.length > 0 && (
                          <div className="mt-4 pt-4 border-t">
                            <p className="text-sm font-medium text-gray-500 mb-2">Items</p>
                            <div className="space-y-2">
                              {orderData.lineItems.map((item: any, idx: number) => (
                                <div key={idx} className="text-sm">
                                  <span className="font-medium">{item.title}</span>
                                  <span className="text-gray-600 ml-2">
                                    Qty: {item.quantity} × {item.lineItemCost?.currency} {item.lineItemCost?.value}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};
