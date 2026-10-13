import Link from "next/link";

export default function PreviewIndex() {
  return (
    <>
      <h1>Two first screens to compare</h1>
      <p className="lede">Both use the real results for four strategies on 13 US stock funds from 2008 to 2026.</p>
      <div className="index-links">
        <Link className="arena-card" href="/preview/pick-two/">
          <h2>Pick two</h2>
          <p className="muted">Choose two strategies and see what $1,000 became in each.</p>
        </Link>
        <Link className="arena-card" href="/preview/guess/">
          <h2>Guess first</h2>
          <p className="muted">Guess which one ended with more money, then see the answer.</p>
        </Link>
      </div>
    </>
  );
}
