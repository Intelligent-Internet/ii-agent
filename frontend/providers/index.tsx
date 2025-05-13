"use client";

import { AppProgressBar as ProgressBar } from "next-nprogress-bar";
import { Toaster } from "@/components/ui/sonner";

import "../app/github-markdown.css";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      forcedTheme="dark"
      themes={["dark"]}
      disableTransitionOnChange
    >
      <TooltipProvider>
        <ProgressBar
          height="2px"
          color="#BAE9F4"
          options={{ showSpinner: false }}
          shallowRouting
        />
        {children}
      </TooltipProvider>
      <Toaster richColors />
    </ThemeProvider>
  );
}
