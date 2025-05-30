import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get("google_access_token")?.value;
  
  if (!accessToken) {
    return NextResponse.json(
      { error: "Not authenticated with Google Drive" },
      { status: 401 }
    );
  }
  
  const searchParams = request.nextUrl.searchParams;
  const query = searchParams.get("q") || "mimeType='image/jpeg' or mimeType='image/png' or mimeType='application/pdf' or mimeType='text/plain' or mimeType='application/json'";
  const pageToken = searchParams.get("pageToken") || "";
  
  try {
    const response = await fetch(
      `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(
        query
      )}&fields=nextPageToken,files(id,name,mimeType,thumbnailLink)&pageSize=50${
        pageToken ? `&pageToken=${pageToken}` : ""
      }`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );
    
    if (!response.ok) {
      const errorData = await response.json();
      console.error("Google Drive API error:", errorData);
      
      // If token is invalid, clear it
      if (response.status === 401) {
        const res = NextResponse.json(
          { error: "Google Drive authentication expired" },
          { status: 401 }
        );
        res.cookies.delete("google_access_token");
        return res;
      }
      
      return NextResponse.json(
        { error: "Failed to fetch files from Google Drive" },
        { status: response.status }
      );
    }
    
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Error fetching files from Google Drive:", error);
    return NextResponse.json(
      { error: "Failed to fetch files from Google Drive" },
      { status: 500 }
    );
  }
}