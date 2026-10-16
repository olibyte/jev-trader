import { loadArena, type Market } from "@/lib/arena";
import { MARKET_IDS } from "@/lib/markets";

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  const { funds } = loadArena();
  return MARKET_IDS.flatMap((market) => funds.map((f) => ({ market, file: `${f.ticker}.json` })));
}

export async function GET(_request: Request, { params }: RouteContext<"/preview/data/[market]/funds/[file]">) {
  const { market, file } = await params;
  return Response.json(loadArena().markets[market as Market].bars[file.replace(/\.json$/, "")]);
}
