import { useState, useEffect, useMemo, useRef } from 'react';
import { getMessages, updateMessage, getMessageStats, MessagesListResponse } from '../api/messages';
import { Mail, MailOpen, Star, Archive, Search, Inbox, Send, Flag, FolderPlus, Folder, Trash2, Maximize2, X } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import FixedHeader from '@/components/FixedHeader';
import apiClient from '../api/client';

interface ParsedThreadEntry {
  // Backend fields (from parser)
  author?: string | null;
  direction: 'inbound' | 'outbound' | 'system' | string;
  role?: 'buyer' | 'seller' | 'system' | 'other' | string;
  text: string;
  timestamp?: string | null;
  // Optional, future-friendly fields from prompt spec
  id?: string;
  sentAt?: string;
  fromName?: string;
  toName?: string;
}

interface ParsedOrder {
  orderNumber?: string;
  itemId?: string;
  transactionId?: string;
  title?: string;
  imageUrl?: string;
  itemUrl?: string;
  status?: string;
  viewOrderUrl?: string;
}

interface ParsedMeta {
  emailReferenceId?: string;
  [key: string]: any;
}

interface ParsedBuyer {
  username?: string;
  feedbackScore?: number | null;
  profileUrl?: string | null;
  feedbackUrl?: string | null;
}

interface ParsedMessage {
  buyer?: ParsedBuyer;
  currentMessage?: ParsedThreadEntry | null;
  history?: ParsedThreadEntry[];
  order?: ParsedOrder;
  meta?: ParsedMeta;
  [key: string]: any;
}

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
  // Parsed and normalized structure from backend (see ParsedMessage)
  parsed_body?: ParsedMessage | null;
  bucket?: 'offers' | 'cases' | 'ebay' | 'other';
}

const classifyBucket = (msg: Message): 'offers' | 'cases' | 'ebay' | 'other' => {
  const mt = (msg.message_type || '').toUpperCase();
  const subj = (msg.subject || '').toLowerCase();
  const body = (msg.body || '').toLowerCase();
  const sender = (msg.sender_username || '').toLowerCase();

  // OFFERS – any message that clearly looks like an offer
  if (
    mt.includes('OFFER') ||
    subj.includes('offer') ||
    body.includes('offer')
  ) {
    return 'offers';
  }

  // CASES & DISPUTES – keywords in subject/body or certain message types
  if (
    ['CASE', 'INQUIRY', 'RETURN', 'CANCELLATION', 'UNPAID'].some((k) => mt.includes(k)) ||
    subj.includes('case') ||
    subj.includes('dispute') ||
    body.includes('case') ||
    body.includes('dispute')
  ) {
    return 'cases';
  }

  // EBAY MESSAGES – anything obviously from eBay system
  if (sender.includes('ebay') || mt.includes('EBAY')) {
    return 'ebay';
  }

  return 'other';
};

interface MessageStats {
  unread_count: number;
  flagged_count: number;
}

