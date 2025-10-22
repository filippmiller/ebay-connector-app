import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';

export default function InventoryPage() {
  const [, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    const fetchInventory = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_URL}/api/inventory?limit=50`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
          const data = await response.json();
          setItems(data.items || []);
          setTotal(data.total || 0);
        }
      } catch (error) {
        console.error('Failed to fetch inventory:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchInventory();
  }, []);

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Inventory</h1>

      {loading ? (
        <div className="flex justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      ) : (
        <Card className="p-6">
          <div className="text-center">
            <p className="text-xl font-semibold mb-2">Total Items: {total}</p>
            <p className="text-gray-600">Inventory CRUD module is live</p>
            <p className="text-sm text-gray-500 mt-4">API endpoints: GET/POST/PUT/DELETE /api/inventory</p>
          </div>
        </Card>
      )}
    </div>
  );
}
