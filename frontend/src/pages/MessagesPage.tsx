import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getMessages, updateMessage, getMessageStats } from '../api/messages';
import { Mail, MailOpen, Star, Archive, Search, Inbox, Send, Flag } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import FixedHeader from '@/components/FixedHeader';

interface Message {
  id: string;
  message_id: string;
  thread_id: string | null;
  sender_username: string | null;
  recipient_username: string | null;
  subject: string | null;
  body: string;
  message_type: string | null;
  is_read: boolean;
  is_flagged: boolean;
  is_archived: boolean;
  direction: string;
  message_date: string;
  order_id: string | null;
  listing_id: string | null;
}

interface MessageStats {
  unread_count: number;
  flagged_count: number;
}

export const MessagesPage = () => {
  const { } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<MessageStats>({ unread_count: 0, flagged_count: 0 });
  const [selectedFolder, setSelectedFolder] = useState<'inbox' | 'sent' | 'flagged' | 'archived'>('inbox');
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMessages();
    loadStats();
  }, [selectedFolder]);

  const loadMessages = async () => {
    try {
      setLoading(true);
      const data = await getMessages(selectedFolder, false, searchQuery);
      console.log('Messages data:', data);
      setMessages(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load messages:', error);
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await getMessageStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const handleMessageClick = async (message: Message) => {
    setSelectedMessage(message);
    if (!message.is_read && message.direction === 'INCOMING') {
      await updateMessage(message.id, { is_read: true });
      loadMessages();
      loadStats();
    }
  };

  const handleToggleFlagged = async (message: Message, e: React.MouseEvent) => {
    e.stopPropagation();
    await updateMessage(message.id, { is_flagged: !message.is_flagged });
    loadMessages();
    loadStats();
  };

  const handleArchive = async (message: Message) => {
    await updateMessage(message.id, { is_archived: true });
    setSelectedMessage(null);
    loadMessages();
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHrs = diffMs / (1000 * 60 * 60);

    if (diffHrs < 24) {
      return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    } else if (diffHrs < 48) {
      return 'Yesterday';
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  };

  const getMessageTypeColor = (type: string | null) => {
    switch (type) {
      case 'SHIPPING': return 'bg-blue-100 text-blue-800';
      case 'ISSUE': return 'bg-red-100 text-red-800';
      case 'FEEDBACK': return 'bg-green-100 text-green-800';
      case 'QUESTION': return 'bg-yellow-100 text-yellow-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <FixedHeader />
      <div className="pt-12 flex flex-1 overflow-hidden">
        {/* Left Sidebar - Folders */}
        <div className="w-64 border-r bg-gray-50 p-4">
          <div className="space-y-1">
            <Button
              variant={selectedFolder === 'inbox' ? 'secondary' : 'ghost'}
              className="w-full justify-start"
              onClick={() => setSelectedFolder('inbox')}
            >
              <Inbox className="mr-2 h-4 w-4" />
              Inbox
              {stats && stats.unread_count > 0 && (
                <Badge className="ml-auto" variant="default">
                  {stats.unread_count}
                </Badge>
              )}
            </Button>

            <Button
              variant={selectedFolder === 'sent' ? 'secondary' : 'ghost'}
              className="w-full justify-start"
              onClick={() => setSelectedFolder('sent')}
            >
              <Send className="mr-2 h-4 w-4" />
              Sent
            </Button>

            <Button
              variant={selectedFolder === 'flagged' ? 'secondary' : 'ghost'}
              className="w-full justify-start"
              onClick={() => setSelectedFolder('flagged')}
            >
              <Flag className="mr-2 h-4 w-4" />
              Flagged
              {stats && stats.flagged_count > 0 && (
                <Badge className="ml-auto" variant="outline">
                  {stats.flagged_count}
                </Badge>
              )}
            </Button>

            <Button
              variant={selectedFolder === 'archived' ? 'secondary' : 'ghost'}
              className="w-full justify-start"
              onClick={() => setSelectedFolder('archived')}
            >
              <Archive className="mr-2 h-4 w-4" />
              Archived
            </Button>
          </div>
        </div>

        {/* Middle - Message List */}
        <div className="w-96 border-r flex flex-col">
          <div className="p-4 border-b">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Search messages..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadMessages()}
              />
            </div>
          </div>

          <ScrollArea className="flex-1">
            {loading ? (
              <div className="p-4 text-center text-gray-500">Loading...</div>
            ) : messages.length === 0 ? (
              <div className="p-4 text-center text-gray-500">No messages</div>
            ) : (
              <div className="divide-y">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`p-4 cursor-pointer hover:bg-gray-50 ${
                      selectedMessage?.id === message.id ? 'bg-blue-50' : ''
                    } ${!message.is_read && message.direction === 'INCOMING' ? 'bg-blue-50/30' : ''}`}
                    onClick={() => handleMessageClick(message)}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        {message.direction === 'INCOMING' && !message.is_read ? (
                          <Mail className="h-4 w-4 text-blue-600 flex-shrink-0" />
                        ) : (
                          <MailOpen className="h-4 w-4 text-gray-400 flex-shrink-0" />
                        )}
                        <span className={`truncate ${!message.is_read && message.direction === 'INCOMING' ? 'font-semibold' : ''}`}>
                          {message.direction === 'INCOMING' ? message.sender_username : message.recipient_username}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Star
                          className={`h-4 w-4 cursor-pointer ${
                            message.is_flagged ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'
                          }`}
                          onClick={(e) => handleToggleFlagged(message, e)}
                        />
                        <span className="text-xs text-gray-500">
                          {formatDate(message.message_date)}
                        </span>
                      </div>
                    </div>
                    <div className={`text-sm mb-1 truncate ${!message.is_read && message.direction === 'INCOMING' ? 'font-semibold' : ''}`}>
                      {message.subject || '(No subject)'}
                    </div>
                    <div className="text-sm text-gray-500 truncate">
                      {message.body}
                    </div>
                    {message.message_type && (
                      <Badge className={`mt-2 text-xs ${getMessageTypeColor(message.message_type)}`}>
                        {message.message_type}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>

        {/* Right - Message Detail */}
        <div className="flex-1 flex flex-col">
          {selectedMessage ? (
            <>
              <div className="border-b p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h2 className="text-xl font-semibold mb-2">
                      {selectedMessage.subject || '(No subject)'}
                    </h2>
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <span className="font-medium">
                        {selectedMessage.direction === 'INCOMING' ? 'From:' : 'To:'}
                      </span>
                      <span>
                        {selectedMessage.direction === 'INCOMING' 
                          ? selectedMessage.sender_username 
                          : selectedMessage.recipient_username}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {new Date(selectedMessage.message_date).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleArchive(selectedMessage)}
                    >
                      <Archive className="h-4 w-4 mr-2" />
                      Archive
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleToggleFlagged(selectedMessage, e);
                      }}
                    >
                      <Star className={`h-4 w-4 mr-2 ${selectedMessage.is_flagged ? 'fill-yellow-400 text-yellow-400' : ''}`} />
                      {selectedMessage.is_flagged ? 'Unflag' : 'Flag'}
                    </Button>
                  </div>
                </div>
              </div>

              <ScrollArea className="flex-1 p-6">
                <div className="whitespace-pre-wrap text-gray-800">
                  {selectedMessage.body}
                </div>

                {(selectedMessage.order_id || selectedMessage.listing_id) && (
                  <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                    <h3 className="font-semibold mb-2">Related Items</h3>
                    {selectedMessage.order_id && (
                      <div className="text-sm text-gray-600">
                        Order: {selectedMessage.order_id}
                      </div>
                    )}
                    {selectedMessage.listing_id && (
                      <div className="text-sm text-gray-600">
                        Listing: {selectedMessage.listing_id}
                      </div>
                    )}
                  </div>
                )}
              </ScrollArea>

              <div className="border-t p-4">
                <Button className="w-full">
                  <Send className="h-4 w-4 mr-2" />
                  Reply
                </Button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              <div className="text-center">
                <Mail className="h-16 w-16 mx-auto mb-4 opacity-20" />
                <p>Select a message to read</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
