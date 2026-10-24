"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, X, CheckCheck, AlertCircle, RefreshCw } from "lucide-react";
import { api, ApiError, PlatformNotification } from "@/lib/api/client";

const UNREAD_POLL_INTERVAL_MS = 60_000;

/**
 * Polls the unread notification count every 60s while the tab is visible.
 * Refreshes immediately when the tab becomes visible again; clears timers on unmount.
 */
export function useNotificationUnreadCount(enabled: boolean) {
  const [unreadCount, setUnreadCount] = useState(0);

  const refresh = useCallback(async () => {
    try {
      setUnreadCount(await api.notifications.getUnreadCount());
    } catch {
      // Keep the last known count; transient failures should not disrupt the platform shell.
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const poll = async () => {
      if (cancelled || (typeof document !== "undefined" && document.hidden)) return;
      await refresh();
    };

    void poll();
    const intervalId = window.setInterval(poll, UNREAD_POLL_INTERVAL_MS);
    const onVisibilityChange = () => {
      if (!document.hidden) void poll();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, refresh]);

  return { unreadCount: enabled ? unreadCount : 0, setUnreadCount, refreshUnreadCount: refresh };
}

function formatRelativeTime(iso: string): string {
  const diffSeconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (Number.isNaN(diffSeconds)) return "";
  if (diffSeconds < 60) return "just now";
  const minutes = Math.floor(diffSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

interface NotificationDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Called after read-state changes so the TopBar badge stays in sync. */
  onUnreadCountChange: () => void;
  /** Navigates within the single-page platform shell (links of the form /platform?tab=...). */
  onNavigateTab: (tab: string) => void;
}

export default function NotificationDrawer(props: NotificationDrawerProps) {
  // The panel mounts only while open, so each opening starts from a fresh loading state.
  if (!props.open) return null;
  return <NotificationDrawerPanel {...props} />;
}

function NotificationDrawerPanel({ onClose, onUnreadCountChange, onNavigateTab }: NotificationDrawerProps) {
  const router = useRouter();
  const [notifications, setNotifications] = useState<PlatformNotification[]>([]);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const fetchPage = useCallback(async (page: number) => {
    const requestId = ++requestIdRef.current;
    try {
      const data = await api.notifications.list({ page });
      if (requestId !== requestIdRef.current) return;
      setNotifications((prev) => (page === 1 ? data.results : [...prev, ...data.results]));
      setNextPage(data.next ? page + 1 : null);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof ApiError ? err.message : "Could not load notifications.");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) void fetchPage(1);
    });
    return () => {
      ignore = true;
      requestIdRef.current += 1; // discard any in-flight response after unmount
    };
  }, [fetchPage]);

  const reload = () => {
    setLoading(true);
    setError(null);
    void fetchPage(1);
  };

  const loadMore = (page: number) => {
    setLoadingMore(true);
    setError(null);
    void fetchPage(page);
  };

  const markRead = async (notification: PlatformNotification) => {
    if (notification.is_read) return;
    try {
      const updated = await api.notifications.markRead(notification.id);
      setNotifications((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
      onUnreadCountChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not mark notification as read.");
    }
  };

  const markAllRead = async () => {
    setMarkingAll(true);
    setError(null);
    try {
      await api.notifications.markAllRead();
      const now = new Date().toISOString();
      setNotifications((prev) => prev.map((n) => (n.is_read ? n : { ...n, is_read: true, read_at: now })));
      onUnreadCountChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not mark notifications as read.");
    } finally {
      setMarkingAll(false);
    }
  };

  const openNotification = async (notification: PlatformNotification) => {
    await markRead(notification);
    if (!notification.link) return;
    const url = new URL(notification.link, window.location.origin);
    const tab = url.searchParams.get("tab");
    if (url.origin === window.location.origin && url.pathname === "/platform" && tab) {
      onNavigateTab(tab);
      onClose();
    } else if (url.origin === window.location.origin) {
      onClose();
      router.push(`${url.pathname}${url.search}`);
    }
  };

  const hasUnread = notifications.some((n) => !n.is_read);

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end" onClick={onClose}>
      <div
        className="bg-white w-full max-w-sm h-full p-6 shadow-2xl flex flex-col border-l border-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-amber-500" />
            <h4 className="text-sm font-black text-slate-950">Notifications</h4>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={markAllRead}
              disabled={!hasUnread || markingAll}
              className="flex items-center gap-1 text-[11px] font-bold text-slate-600 hover:text-slate-950 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              {markingAll ? "Marking..." : "Mark all read"}
            </button>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close notifications">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto mt-4 space-y-3 text-xs">
          {error && (
            <div className="p-3 bg-rose-50 rounded-xl border border-rose-200 text-rose-800 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p>{error}</p>
                <button onClick={reload} className="mt-1 font-bold underline">
                  Try again
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-slate-500">
              <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading notifications...</span>
            </div>
          ) : notifications.length === 0 && !error ? (
            <div className="py-10 text-center text-slate-500">
              <Bell className="w-6 h-6 mx-auto mb-2 text-slate-300" />
              <p className="font-bold text-slate-700">You&apos;re all caught up</p>
              <p className="mt-1">Updates on your applications, listings and enquiries will appear here.</p>
            </div>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => openNotification(n)}
                className={`w-full text-left p-3 rounded-xl border transition-colors ${
                  n.is_read
                    ? "bg-white border-slate-200 hover:bg-slate-50"
                    : "bg-amber-50 border-amber-200 hover:bg-amber-100"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className={`flex items-center gap-1.5 ${n.is_read ? "font-semibold text-slate-700" : "font-bold text-slate-950"}`}>
                    {!n.is_read && <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" aria-label="Unread" />}
                    {n.title}
                  </span>
                  <span className="text-[10px] text-slate-400 shrink-0">{formatRelativeTime(n.created_at)}</span>
                </div>
                {n.message && <p className="text-slate-600 mt-1">{n.message}</p>}
              </button>
            ))
          )}

          {nextPage && !loading && (
            <button
              onClick={() => loadMore(nextPage)}
              disabled={loadingMore}
              className="w-full flex items-center justify-center gap-1 py-2 text-[11px] font-bold text-slate-600 hover:text-slate-950 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingMore ? "animate-spin" : ""}`} />
              {loadingMore ? "Loading..." : "Load older notifications"}
            </button>
          )}
        </div>

        <button onClick={onClose} className="mt-4 w-full h-10 bg-slate-950 text-white text-xs font-bold rounded-xl">
          Close Notifications
        </button>
      </div>
    </div>
  );
}
