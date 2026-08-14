import { type NextRequest, NextResponse } from 'next/server';
import { nanoid } from 'nanoid';

export function GET(request: NextRequest) {
  const origin = request.nextUrl.searchParams.get('origin');
  const city = request.nextUrl.searchParams.get('city');
  // Next's development proxy can normalize request.url to localhost even when the
  // browser opened 127.0.0.1. Building the redirect from the forwarded/Host header
  // keeps the RSC navigation same-origin and avoids a failed CORS preflight.
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host');
  const protocol = request.headers.get('x-forwarded-proto') ?? request.nextUrl.protocol.replace(':', '');
  const baseUrl = host ? `${protocol}://${host}` : request.nextUrl.origin;
  const target = new URL(`/plan/${nanoid(10)}/city`, baseUrl);
  if (origin) target.searchParams.set('origin', origin);
  if (city) target.searchParams.set('city', city);
  return NextResponse.redirect(target);
}
