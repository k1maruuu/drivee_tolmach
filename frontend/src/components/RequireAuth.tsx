"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isLoading) return;
    if (!token) {
      const next = pathname && pathname !== "/auth" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/auth${next}`);
    }
  }, [isLoading, token, router, pathname]);

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background">
        <div className="flex items-center gap-3 text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-border2 border-t-accent" />
          Загрузка…
        </div>
      </div>
    );
  }

  if (!token) return null;
  return children;
}

