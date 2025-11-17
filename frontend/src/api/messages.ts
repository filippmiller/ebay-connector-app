import apiClient from './client';

export interface MessagesListResponse {
  items: any[];
  total: number;
  counts: {
    all: number;
    offers: number;
    cases: number;
    ebay: number;
  };
}

export const getMessages = async (
  folder: string = 'inbox',
  unreadOnly: boolean = false,
  search: string = '',
  bucket: 'all' | 'offers' | 'cases' | 'ebay' = 'all',
  skip: number = 0,
  limit: number = 50
): Promise<MessagesListResponse> => {
  const params = new URLSearchParams({
    folder,
    unread_only: unreadOnly.toString(),
    bucket,
    skip: skip.toString(),
    limit: limit.toString(),
  });

  if (search) {
    params.append('search', search);
  }

  const response = await apiClient.get(`/messages/?${params.toString()}`);
  return response.data;
};

export const getMessage = async (messageId: string) => {
  const response = await apiClient.get(`/messages/${messageId}`);
  return response.data;
};

export const updateMessage = async (
  messageId: string,
  updates: {
    is_read?: boolean;
    is_flagged?: boolean;
    is_archived?: boolean;
  }
) => {
  const response = await apiClient.patch(`/messages/${messageId}`, updates);
  return response.data;
};

export const getMessageStats = async () => {
  const response = await apiClient.get('/messages/stats/summary');
  return response.data;
};
