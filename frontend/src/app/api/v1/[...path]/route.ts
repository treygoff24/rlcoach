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

type RouteParams = { path: string[] };
type RouteContext = { params: Promise<RouteParams> };

async function proxyRequest(
  request: NextRequest,
  params: RouteParams
): Promise<NextResponse> {
  const path = params.path.join('/');
  const url = new URL(`/api/v1/${path}`, BACKEND_URL);

  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const session = await auth();

  const headers = new Headers();

  const contentType = request.headers.get('content-type');
  if (contentType) {
    headers.set('Content-Type', contentType);
  }

  // session.accessToken is created in the session callback in auth.ts
  if (session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`);
  }

  let body: BodyInit | null = null;
  if (['POST', 'PUT', 'PATCH'].includes(request.method)) {
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

    const responseContentType = response.headers.get('content-type');
    let responseBody: string | Blob;

    if (responseContentType?.includes('application/json')) {
      responseBody = await response.text();
    } else {
      responseBody = await response.blob();
    }

    const proxyResponse = new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
    });

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

async function proxyRoute(request: NextRequest, { params }: RouteContext) {
  return proxyRequest(request, await params);
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyRoute(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyRoute(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return proxyRoute(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxyRoute(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxyRoute(request, context);
}
