import { Sidebar, MobileBottomNav } from "@/components/dashboard/sidebar";
import { Topbar } from "@/components/dashboard/topbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#050505] text-white">
      <Sidebar />
      <div className="md:pl-[240px] transition-[padding] duration-300">
        <Topbar />
        <main className="px-4 sm:px-6 py-6 pb-24 md:pb-10 max-w-[1600px] mx-auto">
          {children}
        </main>
      </div>
      <MobileBottomNav />
    </div>
  );
}
