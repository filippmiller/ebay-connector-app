import { useState, useEffect } from 'react';
import { getOrders, getOrderStats } from '../api/orders';
import { Package, Search, Download } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';

interface OrderLineItem {
  id: string;
  title: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  image_url: string | null;
}

interface Order {
  id: string;
  order_id: string;
  order_status: string;
  order_date: string;
  buyer_username: string | null;
  buyer_email: string | null;
  total_amount: number;
  shipping_cost: number | null;
  tax_amount: number | null;
  tracking_number: string | null;
  shipped_date: string | null;
  line_items: OrderLineItem[];
}

interface OrderStats {
  total_orders: number;
  total_revenue: number;
  status_breakdown: Record<string, number>;
}

export const OrdersPage = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOrders();
    loadStats();
  }, [selectedStatus]);

  const loadOrders = async () => {
    try {
      setLoading(true);
      const data = await getOrders(selectedStatus, searchQuery);
      setOrders(data as Order[]);
    } catch (error) {
      console.error('Failed to load orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await getOrderStats();
      setStats(data as OrderStats);
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

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <div className="border-b px-6 py-4">
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
                {stats.status_breakdown && Object.entries(stats.status_breakdown).map(([status, count]) => (
                  <Badge key={status} className={getStatusColor(status)}>
                    {status}: {count}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search by order ID, buyer name, or email..."
              className="pl-10"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadOrders()}
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
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-center py-8 text-gray-500">Loading...</div>
        ) : orders.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Package className="h-16 w-16 mx-auto mb-4 opacity-20" />
            <p>No orders found</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order ID</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Buyer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Tracking</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.map((order) => (
                <TableRow
                  key={order.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelectedOrder(selectedOrder?.id === order.id ? null : order)}
                >
                  <TableCell className="font-medium">{order.order_id}</TableCell>
                  <TableCell>{order.order_date ? formatDate(order.order_date) : 'N/A'}</TableCell>
                  <TableCell>
                    <div className="text-sm">
                      <div className="font-medium">{order.buyer_username || 'N/A'}</div>
                      <div className="text-gray-500 text-xs">{order.buyer_email || ''}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge className={getStatusColor(order.order_status)}>
                      {order.order_status || 'UNKNOWN'}
                    </Badge>
                  </TableCell>
                  <TableCell>{order.line_items?.length || 0} item(s)</TableCell>
                  <TableCell className="text-right font-medium">
                    {formatCurrency(order.total_amount || 0)}
                  </TableCell>
                  <TableCell>
                    {order.tracking_number && (
                      <span className="text-xs text-blue-600">{order.tracking_number}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {selectedOrder && (
          <div className="mt-6 border rounded-lg p-6 bg-gray-50">
            <h3 className="text-lg font-semibold mb-4">Order Details: {selectedOrder.order_id}</h3>

            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <div className="text-sm text-gray-600">Buyer Information</div>
                <div className="mt-2">
                  <div className="font-medium">{selectedOrder.buyer_username}</div>
                  <div className="text-sm text-gray-600">{selectedOrder.buyer_email}</div>
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Order Summary</div>
                <div className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span>Subtotal:</span>
                    <span>{formatCurrency(selectedOrder.total_amount - (selectedOrder.shipping_cost || 0) - (selectedOrder.tax_amount || 0))}</span>
                  </div>
                  {selectedOrder.shipping_cost && (
                    <div className="flex justify-between">
                      <span>Shipping:</span>
                      <span>{formatCurrency(selectedOrder.shipping_cost)}</span>
                    </div>
                  )}
                  {selectedOrder.tax_amount && (
                    <div className="flex justify-between">
                      <span>Tax:</span>
                      <span>{formatCurrency(selectedOrder.tax_amount)}</span>
                    </div>
                  )}
                  <div className="flex justify-between font-bold border-t pt-1">
                    <span>Total:</span>
                    <span>{formatCurrency(selectedOrder.total_amount)}</span>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <div className="text-sm text-gray-600 mb-2">Line Items</div>
              <div className="space-y-2">
                {(selectedOrder.line_items || []).map((item) => (
                  <div key={item.id} className="flex items-center gap-4 bg-white p-3 rounded">
                    {item.image_url && (
                      <img src={item.image_url} alt={item.title} className="w-16 h-16 object-cover rounded" />
                    )}
                    <div className="flex-1">
                      <div className="font-medium">{item.title || 'Unknown item'}</div>
                      <div className="text-sm text-gray-600">
                        Quantity: {item.quantity || 1} × {formatCurrency(item.unit_price || 0)}
                      </div>
                    </div>
                    <div className="font-medium">{formatCurrency(item.total_price || 0)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
