import { loadArena } from "@/lib/arena";

export const dynamic = "force-static";

export function GET() {
  return Response.json(loadArena().curve);
}