export const MessagesPage = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<MessageStats>({ unread_count: 0, flagged_count: 0 });
  const [selectedFolder, setSelectedFolder] = useState<'inbox' | 'sent' | 'flagged' | 'archived'>('inbox');
  const [selectedBucket, setSelectedBucket] = useState<'primary' | 'offers' | 'cases' | 'ebay'>('primary');
  const [bucketCounts, setBucketCounts] = useState<{ primary: number; offers: number; cases: number; ebay: number }>(
    {
      primary: 0,
      offers: 0,
      cases: 0,
      ebay: 0,
    },
  );
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [replyText, setReplyText] = useState('');
  const [draftLoading, setDraftLoading] = useState(false);
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [selectedCustomFolder, setSelectedCustomFolder] = useState<string | null>(null);
  // Map of message.id -> custom folder name (e.g. "old"). Stored locally for now.
  const [messageFolders, setMessageFolders] = useState<Record<string, string>>({});
  const [draggedMessageId, setDraggedMessageId] = useState<string | null>(null);
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [topHeightRatio, setTopHeightRatio] = useState(0.6);
  const [isDraggingSplit, setIsDraggingSplit] = useState(false);
  const rightPaneRef = useRef<HTMLDivElement | null>(null);
  const splitStateRef = useRef({ startY: 0, startRatio: 0.6 });

  // Load persisted custom folders and message-folder assignments from localStorage once.
  useEffect(() => {
    try {
      const storedFoldersRaw = localStorage.getItem('messages.customFolders');
      if (storedFoldersRaw) {
        const parsed = JSON.parse(storedFoldersRaw);
        if (Array.isArray(parsed)) {
          setCustomFolders(parsed);
        }
      }
      const storedMapRaw = localStorage.getItem('messages.messageFolders');
      if (storedMapRaw) {
        const parsedMap = JSON.parse(storedMapRaw);
        if (parsedMap && typeof parsedMap === 'object') {
          setMessageFolders(parsedMap as Record<string, string>);
        }
      }
    } catch (e) {
      console.error('Failed to load messages preferences from localStorage', e);
    }
  }, []);

  // Persist custom folders / assignments whenever they change.
  useEffect(() => {
    try {
      localStorage.setItem('messages.customFolders', JSON.stringify(customFolders));
    } catch (e) {
      console.error('Failed to persist custom folders', e);
    }
  }, [customFolders]);

  useEffect(() => {
    try {
      localStorage.setItem('messages.messageFolders', JSON.stringify(messageFolders));
    } catch (e) {
      console.error('Failed to persist message folders', e);
    }
  }, [messageFolders]);

  useEffect(() => {
    loadMessages();
    loadStats();
  }, [selectedFolder, selectedBucket]);

  // Reset source view when switching messages
  useEffect(() => {
    setShowSource(false);
  }, [selectedMessage]);

  // Handle splitter drag events on window
  useEffect(() => {
    if (!isDraggingSplit) return;

    const handleMove = (e: MouseEvent) => {
      const container = rightPaneRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const height = rect.height || 1;
      const deltaY = e.clientY - splitStateRef.current.startY;
      let nextRatio = splitStateRef.current.startRatio + deltaY / height;
      // Clamp between 20% and 80%
      nextRatio = Math.max(0.2, Math.min(0.8, nextRatio));
      setTopHeightRatio(nextRatio);
    };

    const handleUp = () => {
      setIsDraggingSplit(false);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [isDraggingSplit]);

  const loadMessages = async () => {
    try {
      setLoading(true);

      const searching = searchQuery.trim().length > 0;

      // Map UI bucket to API bucket. "primary" reuses "all" data but we compute buckets/counts on the client.
      const apiBucket: 'all' | 'offers' | 'cases' | 'ebay' =
        selectedBucket === 'primary' ? 'all' : selectedBucket;

      // For now, search always hits the inbox view on the backend, but we keep all
      // custom-folder filtering on the client so that results span custom folders.
      const folderForApi = searching ? 'inbox' : selectedFolder;

      const data: MessagesListResponse = await getMessages(folderForApi, false, searchQuery, apiBucket);
      const rawItems: Message[] = Array.isArray(data.items) ? (data.items as Message[]) : [];

      const itemsWithBuckets = rawItems.map((m) => ({ ...m, bucket: classifyBucket(m) }));

      // Compute counts locally so we don't depend on backend version.
      const counts = {
        primary: 0,
        offers: 0,
        cases: 0,
        ebay: 0,
      };

      for (const m of itemsWithBuckets) {
        if (m.bucket === 'offers') counts.offers += 1;
        else if (m.bucket === 'cases') counts.cases += 1;
        else if (m.bucket === 'ebay') counts.ebay += 1;
        else counts.primary += 1;
      }

      // Apply custom folder + bucket filters in-memory.
      let working = itemsWithBuckets;

      if (!searching) {
        // When viewing Inbox, hide any messages that have been moved into a custom folder.
        if (!selectedCustomFolder && selectedFolder === 'inbox') {
          working = working.filter((m) => !messageFolders[m.id]);
        }

        // When a custom folder is selected, show only messages assigned to it.
        if (selectedCustomFolder) {
          working = working.filter((m) => messageFolders[m.id] === selectedCustomFolder);
        }
      }

      const filteredItems =
        selectedBucket === 'primary'
          ? working.filter((m) => m.bucket === 'other')
          : working.filter((m) => m.bucket === apiBucket || apiBucket === 'all');

      setMessages(filteredItems);
      setBucketCounts(counts);
    } catch (error) {
      console.error('Failed to load messages:', error);
      setMessages([]);
      setBucketCounts({ primary: 0, offers: 0, cases: 0, ebay: 0 });
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
    setReplyText('');

    // Optimistically mark as read without reloading the whole list so the detail
    // panel stays open and the row styling updates immediately.
    if (!message.is_read && message.direction === 'INCOMING') {
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, is_read: true } : m)),
      );
      setSelectedMessage((prev) => (prev && prev.id === message.id ? { ...prev, is_read: true } : prev));
      try {
        await updateMessage(message.id, { is_read: true });
        loadStats();
      } catch (e) {
        console.error('Failed to mark message as read', e);
      }
    }
  };

  const handleToggleFlagged = async (message: Message, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextFlag = !message.is_flagged;
    setMessages((prev) =>
      prev.map((m) => (m.id === message.id ? { ...m, is_flagged: nextFlag } : m)),
    );
    setSelectedMessage((prev) => (prev && prev.id === message.id ? { ...prev, is_flagged: nextFlag } : prev));
    try {
      await updateMessage(message.id, { is_flagged: nextFlag });
      loadStats();
    } catch (err) {
      console.error('Failed to toggle flag', err);
    }
  };

  const handleArchive = async (message: Message) => {
    // Remove from current view and clear selection; archived messages can still
    // be viewed from the Archived folder.
    setMessages((prev) => prev.filter((m) => m.id !== message.id));
    setSelectedMessage((prev) => (prev && prev.id === message.id ? null : prev));
    try {
      await updateMessage(message.id, { is_archived: true });
    } catch (err) {
      console.error('Failed to archive message', err);
    }
  };

  const handleDelete = async (message: Message) => {
    // Placeholder for real delete logic – for now just clear selection and refresh list.
    console.log('Delete message (not yet wired to backend):', message.id);
    setSelectedMessage(null);
    await loadMessages();
  };

  const handleDraftWithAI = async (message: Message) => {
    try {
      setDraftLoading(true);
      const resp = await apiClient.post(`/api/ai/messages/${message.id}/draft`, {
        ebay_account_id: undefined,
        house_name: undefined,
      });
      setReplyText(resp.data?.draft || '');
    } catch (e) {
      console.error('Failed to draft reply with AI', e);
    } finally {
      setDraftLoading(false);
    }
  };

  const visibleMessages = useMemo(() => messages, [messages]);

  const handleAddCustomFolder = () => {
    const name = window.prompt('Folder name');
    if (!name) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    setCustomFolders((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
    setSelectedCustomFolder(trimmed);
  };

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, messageId: string) => {
    setDraggedMessageId(messageId);
    try {
      e.dataTransfer.setData('application/x-message-id', messageId);
      e.dataTransfer.setData('text/plain', messageId);
      e.dataTransfer.effectAllowed = 'move';
    } catch {
      // Ignore browsers that restrict dataTransfer in some contexts.
    }
  };

  const handleDragEnd = () => {
    setDraggedMessageId(null);
  };

  const handleDropOnCustomFolder = (e: React.DragEvent<HTMLButtonElement>, folderName: string) => {
    e.preventDefault();
    let id = draggedMessageId;
    if (!id) {
      try {
        id = e.dataTransfer.getData('application/x-message-id') || e.dataTransfer.getData('text/plain') || null;
      } catch {
        id = null;
      }
    }
    if (!id) return;

    setMessageFolders((prev) => ({ ...prev, [id as string]: folderName }));
    setSelectedCustomFolder(folderName);
    setDraggedMessageId(null);
    setDragOverFolder(null);
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
      case 'SHIPPING':
        return 'bg-blue-100 text-blue-800';
      case 'ISSUE':
        return 'bg-red-100 text-red-800';
      case 'FEEDBACK':
        return 'bg-green-100 text-green-800';
      case 'QUESTION':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const htmlToText = (html: string | null | undefined): string => {
    if (!html) return '';
    try {
      const div = document.createElement('div');
      div.innerHTML = html;
      // Strip scripts/styles/noscript so CSS/JS don't leak into text
      div.querySelectorAll('script, style, noscript').forEach((el) => el.remove());
      const text = div.textContent || div.innerText || '';
      return text
        .replace(/\s+\n/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    } catch {
      return (html || '').toString();
    }
  };

  const getMessageSnippet = (message: Message): string => {
    const parsedText = (message.parsed_body?.currentMessage?.text || '').trim();
    let preview = parsedText || htmlToText(message.body || '');

    preview = preview.replace(/\s+/g, ' ').trim();
    const MAX_PREVIEW = 160;
    if (preview.length > MAX_PREVIEW) {
      preview = preview.slice(0, MAX_PREVIEW - 1).trimEnd() + '…';
    }
    return preview;
  };

  const renderTextWithLineBreaks = (text?: string) => {
    if (!text) return null;
    const lines = text.split('\n');
    return (
      <>
        {lines.map((line, idx) => (
          <span key={idx}>
            {line}
            {idx < lines.length - 1 && <br />}
          </span>
        ))}
      </>
    );
  };

  return (
    <div className="h-screen flex flex-col bg-white">
      <FixedHeader />
      <div className="pt-12 flex flex-1 overflow-x-hidden overflow-y-auto">
        {/* Left Sidebar - Folders */}
        <div className="w-64 border-r bg-gray-50 p-4 flex flex-col">
          <div className="space-y-1">
            <Button
              variant={
                selectedFolder === 'inbox'
                  ? 'secondary'
                  : dragOverFolder === 'inbox'
                  ? 'outline'
                  : 'ghost'
              }
              className={`w-full justify-start ${
                dragOverFolder === 'inbox' ? 'border border-blue-400 bg-blue-50' : ''
              }`}
              onClick={() => {
                setSelectedFolder('inbox');
                setSelectedCustomFolder(null);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={() => setDragOverFolder('inbox')}
              onDragLeave={() => setDragOverFolder((prev) => (prev === 'inbox' ? null : prev))}
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
              variant={
                selectedFolder === 'sent'
                  ? 'secondary'
                  : dragOverFolder === 'sent'
                  ? 'outline'
                  : 'ghost'
              }
              className={`w-full justify-start ${
                dragOverFolder === 'sent' ? 'border border-blue-400 bg-blue-50' : ''
              }`}
              onClick={() => {
                setSelectedFolder('sent');
                setSelectedCustomFolder(null);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={() => setDragOverFolder('sent')}
              onDragLeave={() => setDragOverFolder((prev) => (prev === 'sent' ? null : prev))}
            >
              <Send className="mr-2 h-4 w-4" />
              Sent
            </Button>

            <Button
              variant={
                selectedFolder === 'flagged'
                  ? 'secondary'
                  : dragOverFolder === 'flagged'
                  ? 'outline'
                  : 'ghost'
              }
              className={`w-full justify-start ${
                dragOverFolder === 'flagged' ? 'border border-blue-400 bg-blue-50' : ''
              }`}
              onClick={() => {
                setSelectedFolder('flagged');
                setSelectedCustomFolder(null);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={() => setDragOverFolder('flagged')}
              onDragLeave={() => setDragOverFolder((prev) => (prev === 'flagged' ? null : prev))}
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
              variant={
                selectedFolder === 'archived'
                  ? 'secondary'
                  : dragOverFolder === 'archived'
                  ? 'outline'
                  : 'ghost'
              }
              className={`w-full justify-start ${
                dragOverFolder === 'archived' ? 'border border-blue-400 bg-blue-50' : ''
              }`}
              onClick={() => {
                setSelectedFolder('archived');
                setSelectedCustomFolder(null);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={() => setDragOverFolder('archived')}
              onDragLeave={() => setDragOverFolder((prev) => (prev === 'archived' ? null : prev))}
            >
              <Archive className="mr-2 h-4 w-4" />
              Archived
            </Button>
          </div>

          {/* Custom folders */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <span>Custom folders</span>
              <button
                type="button"
                className="flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-700"
                onClick={handleAddCustomFolder}
              >
                <FolderPlus className="h-3 w-3" />
                Add
              </button>
            </div>
            <div className="space-y-1">
              {customFolders.length === 0 && (
                <div className="text-[11px] text-gray-400 px-1">No custom folders yet</div>
              )}
              {customFolders.map((name) => (
                <Button
                  key={name}
                  variant={
                    selectedCustomFolder === name
                      ? 'secondary'
                      : dragOverFolder === name
                      ? 'outline'
                      : 'ghost'
                  }
                  className={`w-full justify-start ${
                    dragOverFolder === name ? 'border border-blue-400 bg-blue-50' : ''
                  }`}
                  onClick={() => setSelectedCustomFolder(name)}
                  onDragOver={(e) => e.preventDefault()}
                  onDragEnter={() => setDragOverFolder(name)}
                  onDragLeave={() => setDragOverFolder((prev) => (prev === name ? null : prev))}
                  onDrop={(e) => handleDropOnCustomFolder(e, name)}
                >
                  <Folder className="mr-2 h-4 w-4" />
                  {name}
                </Button>
              ))}
            </div>
          </div>
        </div>

        {/* Right side: header + resizable split view */}
        <div className="flex-1 flex flex-col min-h-0" ref={rightPaneRef}>
          {/* Compact toolbar with search + Gmail-like buckets in one row */}
          <div className="border-b bg-white">
            <div className="px-4 py-2 flex items-center justify-between gap-3">
              <div className="relative flex-1 max-w-xl">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="Search messages..."
                  className="pl-10"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && loadMessages()}
                />
              </div>
              <div className="flex items-center justify-end">
                <div className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-1 text-xs">
                  {([
                    { key: 'primary', label: 'Primary' },
                    { key: 'offers', label: 'Offers' },
                    { key: 'cases', label: 'Cases & Disputes' },
                    { key: 'ebay', label: 'eBay Messages' },
                  ] as const).map((b) => (
                    <Button
                      key={b.key}
                      variant={selectedBucket === b.key ? 'secondary' : 'ghost'}
                      size="sm"
                      className="flex items-center gap-1 px-3 rounded-full"
                      onClick={() => setSelectedBucket(b.key)}
                    >
                      <span>{b.label}</span>
                      <Badge
                        variant={selectedBucket === b.key ? 'default' : 'outline'}
                        className="ml-1"
                      >
                        {bucketCounts[b.key] ?? 0}
                      </Badge>
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Resizable split: top list + bottom detail */}
          <div className="flex-1 flex flex-col min-h-0">
            {/* Top panel - message list */}
            <div
              style={{ flexBasis: `${topHeightRatio * 100}%` }}
              className="min-h-[120px] border-b bg-white overflow-hidden"
            >
              <ScrollArea className="h-full">
              {loading ? (
                <div className="p-4 text-center text-gray-500">Loading...</div>
              ) : visibleMessages.length === 0 ? (
                <div className="p-4 text-center text-gray-500">No messages</div>
              ) : (
                <div className="divide-y">
                  {visibleMessages.map((message) => (
                    <div
                      key={message.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, message.id)}
                      onDragEnd={handleDragEnd}
                      className={`px-4 py-3 cursor-pointer hover:bg-gray-50 text-sm flex items-start justify-between gap-3 ${
                        selectedMessage?.id === message.id ? 'bg-blue-50' : ''
                      } ${
                        !message.is_read && message.direction === 'INCOMING' ? 'bg-blue-50/40' : ''
                      }`}
                      onClick={() => handleMessageClick(message)}
                    >
                      <div className="flex items-start gap-2 flex-1 min-w-0">
                        {message.direction === 'INCOMING' && !message.is_read ? (
                          <Mail className="h-4 w-4 text-blue-600 flex-shrink-0 mt-[2px]" />
                        ) : (
                          <MailOpen className="h-4 w-4 text-gray-400 flex-shrink-0 mt-[2px]" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <span
                              className={`truncate ${
                                !message.is_read && message.direction === 'INCOMING'
                                  ? 'font-semibold'
                                  : ''
                              }`}
                            >
                              {message.direction === 'INCOMING'
                                ? message.sender_username
                                : message.recipient_username}
                            </span>
                            {message.message_type && (
                              <Badge
                                className={`text-[10px] ${getMessageTypeColor(message.message_type)}`}
                              >
                                {message.message_type}
                              </Badge>
                            )}
                          </div>
                          <div
                            className={`truncate text-xs ${
                              !message.is_read && message.direction === 'INCOMING'
                                ? 'font-semibold'
                                : 'text-gray-600'
                            }`}
                          >
                            {message.subject || '(No subject)'}
                          </div>
                          <div className="truncate text-xs text-gray-500">
                            {getMessageSnippet(message)}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
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
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>

            {/* Splitter handle */}
            <div
              className={`h-1 bg-gray-200 ${isDraggingSplit ? 'bg-gray-300' : ''} cursor-row-resize`}
              onMouseDown={(e) => {
                splitStateRef.current = { startY: e.clientY, startRatio: topHeightRatio };
                setIsDraggingSplit(true);
              }}
            />

            {/* Bottom panel - message detail & reply */}
            <div
              style={{ flexBasis: `${(1 - topHeightRatio) * 100}%` }}
              className="min-h-[160px] flex flex-col bg-white overflow-hidden"
            >
              {selectedMessage ? (
              <>
                <div className="border-b p-4 md:p-4">
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <div className="flex-1 min-w-0">
                      <h2 className="text-lg md:text-xl font-semibold mb-1 truncate">
                        {selectedMessage.subject || '(No subject)'}
                      </h2>
                      <div className="flex items-center gap-2 text-sm text-gray-600 flex-wrap">
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
                    <div className="flex flex-col gap-2 items-end">
                      <div className="flex flex-wrap gap-2 justify-end">
                        <Badge variant="outline">
                          {selectedMessage.bucket === 'offers'
                            ? 'OFFERS'
                            : selectedMessage.bucket === 'cases'
                            ? 'CASES & DISPUTES'
                            : selectedMessage.bucket === 'ebay'
                            ? 'EBAY MESSAGE'
                            : 'OTHER'}
                        </Badge>
                        <Badge variant="outline">
                          {selectedMessage.direction === 'INCOMING' ? 'Inbox' : 'Sent'}
                        </Badge>
                        {selectedMessage.is_read ? (
                          <Badge variant="outline">Read</Badge>
                        ) : (
                          <Badge variant="default">Unread</Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2 justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowSource((prev) => !prev)}
                        >
                          {showSource ? 'Hide source' : 'View source'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setIsDetailModalOpen(true)}
                        >
                          <Maximize2 className="h-4 w-4 mr-1" /> Pop out
                        </Button>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => {
                            const textarea = document.getElementById('reply-textarea');
                            textarea?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            (textarea as HTMLTextAreaElement | null)?.focus?.();
                          }}
                        >
                          <Send className="h-4 w-4 mr-1" /> Reply
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={draftLoading}
                          onClick={() => handleDraftWithAI(selectedMessage)}
                        >
                          {draftLoading ? 'AI answering…' : 'AI Answer'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleArchive(selectedMessage)}
                        >
                          <Archive className="h-4 w-4 mr-1" /> Archive
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(selectedMessage)}
                        >
                          <Trash2 className="h-4 w-4 mr-1" /> Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <ScrollArea className="flex-1 p-4 md:p-6">
                  <div className="space-y-3 text-gray-800 text-sm">
                    {/* Order / item card from parsed_body.order, if available */}
                    {selectedMessage.parsed_body?.order && (
                      <div className="flex gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                        {selectedMessage.parsed_body.order.imageUrl && (
                          <div className="flex-shrink-0">
                            <img
                              src={selectedMessage.parsed_body.order.imageUrl}
                              alt={selectedMessage.parsed_body.order.title || 'Item image'}
                              className="w-16 h-16 object-cover rounded"
                            />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          {selectedMessage.parsed_body.order.title && (
                            <div className="font-semibold text-sm mb-1 truncate">
                              {selectedMessage.parsed_body.order.itemUrl ? (
                                <a
                                  href={selectedMessage.parsed_body.order.itemUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-blue-600 hover:underline"
                                >
                                  {selectedMessage.parsed_body.order.title}
                                </a>
                              ) : (
                                selectedMessage.parsed_body.order.title
                              )}
                            </div>
                          )}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-700">
                            {selectedMessage.parsed_body.order.orderNumber && (
                              <div>
                                <span className="font-medium">Order #:</span>{' '}
                                {selectedMessage.parsed_body.order.orderNumber}
                              </div>
                            )}
                            {selectedMessage.parsed_body.order.itemId && (
                              <div>
                                <span className="font-medium">Item ID:</span>{' '}
                                {selectedMessage.parsed_body.order.itemId}
                              </div>
                            )}
                            {selectedMessage.parsed_body.order.transactionId && (
                              <div>
                                <span className="font-medium">Transaction ID:</span>{' '}
                                {selectedMessage.parsed_body.order.transactionId}
                              </div>
                            )}
                            {selectedMessage.parsed_body.order.status && (
                              <div>
                                <span className="font-medium">Status:</span>{' '}
                                {selectedMessage.parsed_body.order.status}
                              </div>
                            )}
                          </div>

                          {selectedMessage.parsed_body.order.viewOrderUrl && (
                            <div className="mt-2 text-xs">
                              <a
                                href={selectedMessage.parsed_body.order.viewOrderUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="text-blue-600 hover:underline"
                              >
                                View order details on eBay
                              </a>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Thread view built from parsed_body.history + parsed_body.currentMessage */}
                    <div className="text-gray-800 text-sm">
                      {selectedMessage.parsed_body &&
                      ((selectedMessage.parsed_body.history && selectedMessage.parsed_body.history.length > 0) ||
                        selectedMessage.parsed_body.currentMessage) ? (
                        <div className="space-y-2">
                          {[...(selectedMessage.parsed_body.history || []),
                            ...(selectedMessage.parsed_body.currentMessage
                              ? [selectedMessage.parsed_body.currentMessage]
                              : []),
                          ].map((entry, idx) => {
                            const dir = (entry.direction || 'system') as string;
                            const isSeller = dir === 'outbound';
                            const isSystem = dir === 'system';

                            const containerAlign = isSystem
                              ? 'items-center justify-center'
                              : isSeller
                              ? 'items-end justify-end'
                              : 'items-start justify-start';

                            const bubbleClasses = isSystem
                              ? 'bg-gray-100 text-gray-800'
                              : isSeller
                              ? 'bg-blue-600 text-white'
                              : 'bg-gray-100 text-gray-900';

                            const author = entry.fromName || entry.author;
                            const ts = entry.sentAt || entry.timestamp;

                            return (
                              <div key={entry.id || idx} className={`flex ${containerAlign}`}>
                                <div
                                  className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${bubbleClasses}`}
                                >
                                  {author && (
                                    <div className="text-[11px] mb-1 opacity-80">
                                      {author}
                                      {ts && (
                                        <span className="ml-1">
                                          · {new Date(ts).toLocaleString()}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                  <div className="text-xs md:text-sm">
                                    {renderTextWithLineBreaks(entry.text)}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap">
                          {htmlToText(selectedMessage.body)}
                        </div>
                      )}
                    </div>

                    {showSource && (
                      <pre className="mt-3 max-h-80 overflow-auto text-xs bg-gray-50 p-2 rounded border border-gray-200">
                        {selectedMessage.body}
                      </pre>
                    )}
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

                  {/* Reply box */}
                  <div className="mt-6 border-t pt-4" id="reply-section">
                    <h3 className="font-semibold mb-2">Reply message</h3>
                    <textarea
                      id="reply-textarea"
                      className="w-full border rounded-md p-2 text-sm min-h-[120px] focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Type your reply here..."
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                    />
                    <div className="mt-3 flex flex-wrap gap-2 justify-end">
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => {
                          console.log('Send reply (stub):', {
                            messageId: selectedMessage.id,
                            replyText,
                          });
                          setReplyText('');
                        }}
                      >
                        <Send className="h-4 w-4 mr-1" /> Reply
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setReplyText('')}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>
                </ScrollArea>
              </>
            ) : (
              // Keep the bottom container visually empty until a message is selected.
              <div className="flex-1" />
            )}
          </div>
        </div>
      </div>
    </div>

      {/* Pop-out modal for full-screen message view */}
      {isDetailModalOpen && selectedMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-lg shadow-xl w-[90vw] max-w-5xl h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-2 border-b">
              <div className="text-sm font-semibold truncate">
                {selectedMessage.subject || '(No subject)'}
              </div>
              <button
                type="button"
                className="p-1 rounded hover:bg-gray-100"
                onClick={() => setIsDetailModalOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <div className="h-full overflow-auto p-4">
                {/* Reuse the same order card + thread view as in the detail panel */}
                <div className="space-y-3 text-gray-800 text-sm max-w-3xl mx-auto">
                  {/* Modal actions & status row */}
                  <div className="flex items-center justify-between gap-3 mb-1">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">
                        {selectedMessage.bucket === 'offers'
                          ? 'OFFERS'
                          : selectedMessage.bucket === 'cases'
                          ? 'CASES & DISPUTES'
                          : selectedMessage.bucket === 'ebay'
                          ? 'EBAY MESSAGE'
                          : 'OTHER'}
                      </Badge>
                      <Badge variant="outline">
                        {selectedMessage.direction === 'INCOMING' ? 'Inbox' : 'Sent'}
                      </Badge>
                      {selectedMessage.is_read ? (
                        <Badge variant="outline">Read</Badge>
                      ) : (
                        <Badge variant="default">Unread</Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2 justify-end">
                      <Badge variant="outline">
                        {selectedMessage.direction === 'INCOMING' ? 'Inbox' : 'Sent'}
                      </Badge>
                      {selectedMessage.is_read ? (
                        <Badge variant="outline">Read</Badge>
                      ) : (
                        <Badge variant="default">Unread</Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2 justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowSource((prev) => !prev)}
                      >
                        {showSource ? 'Hide source' : 'View source'}
                      </Button>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => {
                          const textarea = document.getElementById('reply-textarea-modal') as HTMLTextAreaElement | null;
                          textarea?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                          textarea?.focus?.();
                        }}
                      >
                        <Send className="h-4 w-4 mr-1" /> Reply
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={draftLoading}
                        onClick={() => handleDraftWithAI(selectedMessage)}
                      >
                        {draftLoading ? 'AI answering…' : 'AI Answer'}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          handleArchive(selectedMessage);
                          setIsDetailModalOpen(false);
                        }}
                      >
                        <Archive className="h-4 w-4 mr-1" /> Archive
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          handleDelete(selectedMessage);
                          setIsDetailModalOpen(false);
                        }}
                      >
                        <Trash2 className="h-4 w-4 mr-1" /> Delete
                      </Button>
                    </div>
                  </div>

                  {selectedMessage.parsed_body?.order && (
                    <div className="flex gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                      {selectedMessage.parsed_body.order.imageUrl && (
                        <div className="flex-shrink-0">
                          <img
                            src={selectedMessage.parsed_body.order.imageUrl}
                            alt={selectedMessage.parsed_body.order.title || 'Item image'}
                            className="w-16 h-16 object-cover rounded"
                          />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        {selectedMessage.parsed_body.order.title && (
                          <div className="font-semibold text-sm mb-1 truncate">
                            {selectedMessage.parsed_body.order.itemUrl ? (
                              <a
                                href={selectedMessage.parsed_body.order.itemUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="text-blue-600 hover:underline"
                              >
                                {selectedMessage.parsed_body.order.title}
                              </a>
                            ) : (
                              selectedMessage.parsed_body.order.title
                            )}
                          </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-700">
                          {selectedMessage.parsed_body.order.orderNumber && (
                            <div>
                              <span className="font-medium">Order #:</span>{' '}
                              {selectedMessage.parsed_body.order.orderNumber}
                            </div>
                          )}
                          {selectedMessage.parsed_body.order.itemId && (
                            <div>
                              <span className="font-medium">Item ID:</span>{' '}
                              {selectedMessage.parsed_body.order.itemId}
                            </div>
                          )}
                          {selectedMessage.parsed_body.order.transactionId && (
                            <div>
                              <span className="font-medium">Transaction ID:</span>{' '}
                              {selectedMessage.parsed_body.order.transactionId}
                            </div>
                          )}
                          {selectedMessage.parsed_body.order.status && (
                            <div>
                              <span className="font-medium">Status:</span>{' '}
                              {selectedMessage.parsed_body.order.status}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="text-gray-800 text-sm">
                    {selectedMessage.parsed_body &&
                    ((selectedMessage.parsed_body.history && selectedMessage.parsed_body.history.length > 0) ||
                      selectedMessage.parsed_body.currentMessage) ? (
                      <div className="space-y-2">
                        {[...(selectedMessage.parsed_body.history || []),
                          ...(selectedMessage.parsed_body.currentMessage
                            ? [selectedMessage.parsed_body.currentMessage]
                            : []),
                        ].map((entry, idx) => {
                          const dir = (entry.direction || 'system') as string;
                          const isSeller = dir === 'outbound';
                          const isSystem = dir === 'system';
                          const containerAlign = isSystem
                            ? 'items-center justify-center'
                            : isSeller
                            ? 'items-end justify-end'
                            : 'items-start justify-start';
                          const bubbleClasses = isSystem
                            ? 'bg-gray-100 text-gray-800'
                            : isSeller
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-100 text-gray-900';
                          const author = entry.fromName || entry.author;
                          const ts = entry.sentAt || entry.timestamp;

                          return (
                            <div key={entry.id || idx} className={`flex ${containerAlign}`}>
                              <div
                                className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${bubbleClasses}`}
                              >
                                {author && (
                                  <div className="text-[11px] mb-1 opacity-80">
                                    {author}
                                    {ts && (
                                      <span className="ml-1">
                                        · {new Date(ts).toLocaleString()}
                                      </span>
                                    )}
                                  </div>
                                )}
                                <div className="text-xs md:text-sm">
                                  {renderTextWithLineBreaks(entry.text)}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap">
                        {htmlToText(selectedMessage.body)}
                      </div>
                    )}
                  </div>

                  {showSource && (
                    <pre className="mt-3 max-h-80 overflow-auto text-xs bg-gray-50 p-2 rounded border border-gray-200">
                      {selectedMessage.body}
                    </pre>
                  )}
                </div>
              </div>

              {/* Reply box pinned to bottom of pop-out */}
              <div className="border-t p-4">
                <h3 className="font-semibold mb-2">Reply message</h3>
                <textarea
                  id="reply-textarea-modal"
                  className="w-full border rounded-md p-2 text-sm min-h-[120px] focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Type your reply here..."
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                />
                <div className="mt-3 flex flex-wrap gap-2 justify-end">
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => {
                      console.log('Send reply (stub):', {
                        messageId: selectedMessage.id,
                        replyText,
                      });
                      setReplyText('');
                    }}
                  >
                    <Send className="h-4 w-4 mr-1" /> Reply
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setReplyText('')}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
};
