import apiClient from './client';

export const getOffers = async (
  status: string = '',
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

  const response = await apiClient.get(`/offers/?${params.toString()}`);
  return response.data;
};

export const handleOfferAction = async (
  offerId: string,
  action: 'accept' | 'decline' | 'counter',
  counterAmount?: number
) => {
  const payload: any = { action };
  if (action === 'counter' && counterAmount) {
    payload.counter_amount = counterAmount;
  }

  const response = await apiClient.post(`/offers/${offerId}/action`, payload);
  return response.data;
};

export const getOfferStats = async () => {
  const response = await apiClient.get('/offers/stats/summary');
  return response.data;
};
