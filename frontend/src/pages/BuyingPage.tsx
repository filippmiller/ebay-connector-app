import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import FixedHeader from '@/components/FixedHeader';

export default function BuyingPage() {
  const [, setPurchases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchPurchases();
  }, []);

  const fetchPurchases = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/buying?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setPurchases(data.purchases || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Failed to fetch purchases:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="w-full pt-16 px-4 py-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Buying (Purchases)</h1>

          {loading ? (
            <div className="flex justify-center p-12">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <Card className="p-6">
              <div className="text-center">
                <p className="text-xl font-semibold mb-2">Total Purchases: {total}</p>
                <p className="text-gray-600">Buying module is live</p>
                <p className="text-sm text-gray-500 mt-4">API: GET /api/buying</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
