import { loadArena } from "@/lib/arena";

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return loadArena().funds.map((f) => ({ file: `${f.ticker}.json` }));
}

export async function GET(_request: Request, { params }: RouteContext<"/preview/data/funds/[file]">) {
  const { file } = await params;
  return Response.json(loadArena().bars[file.replace(/\.json$/, "")]);
}
