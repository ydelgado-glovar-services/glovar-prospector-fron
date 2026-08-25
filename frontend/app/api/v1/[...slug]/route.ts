import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/utils/supabase/server'

type RouteContext = { params: Promise<{ slug?: string[] }> | { slug?: string[] } }

// Reusable handler for all methods
async function handleRequest(request: NextRequest, context: RouteContext) {
  try {
    const supabase = await createClient()

    // Validate the session and get the user
    const { data: { user }, error: authError } = await supabase.auth.getUser()

    if (authError || !user) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      )
    }

    // Safely unwrap the params object (handles both Promise and direct object)
    const resolvedParams = await context.params;
    const slugArray = resolvedParams?.slug || [];
    const path = slugArray.join('/');

    // 1. URL Sanitization
    const backendEnv = process.env.PYTHON_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    const baseUrl = backendEnv.replace(/\/$/, '');
    const targetUrl = `${baseUrl}/api/v1/${path}${request.nextUrl.search}`;

    // 2. Header Sanitization (CRITICAL)
    // We explicitly avoid cloning request.headers to prevent passing Host, Connection, or Content-Length
    const headers = new Headers();
    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
      headers.set('Authorization', authHeader);
    }
    headers.set('X-User-Id', user.id);
    
    // Inject secure backend authorization key
    const backendApiKey = process.env.GLOVAR_BACKEND_API_KEY;
    if (backendApiKey) {
      headers.set('x-api-key', backendApiKey);
    }
    
    const requestInit: RequestInit = {
      method: request.method,
      headers: headers,
    }
    
    // 3. Body Handling
    if (['POST', 'PUT', 'PATCH'].includes(request.method)) {
      headers.set('Content-Type', 'application/json');
      const body = await request.json().catch(() => ({}));
      body.user_id = user.id;
      requestInit.body = JSON.stringify(body);
    }

    // 4. Forensic Logging
    console.log(`[PROXY ${request.method}] Target URL:`, targetUrl);
    console.log(`[PROXY ${request.method}] Headers injected:`, { "X-User-Id": user.id });

    const response = await fetch(targetUrl, requestInit)

    // Directly stream the backend response back to the client
    return new Response(response.body, {
      status: response.status,
      headers: response.headers
    });

  } catch (err: any) {
    // 5. Error Tracing
    console.error(`[PROXY FETCH ERROR]:`, err.message, err.cause);
    return NextResponse.json(
      { error: 'Internal Server Error', details: err.message },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return handleRequest(request, context)
}

export async function POST(request: NextRequest, context: RouteContext) {
  return handleRequest(request, context)
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return handleRequest(request, context)
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return handleRequest(request, context)
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return handleRequest(request, context)
}
