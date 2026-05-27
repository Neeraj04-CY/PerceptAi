import { Sidebar, MobileBottomNav } from "@/components/dashboard/sidebar";
import { Topbar } from "@/components/dashboard/topbar";
import { DashboardContainer } from "@/components/ui/dashboard-container";
import { CommandPaletteProvider } from "@/components/dashboard/command-palette-provider";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <CommandPaletteProvider>
      <div className="min-h-screen bg-[#050505] text-white">
        <Sidebar />
        <div className="md:pl-[240px] transition-[padding] duration-300">
          <Topbar />
          <main className="pb-24 md:pb-10">
            <DashboardContainer>{children}</DashboardContainer>
          </main>
        </div>
        <MobileBottomNav />
      </div>
    </CommandPaletteProvider>
  );
}
