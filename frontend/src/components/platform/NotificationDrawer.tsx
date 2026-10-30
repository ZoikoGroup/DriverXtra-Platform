"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell,
  X,
  CheckCheck,
  AlertCircle,
  RefreshCw,
  Package,
  Truck,
  RotateCcw,
  CreditCard,
  Scale,
  Star,
  ShieldCheck,
  Building2,
  Trash2,
} from "lucide-react";
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

function getNotificationCategoryMeta(eventType: string) {
  if (eventType.startsWith("marketplace.order.")) {
    return {
      icon: Package,
      label: "ORDER",
      badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
    };
  }
  if (eventType.startsWith("marketplace.shipment.")) {
    return {
      icon: Truck,
      label: "SHIPMENT",
      badgeClass: "bg-indigo-50 text-indigo-700 border-indigo-200",
    };
  }
  if (eventType.startsWith("marketplace.return.")) {
    return {
      icon: RotateCcw,
      label: "RETURN",
      badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  if (eventType.startsWith("marketplace.refund.")) {
    return {
      icon: CreditCard,
      label: "REFUND",
      badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
    };
  }
  if (eventType.startsWith("marketplace.dispute.")) {
    return {
      icon: Scale,
      label: "DISPUTE",
      badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    };
  }
  if (eventType.includes("review")) {
    return {
      icon: Star,
      label: "REVIEW",
      badgeClass: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  if (eventType.startsWith("org.")) {
    return {
      icon: Building2,
      label: "TEAM",
      badgeClass: "bg-teal-50 text-teal-700 border-teal-200",
    };
  }
  if (eventType.startsWith("seller.") || eventType.startsWith("listing.") || eventType.startsWith("catalogue.")) {
    return {
      icon: ShieldCheck,
      label: "STATUS",
      badgeClass: "bg-purple-50 text-purple-700 border-purple-200",
    };
  }
  return {
    icon: Bell,
    label: "NOTICE",
    badgeClass: "bg-slate-50 text-slate-700 border-slate-200",
  };
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
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const fetchPage = useCallback(async (page: number, unreadFilter: boolean) => {
    const requestId = ++requestIdRef.current;
    try {
      const data = await api.notifications.list({ page, unread: unreadFilter || undefined });
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
    setLoading(true);
    setError(null);
    Promise.resolve().then(() => {
      if (!ignore) void fetchPage(1, unreadOnly);
    });
    return () => {
      ignore = true;
      requestIdRef.current += 1;
    };
  }, [fetchPage, unreadOnly]);

  const reload = () => {
    setLoading(true);
    setError(null);
    void fetchPage(1, unreadOnly);
  };

  const loadMore = (page: number) => {
    setLoadingMore(true);
    setError(null);
    void fetchPage(page, unreadOnly);
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

  const deleteNotification = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.notifications.delete(id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      onUnreadCountChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete notification.");
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
        className="bg-white w-full max-w-sm sm:max-w-md h-full p-5 sm:p-6 shadow-2xl flex flex-col border-l border-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-600">
              <Bell className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-black text-slate-950">Notifications</h4>
              <p className="text-[10px] text-slate-400">Platform workflow updates</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <button
              onClick={markAllRead}
              disabled={!hasUnread || markingAll}
              className="flex items-center gap-1 text-[11px] font-bold text-slate-600 hover:text-slate-950 disabled:opacity-40 disabled:cursor-not-allowed bg-slate-100 hover:bg-slate-200 px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              {markingAll ? "Marking..." : "Mark all read"}
            </button>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 flex items-center justify-center transition-colors"
              aria-label="Close notifications"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 pt-3 pb-2 border-b border-slate-100">
          <button
            onClick={() => setUnreadOnly(false)}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
              !unreadOnly ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setUnreadOnly(true)}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors flex items-center gap-1.5 ${
              unreadOnly ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Unread
            {hasUnread && <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />}
          </button>
        </div>

        {/* Notifications Scrollable List */}
        <div className="flex-1 overflow-y-auto mt-3 space-y-2.5 text-xs pr-1">
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
            <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
              <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading notifications...</span>
            </div>
          ) : notifications.length === 0 && !error ? (
            <div className="py-12 text-center text-slate-500">
              <Bell className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p className="font-bold text-slate-700">
                {unreadOnly ? "No unread notifications" : "You're all caught up"}
              </p>
              <p className="mt-1 text-slate-400 text-[11px]">
                {unreadOnly
                  ? "Switch to 'All' to review earlier notifications."
                  : "Updates on orders, shipments, returns, and reviews will appear here."}
              </p>
            </div>
          ) : (
            notifications.map((n) => {
              const meta = getNotificationCategoryMeta(n.event_type);
              const CategoryIcon = meta.icon;
              return (
                <div
                  key={n.id}
                  onClick={() => openNotification(n)}
                  className={`group relative w-full text-left p-3 rounded-xl border transition-all cursor-pointer ${
                    n.is_read
                      ? "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                      : "bg-amber-50/80 border-amber-200 hover:bg-amber-100/70 shadow-sm"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <div className="w-6 h-6 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0">
                        <CategoryIcon className="w-3.5 h-3.5 text-slate-700" />
                      </div>
                      <span
                        className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded border shrink-0 ${meta.badgeClass}`}
                      >
                        {meta.label}
                      </span>
                      <span
                        className={`truncate ${
                          n.is_read ? "font-semibold text-slate-800" : "font-black text-slate-950"
                        }`}
                      >
                        {n.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-[10px] text-slate-400">{formatRelativeTime(n.created_at)}</span>
                      <button
                        onClick={(e) => deleteNotification(e, n.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-400 hover:text-rose-600 rounded"
                        title="Dismiss notification"
                        aria-label="Dismiss notification"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>

                  {n.message && (
                    <p className="text-slate-600 text-[11px] mt-1.5 pl-7 leading-relaxed line-clamp-2">
                      {n.message}
                    </p>
                  )}
                </div>
              );
            })
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

        <button
          onClick={onClose}
          className="mt-4 w-full h-10 bg-slate-950 hover:bg-slate-900 text-white text-xs font-bold rounded-xl transition-colors shrink-0"
        >
          Close Notifications
        </button>
      </div>
    </div>
  );
}
