import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Mail, Package, DollarSign, LayoutDashboard, Clock } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <main className="w-full pt-16 px-4 sm:px-6 lg:px-8 py-8">
        <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h2 className="text-2xl font-bold mb-4">Quick Access</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/messages')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <Mail className="h-8 w-8 text-blue-600" />
                <div>
                  <h3 className="font-semibold">Messages</h3>
                  <p className="text-sm text-gray-600">View & manage</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/orders-view')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <Package className="h-8 w-8 text-green-600" />
                <div>
                  <h3 className="font-semibold">Orders</h3>
                  <p className="text-sm text-gray-600">View & filter orders</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/offers')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <DollarSign className="h-8 w-8 text-purple-600" />
                <div>
                  <h3 className="font-semibold">Offers</h3>
                  <p className="text-sm text-gray-600">Manage deals</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/analytics')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <LayoutDashboard className="h-8 w-8 text-orange-600" />
                <div>
                  <h3 className="font-semibold">Analytics</h3>
                  <p className="text-sm text-gray-600">View insights & trends</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/timesheets/my')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <Clock className="h-8 w-8 text-blue-600" />
                <div>
                  <h3 className="font-semibold">My Timesheet</h3>
                  <p className="text-sm text-gray-600">Track your working time</p>
                </div>
              </CardContent>
            </Card>
          </div>

          <h2 className="text-2xl font-bold mb-4 mt-8">Core Operations</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/buying')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <Package className="h-8 w-8 text-blue-600" />
                <div>
                  <h3 className="font-semibold">Buying</h3>
                  <p className="text-sm text-gray-600">Purchases from eBay</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/inventory')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <Package className="h-8 w-8 text-green-600" />
                <div>
                  <h3 className="font-semibold">Inventory</h3>
                  <p className="text-sm text-gray-600">Stock management</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/transactions')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <DollarSign className="h-8 w-8 text-purple-600" />
                <div>
                  <h3 className="font-semibold">Transactions</h3>
                  <p className="text-sm text-gray-600">Sales records</p>
                </div>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => navigate('/financials')}
            >
              <CardContent className="p-6 flex items-center gap-4">
                <DollarSign className="h-8 w-8 text-orange-600" />
                <div>
                  <h3 className="font-semibold">Financials</h3>
                  <p className="text-sm text-gray-600">Fees & payouts</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
        </div>
      </main>
    </div>
  );
};
