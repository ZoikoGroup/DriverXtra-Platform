import { Suspense } from "react";
import LoginClient from "./LoginClient";

export const instant = false;

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center text-white">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg shadow-amber-400/20">
              DX
            </div>
          </div>
        </div>
      }
    >
      <LoginClient />
    </Suspense>
  );
}
