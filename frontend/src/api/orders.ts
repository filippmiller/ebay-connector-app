import apiClient from './client';

export const getOrders = async (
  status: string = '',
  search: string = '',
  skip: number = 0,
  limit: number = 50
) => {
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  });
  
  if (status) {
    params.append('status', status);
  }
  
  if (search) {
    params.append('search', search);
  }

  const response = await apiClient.get(`/ebay/orders?${params.toString()}`);
  return response.data.orders || [];
};

export const getOrder = async (orderId: string) => {
  const response = await apiClient.get(`/ebay/orders/${orderId}`);
  return response.data;
};

export const getOrderStats = async () => {
  const response = await apiClient.get('/ebay/analytics/summary');
  return response.data;
};
