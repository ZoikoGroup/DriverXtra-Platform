import { Suspense } from "react";
import RootClient from "./RootClient";

export const instant = false;

export default function RootPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-white">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-sm shadow">
              DX
            </div>
          </div>
        </div>
      }
    >
      <RootClient />
    </Suspense>
  );
}
