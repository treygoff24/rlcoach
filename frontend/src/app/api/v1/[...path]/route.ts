/**
 * API Proxy Route - Forwards all /api/v1/* requests to FastAPI backend
 *
 * This catch-all route:
 * 1. Extracts JWT from NextAuth session via auth()
 * 2. Forwards request to FastAPI (localhost:8000)
 * 3. Returns FastAPI response to client
 *
 * Benefits:
 * - Single origin (no CORS issues)
 * - JWT automatically attached from session.accessToken
 * - Token refresh handled by NextAuth
 */

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function proxyRequest(
  request: NextRequest,
  params: { path: string[] }
): Promise<NextResponse> {
  const path = params.path.join('/');
  const url = new URL(`/api/v1/${path}`, BACKEND_URL);

  // Preserve query parameters
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value);
  });

  // Get session using NextAuth v5 auth() function
  const session = await auth();

  // Build headers, forwarding relevant ones
  const headers = new Headers();

  // Forward content-type for POST/PUT/PATCH
  const contentType = request.headers.get('content-type');
  if (contentType) {
    headers.set('Content-Type', contentType);
  }

  // Add JWT authorization if user is authenticated
  // session.accessToken is created in the session callback in auth.ts
  if (session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`);
  }

  // Forward request body for methods that have one
  let body: BodyInit | null = null;
  if (['POST', 'PUT', 'PATCH'].includes(request.method)) {
    // Handle multipart form data (file uploads)
    if (contentType?.includes('multipart/form-data')) {
      body = await request.blob();
    } else {
      body = await request.text();
    }
  }

  try {
    const response = await fetch(url.toString(), {
      method: request.method,
      headers,
      body,
    });

    // Get response body
    const responseContentType = response.headers.get('content-type');
    let responseBody: string | Blob;

    if (responseContentType?.includes('application/json')) {
      responseBody = await response.text();
    } else {
      responseBody = await response.blob();
    }

    // Create response with same status and headers
    const proxyResponse = new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
    });

    // Forward relevant response headers
    const headersToForward = [
      'content-type',
      'content-disposition',
      'x-request-id',
      'retry-after',
    ];

    headersToForward.forEach((header) => {
      const value = response.headers.get(header);
      if (value) {
        proxyResponse.headers.set(header, value);
      }
    });

    return proxyResponse;
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { error: 'Backend service unavailable' },
      { status: 503 }
    );
  }
}

// Export handlers for all HTTP methods
export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params);
}
