import { NextRequest, NextResponse } from "next/server";

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const REDIRECT_URI = process.env.NEXT_PUBLIC_BASE_URL + "/api/google/callback";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");

  // Get the state from cookie for verification
  const storedState = request.cookies.get("google_auth_state")?.value;

  // Verify state to prevent CSRF attacks
  if (!state || state !== storedState) {
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_BASE_URL}?error=invalid_state`
    );
  }

  // Handle error from Google
  if (error) {
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_BASE_URL}?error=${error}`
    );
  }

  if (!code) {
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_BASE_URL}?error=no_code`
    );
  }

  try {
    // Exchange code for tokens
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        code,
        client_id: GOOGLE_CLIENT_ID!,
        client_secret: GOOGLE_CLIENT_SECRET!,
        redirect_uri: REDIRECT_URI,
        grant_type: "authorization_code",
      }),
    });

    const tokenData = await tokenResponse.json();

    if (!tokenResponse.ok) {
      console.error("Token exchange error:", tokenData);
      return NextResponse.redirect(
        `${process.env.NEXT_PUBLIC_BASE_URL}?error=token_exchange_failed`
      );
    }

    // Redirect back to the app with success parameter
    const redirectResponse = NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_BASE_URL}?google_auth=success`
    );

    // Store tokens in secure HTTP-only cookies
    redirectResponse.cookies.set(
      "google_access_token",
      tokenData.access_token,
      {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        maxAge: tokenData.expires_in,
        path: "/",
      }
    );

    if (tokenData.refresh_token) {
      redirectResponse.cookies.set(
        "google_refresh_token",
        tokenData.refresh_token,
        {
          httpOnly: true,
          secure: process.env.NODE_ENV === "production",
          maxAge: 60 * 60 * 24 * 30, // 30 days
          path: "/",
        }
      );
    }

    return redirectResponse;
  } catch (error) {
    console.error("Error exchanging code for tokens:", error);
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_BASE_URL}?error=token_exchange_error`
    );
  }
}
