import { NextRequest, NextResponse } from "next/server";

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get("google_refresh_token")?.value;

  if (!refreshToken) {
    return NextResponse.json(
      { error: "No refresh token available" },
      { status: 401 }
    );
  }

  try {
    // Exchange refresh token for new access token
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        client_id: GOOGLE_CLIENT_ID!,
        client_secret: GOOGLE_CLIENT_SECRET!,
        refresh_token: refreshToken,
        grant_type: "refresh_token",
      }),
    });

    const tokenData = await tokenResponse.json();

    if (!tokenResponse.ok) {
      console.error("Token refresh error:", tokenData);
      const response = NextResponse.json(
        { error: "Failed to refresh token" },
        { status: 401 }
      );
      // Clear both tokens if refresh fails
      response.cookies.delete("google_access_token");
      response.cookies.delete("google_refresh_token");
      return response;
    }

    // Create response with new access token
    const response = NextResponse.json({ success: true });

    // Set new access token in cookie
    response.cookies.set("google_access_token", tokenData.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      maxAge: tokenData.expires_in,
      path: "/",
    });

    // If a new refresh token is provided (rare), update it
    if (tokenData.refresh_token) {
      response.cookies.set("google_refresh_token", tokenData.refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        maxAge: 60 * 60 * 24 * 30, // 30 days
        path: "/",
      });
    }

    return response;
  } catch (error) {
    console.error("Error refreshing token:", error);
    return NextResponse.json(
      { error: "Failed to refresh token" },
      { status: 500 }
    );
  }
}
