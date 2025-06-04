"use client";

import { AppProvider } from "@/context/app-context";
import HomeContent from "@/components/home-content";

export default function Home() {
  return (
    <AppProvider>
      <HomeContent />
    </AppProvider>
  );
}
