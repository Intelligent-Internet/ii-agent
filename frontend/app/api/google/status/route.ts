import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get("google_access_token")?.value;
  
  if (!accessToken) {
    return NextResponse.json({ authenticated: false });
  }
  
  try {
    // Validate the token by making a request to Google's tokeninfo endpoint
    const response = await fetch(
      `https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=${accessToken}`
    );
    
    if (!response.ok) {
      // Token is invalid or expired
      const res = NextResponse.json({ authenticated: false });
      res.cookies.delete("google_access_token");
      return res;
    }
    
    return NextResponse.json({ authenticated: true });
  } catch (error) {
    console.error("Error validating token:", error);
    return NextResponse.json({ authenticated: false });
  }
}