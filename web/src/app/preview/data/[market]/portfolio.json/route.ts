import { loadArena, type Market } from "@/lib/arena";
import { MARKET_IDS } from "@/lib/markets";

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return MARKET_IDS.map((market) => ({ market }));
}

export async function GET(_request: Request, { params }: RouteContext<"/preview/data/[market]/portfolio.json">) {
  const { market } = await params;
  return Response.json(loadArena().markets[market as Market].curve);
}
