import { Suspense } from "react";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <Suspense fallback={<div className="min-h-dvh bg-background" />}>
        <AppShell>{children}</AppShell>
      </Suspense>
    </RequireAuth>
  );
}

