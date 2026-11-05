"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  api,
  tokenStorage,
  WorkshopBooking,
  WorkshopConversation,
  WorkshopMessage,
} from "@/lib/api/client";
import {
  MessageSquare,
  Send,
  X,
  RefreshCw,
  Check,
  CheckCheck,
  Car,
  Shield,
  AlertCircle,
  Paperclip,
} from "lucide-react";

interface WorkshopChatModalProps {
  booking: WorkshopBooking;
  onClose: () => void;
  currentUserId?: string;
}

export function WorkshopChatModal({
  booking,
  onClose,
  currentUserId,
}: WorkshopChatModalProps) {
  const [conversation, setConversation] = useState<WorkshopConversation | null>(null);
  const [messages, setMessages] = useState<WorkshopMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Message composer
  const [newMessage, setNewMessage] = useState("");
  const [attachmentUrl, setAttachmentUrl] = useState("");
  const [showAttachmentInput, setShowAttachmentInput] = useState(false);
  const [sending, setSending] = useState(false);

  // WebSocket state
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected" | "error">("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom of messages
  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
  }, []);

  // Fetch or initialize conversation on mount or retry
  const fetchConversationAndMessages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const conv = await api.workshops.messaging.getBookingConversation(booking.booking_number || booking.id);
      setConversation(conv);

      const msgs = await api.workshops.messaging.getMessages(conv.id);
      setMessages(msgs || []);

      if (conv.unread_count > 0) {
        api.workshops.messaging.markRead(conv.id).catch(() => {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messaging conversation.");
    } finally {
      setLoading(false);
      setTimeout(() => scrollToBottom(false), 100);
    }
  }, [booking.booking_number, booking.id, scrollToBottom]);

  useEffect(() => {
    let isCancelled = false;

    async function initialize() {
      try {
        const conv = await api.workshops.messaging.getBookingConversation(booking.booking_number || booking.id);
        if (isCancelled) return;
        setConversation(conv);

        const msgs = await api.workshops.messaging.getMessages(conv.id);
        if (isCancelled) return;
        setMessages(msgs || []);

        if (conv.unread_count > 0) {
          api.workshops.messaging.markRead(conv.id).catch(() => {});
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : "Failed to load messaging conversation.");
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
          setTimeout(() => scrollToBottom(false), 100);
        }
      }
    }

    void initialize();
    return () => {
      isCancelled = true;
    };
  }, [booking.booking_number, booking.id, scrollToBottom]);

  // Establish real-time WebSocket connection
  useEffect(() => {
    if (!conversation?.id) return;

    let socket: WebSocket | null = null;
    let reconnectTimer: NodeJS.Timeout | null = null;
    let isDisposed = false;

    const connectWebSocket = () => {
      if (isDisposed) return;
      setWsStatus("connecting");

      try {
        const token = tokenStorage.getAccessToken();
        const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = typeof window !== "undefined" ? window.location.host : "localhost:8000";
        // Connect to Channels endpoint
        const wsUrl = `${protocol}//${host}/ws/workshops/conversations/${conversation.id}/${token ? `?token=${encodeURIComponent(token)}` : ""}`;

        socket = new WebSocket(wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          if (isDisposed) return;
          setWsStatus("connected");
          // Tell server to mark messages read upon connection
          socket?.send(JSON.stringify({ action: "mark_read" }));
        };

        socket.onmessage = (event) => {
          if (isDisposed) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === "chat_message" && data.message) {
              const incomingMsg: WorkshopMessage = data.message;
              setMessages((prev) => {
                // Avoid duplicates
                if (prev.some((m) => m.id === incomingMsg.id)) {
                  return prev;
                }
                return [...prev, incomingMsg];
              });
              setTimeout(() => scrollToBottom(true), 50);

              // If message is from counterparty, mark read immediately
              if (incomingMsg.sender_id !== currentUserId) {
                socket?.send(JSON.stringify({ action: "mark_read" }));
              }
            } else if (data.type === "read_receipt") {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.sender_id === currentUserId
                    ? { ...msg, is_read: true, read_at: data.read_at }
                    : msg
                )
              );
            }
          } catch {
            // Ignore parse errors on malformed socket messages
          }
        };

        socket.onclose = (event) => {
          if (isDisposed) return;
          setWsStatus(event.wasClean ? "disconnected" : "error");
          // Attempt auto-reconnect after 4s
          reconnectTimer = setTimeout(connectWebSocket, 4000);
        };

        socket.onerror = () => {
          if (isDisposed) return;
          setWsStatus("error");
        };
      } catch {
        setWsStatus("error");
      }
    };

    connectWebSocket();

    return () => {
      isDisposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) {
        socket.close();
      }
      wsRef.current = null;
    };
  }, [conversation?.id, currentUserId, scrollToBottom]);

  // Handle message send (dual-mode: WebSocket when connected, REST fallback)
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!conversation) return;

    const trimmed = newMessage.trim();
    const trimmedAttachment = attachmentUrl.trim();
    if (!trimmed && !trimmedAttachment) return;

    setSending(true);
    try {
      const activeWs = wsRef.current;
      if (activeWs && activeWs.readyState === WebSocket.OPEN) {
        // Send via WebSocket for instant delivery
        activeWs.send(
          JSON.stringify({
            action: "send_message",
            content: trimmed,
            attachment_url: trimmedAttachment || undefined,
          })
        );
      } else {
        // Fallback to REST endpoint
        const createdMsg = await api.workshops.messaging.sendMessage(
          conversation.id,
          trimmed,
          trimmedAttachment || undefined
        );
        setMessages((prev) => {
          if (prev.some((m) => m.id === createdMsg.id)) return prev;
          return [...prev, createdMsg];
        });
      }

      setNewMessage("");
      setAttachmentUrl("");
      setShowAttachmentInput(false);
      setTimeout(() => scrollToBottom(true), 60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const formatMessageTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-50 flex items-center justify-center p-3 sm:p-6 overflow-hidden">
      <div className="bg-white rounded-3xl max-w-2xl w-full h-[90vh] max-h-[750px] shadow-2xl flex flex-col border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* MODAL HEADER */}
        <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-2xl bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-md shadow-indigo-200">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm sm:text-base font-bold text-slate-900 truncate">
                  Workshop Communication
                </h3>
                <span className="text-[10px] font-black uppercase tracking-wider text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full shrink-0">
                  {booking.booking_number}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5 truncate">
                <span className="font-semibold text-slate-700">{booking.workshop_name}</span>
                <span>•</span>
                <span className="flex items-center gap-1 truncate">
                  <Car className="w-3 h-3 text-slate-400" />
                  {booking.vehicle_year} {booking.vehicle_make} {booking.vehicle_model}
                  {booking.vehicle_registration_plate && ` (${booking.vehicle_registration_plate})`}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Real-time status pill */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border">
              {wsStatus === "connected" && (
                <div className="flex items-center gap-1.5 text-emerald-700 bg-emerald-50 border-emerald-200 px-2 py-0.5 rounded-full">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span>Live</span>
                </div>
              )}
              {wsStatus === "connecting" && (
                <div className="flex items-center gap-1.5 text-amber-700 bg-amber-50 border-amber-200 px-2 py-0.5 rounded-full">
                  <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                  <span>Connecting...</span>
                </div>
              )}
              {(wsStatus === "disconnected" || wsStatus === "error") && (
                <div className="flex items-center gap-1.5 text-slate-600 bg-slate-100 border-slate-200 px-2 py-0.5 rounded-full">
                  <span className="w-2 h-2 rounded-full bg-slate-400" />
                  <span>Offline Sync</span>
                </div>
              )}
            </div>

            <button
              onClick={onClose}
              className="w-9 h-9 rounded-2xl bg-white hover:bg-slate-100 text-slate-500 hover:text-slate-800 flex items-center justify-center border border-slate-200 transition"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* MESSAGES CONTAINER */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3 bg-slate-50/30">
          {loading ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
              <p className="text-xs font-medium">Loading secure message history...</p>
            </div>
          ) : error ? (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
              <button
                onClick={fetchConversationAndMessages}
                className="ml-auto underline font-bold"
              >
                Retry
              </button>
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3">
              <div className="w-14 h-14 rounded-3xl bg-indigo-50 border border-indigo-100 text-indigo-500 flex items-center justify-center">
                <MessageSquare className="w-7 h-7" />
              </div>
              <div className="max-w-xs space-y-1">
                <h4 className="text-sm font-bold text-slate-800">No messages yet</h4>
                <p className="text-xs text-slate-500">
                  Ask {booking.workshop_name} questions about service progress, estimated collection time, or quotes.
                </p>
              </div>
              <div className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-400 bg-white border border-slate-200 px-3 py-1 rounded-full">
                <Shield className="w-3 h-3 text-indigo-500" />
                <span>End-to-end audit tracked communication</span>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg) => {
                const isMine = currentUserId ? msg.sender_id === currentUserId : msg.sender_type === "BUYER";
                return (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${isMine ? "items-end" : "items-start"}`}
                  >
                    <div className="text-[10px] text-slate-400 font-medium mb-1 px-1">
                      {isMine ? "You" : msg.sender_name || "Workshop Staff"}
                    </div>
                    <div
                      className={`max-w-[82%] sm:max-w-[70%] rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
                        isMine
                          ? "bg-indigo-600 text-white rounded-br-none"
                          : "bg-white text-slate-800 border border-slate-200/80 rounded-bl-none"
                      }`}
                    >
                      <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      {msg.attachment_url && (
                        <a
                          href={msg.attachment_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`mt-2 flex items-center gap-1.5 text-[11px] underline font-medium ${
                            isMine ? "text-indigo-100 hover:text-white" : "text-indigo-600 hover:text-indigo-800"
                          }`}
                        >
                          <Paperclip className="w-3 h-3" />
                          <span>View Attachment</span>
                        </a>
                      )}
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-slate-400 mt-1 px-1">
                      <span>{formatMessageTime(msg.created_at)}</span>
                      {isMine && (
                        <span>
                          {msg.is_read ? (
                            <CheckCheck className="w-3.5 h-3.5 text-indigo-600" />
                          ) : (
                            <Check className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* ATTACHMENT INPUT (EXPANDABLE) */}
        {showAttachmentInput && (
          <div className="px-4 py-2 bg-indigo-50/60 border-t border-indigo-100 flex items-center gap-2">
            <Paperclip className="w-4 h-4 text-indigo-600 shrink-0" />
            <input
              type="url"
              value={attachmentUrl}
              onChange={(e) => setAttachmentUrl(e.target.value)}
              placeholder="Paste attachment URL (photo, invoice, inspection report)..."
              className="flex-1 bg-white border border-indigo-200 rounded-xl px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={() => {
                setShowAttachmentInput(false);
                setAttachmentUrl("");
              }}
              className="text-xs text-slate-500 hover:text-slate-800"
            >
              Cancel
            </button>
          </div>
        )}

        {/* MESSAGE COMPOSER */}
        <form
          onSubmit={handleSendMessage}
          className="p-3 sm:p-4 bg-white border-t border-slate-200 flex items-end gap-2"
        >
          <button
            type="button"
            onClick={() => setShowAttachmentInput((prev) => !prev)}
            className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 border transition ${
              showAttachmentInput
                ? "bg-indigo-50 text-indigo-600 border-indigo-200"
                : "bg-slate-50 text-slate-500 hover:text-slate-800 border-slate-200"
            }`}
            title="Attach Link or Document"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Type your message to the workshop (Enter to send, Shift+Enter for newline)..."
            className="flex-1 max-h-32 min-h-[42px] bg-slate-50 border border-slate-200 rounded-2xl px-4 py-2.5 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white resize-none"
          />

          <button
            type="submit"
            disabled={(!newMessage.trim() && !attachmentUrl.trim()) || sending}
            className="w-10 h-10 rounded-2xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white flex items-center justify-center shrink-0 shadow-md shadow-indigo-200 transition"
          >
            {sending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
