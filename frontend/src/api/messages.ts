import apiClient from './client';

export const getMessages = async (
  folder: string = 'inbox',
  unreadOnly: boolean = false,
  search: string = '',
  skip: number = 0,
  limit: number = 50
) => {
  const params = new URLSearchParams({
    folder,
    unread_only: unreadOnly.toString(),
    skip: skip.toString(),
    limit: limit.toString(),
  });
  
  if (search) {
    params.append('search', search);
  }

  const response = await apiClient.get(`/messages/?${params.toString()}`);
  return response;
};

export const getMessage = async (messageId: string) => {
  const response = await apiClient.get(`/messages/${messageId}`);
  return response;
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
  return response;
};

export const getMessageStats = async () => {
  const response = await apiClient.get('/messages/stats/summary');
  return response;
};
