import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get("google_access_token")?.value;
  
  if (!accessToken) {
    return NextResponse.json(
      { error: "Not authenticated with Google Drive" },
      { status: 401 }
    );
  }
  
  // Google Picker API requires a developer key (API key)
  const developerKey = process.env.GOOGLE_API_KEY;
  
  if (!developerKey) {
    return NextResponse.json(
      { error: "Google API key not configured" },
      { status: 500 }
    );
  }
  
  // Return the access token and developer key needed for the Picker API
  return NextResponse.json({
    accessToken,
    developerKey,
    appId: process.env.GOOGLE_APP_ID
  });
}