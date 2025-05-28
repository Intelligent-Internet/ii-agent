import { NextResponse } from "next/server";

// Server-side Google OAuth configuration
const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const REDIRECT_URI = process.env.NEXT_PUBLIC_BASE_URL + "/api/google/callback";
const SCOPES = ["https://www.googleapis.com/auth/drive.readonly"];

export async function GET() {
  // Generate a random state value for CSRF protection
  const state = Math.random().toString(36).substring(2);

  // Store state in a cookie for verification when the callback is received
  const response = NextResponse.redirect(
    `https://accounts.google.com/o/oauth2/v2/auth?client_id=${GOOGLE_CLIENT_ID}&redirect_uri=${encodeURIComponent(
      REDIRECT_URI
    )}&response_type=code&scope=${encodeURIComponent(
      SCOPES.join(" ")
    )}&access_type=offline&state=${state}&prompt=consent`
  );

  // Set state cookie for verification
  response.cookies.set("google_auth_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 10, // 10 minutes
    path: "/",
  });

  return response;
}
