export const dynamic = 'force-dynamic';

export function GET() {
  return Response.json({
    ok: true,
    service: 'voyagent',
    version: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? 'local',
    timestamp: new Date().toISOString(),
  }, { headers: { 'Cache-Control': 'no-store' } });
}
