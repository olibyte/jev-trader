"""Throwaway: the block draws evaluate.block_bootstrap makes for 98 blocks, seed 0, 2000 reps."""
import json, sys
import numpy as np
rng = np.random.default_rng(0)
count = 98
draws = [rng.integers(count, size=count).tolist() for _ in range(2000)]
open(sys.argv[1], "w").write(json.dumps(draws))
print(len(bytes(np.array(draws, dtype=np.uint8))), "bytes as uint8")
