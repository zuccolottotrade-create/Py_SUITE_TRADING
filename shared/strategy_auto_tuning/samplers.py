from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable
import random

from .space import SearchSpace


@dataclass(frozen=True)
class TrialSample:
    trial_id: int
    params: Dict[str, Any]


@dataclass
class RandomSearchSampler:
    seed: int = 42

    def iter_trials(self, space: SearchSpace, n_trials: int) -> Iterable[TrialSample]:
        """
        Deterministic per-trial sampling: seed is mixed with trial_id.
        trial_id starts at 1 to match trial_0001.xlsx naming in engine.
        """
        for tid in range(1, int(n_trials) + 1):
            rng = random.Random(self.seed + int(tid))
            params: Dict[str, Any] = {}
            for p in space.params:
                params[p.param_name] = rng.choice(list(p.candidate_values))
            yield TrialSample(trial_id=tid, params=params)