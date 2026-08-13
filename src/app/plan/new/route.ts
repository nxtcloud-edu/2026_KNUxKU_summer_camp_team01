import { type NextRequest, NextResponse } from 'next/server';
import { nanoid } from 'nanoid';

export function GET(request: NextRequest) {
  const origin = request.nextUrl.searchParams.get('origin');
  const city = request.nextUrl.searchParams.get('city');
  const target = new URL(`/plan/${nanoid(10)}/city`, request.url);
  if (origin) target.searchParams.set('origin', origin);
  if (city) target.searchParams.set('city', city);
  return NextResponse.redirect(target);
}
