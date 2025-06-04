import { useState, useEffect } from 'react';
import Cookies from 'js-cookie';
import { v4 as uuidv4 } from 'uuid';

export function useDeviceId() {
  const [deviceId, setDeviceId] = useState("");

  useEffect(() => {
    // Check if device ID exists in cookies
    let existingDeviceId = Cookies.get("device_id");

    // If no device ID exists, generate a new one and save it
    if (!existingDeviceId) {
      existingDeviceId = uuidv4();

      // Set cookie with a long expiration (1 year)
      Cookies.set("device_id", existingDeviceId, {
        expires: 365,
        sameSite: "strict",
        secure: window.location.protocol === "https:",
      });

      console.log("Generated new device ID:", existingDeviceId);
    } else {
      console.log("Using existing device ID:", existingDeviceId);
    }

    // Set the device ID in state
    setDeviceId(existingDeviceId);
  }, []);

  return { deviceId };
}