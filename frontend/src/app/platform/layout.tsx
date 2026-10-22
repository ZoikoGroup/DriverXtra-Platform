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

  return <>{children}</>;
}
