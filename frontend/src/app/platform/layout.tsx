"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";

export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, isLoading, isInitialized } = useAuth();

  useEffect(() => {
    // Only redirect once initialization has finished, request is not loading, and user is unauthenticated
    if (isInitialized && !isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isInitialized, isLoading, isAuthenticated, router]);

  // While restoring session or during initial auth bootstrap, show the verification state
  if (!isInitialized || isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
          <span>Verifying DriverXtra session...</span>
        </div>
      </div>
    );
  }

  // If initialized, not loading, but unauthenticated, show redirect state while router.replace executes
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
          <span>Redirecting to authentication...</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
