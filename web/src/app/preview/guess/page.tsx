import type { Metadata } from "next";
import { GuessGame } from "@/components/arena/GuessGame";
import { loadArena } from "@/lib/arena";

export const metadata: Metadata = { title: "Guess first" };

export default function GuessPage() {
  const { strategies, funds, tooClose } = loadArena();
  return (
    <>
      <div>
        <h1>Two strategies. One question.</h1>
        <p className="lede">
          Famous trading strategies, run on real prices with the same small fee. Guess which one ended with more money,
          then see what happened. Three rounds, about a minute.
        </p>
      </div>
      <GuessGame strategies={strategies} funds={funds} tooClose={tooClose} />
    </>
  );
}
