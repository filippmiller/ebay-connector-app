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

  const response = await apiClient.get(`/orders/?${params.toString()}`);
  return response;
};

export const getOrder = async (orderId: string) => {
  const response = await apiClient.get(`/orders/${orderId}`);
  return response;
};

export const getOrderStats = async () => {
  const response = await apiClient.get('/orders/stats/summary');
  return response;
};
