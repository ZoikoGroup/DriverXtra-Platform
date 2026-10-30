"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";

export default function RootPage() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuth();

  useEffect(() => {
    if (!isInitialized) return;
    if (isAuthenticated) {
      router.replace("/platform");
    } else {
      router.replace("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-white">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-sm shadow">
          DX
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
          <span>Loading DriverXtra...</span>
        </div>
      </div>
    </div>
  );
}
