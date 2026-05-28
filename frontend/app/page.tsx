import { Navbar } from "@/components/landing/navbar";
import { Hero } from "@/components/landing/hero";
import { Ticker } from "@/components/landing/ticker";
import { HowItWorks } from "@/components/landing/how-it-works";
import { ApiShowcase } from "@/components/landing/api-showcase";
import { UseCases } from "@/components/landing/use-cases";
import { Comparison } from "@/components/landing/comparison";
import { CtaBlock } from "@/components/landing/cta-block";
import { Pricing } from "@/components/landing/pricing";
import { Footer } from "@/components/landing/footer";

export default function Page() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <Navbar />
      <Hero />
      <Ticker />
      <HowItWorks />
      <ApiShowcase />
      <UseCases />
      <Comparison />
      <CtaBlock />
      <Pricing />
      <Footer />
    </main>
  );
}
