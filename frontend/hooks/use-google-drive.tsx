import { useState, useEffect } from "react";
import { toast } from "sonner";

export function useGoogleDrive() {
  const [isGoogleDriveConnected, setIsGoogleDriveConnected] = useState(false);
  const [googlePickerLoaded, setGooglePickerLoaded] = useState(false);
  const [googlePickerApiLoaded, setGooglePickerApiLoaded] = useState(false);

  useEffect(() => {
    const checkGoogleAuthStatus = async () => {
      try {
        const response = await fetch("/api/google/status");
        const data = await response.json();

        if (!data.authenticated) {
          const refreshResponse = await fetch("/api/google/refresh", {
            method: "POST",
          });

          if (refreshResponse.ok) {
            const retryResponse = await fetch("/api/google/status");
            const retryData = await retryResponse.json();
            setIsGoogleDriveConnected(retryData.authenticated);
            return;
          }
        }
        setIsGoogleDriveConnected(data.authenticated);
      } catch (error) {
        console.error("Error checking Google auth status:", error);
        setIsGoogleDriveConnected(false);
      }
    };

    checkGoogleAuthStatus();

    // Check auth status when URL contains google_auth=success
    const handleAuthSuccess = () => {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get("google_auth") === "success") {
        const newUrl = window.location.pathname;
        window.history.replaceState({}, document.title, newUrl);
      }
    };

    handleAuthSuccess();
  }, []);

  useEffect(() => {
    if (!googlePickerLoaded) {
      const script = document.createElement("script");
      script.src = "https://apis.google.com/js/api.js";
      script.onload = () => {
        window.gapi.load("picker", () => {
          setGooglePickerApiLoaded(true);
        });
      };
      document.body.appendChild(script);
      setGooglePickerLoaded(true);
    }
  }, [googlePickerLoaded]);

  const handleGoogleDriveAuth = async (): Promise<boolean> => {
    try {
      window.location.href = "/api/google/auth";
      return false;
    } catch {
      toast.error("Failed to authenticate with Google Drive");
      return false;
    }
  };

  return {
    isGoogleDriveConnected,
    googlePickerApiLoaded,
    setIsGoogleDriveConnected,
    handleGoogleDriveAuth,
  };
}
