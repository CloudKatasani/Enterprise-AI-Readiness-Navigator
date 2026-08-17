"""Benchmarking against anonymised peer cohorts.

A percentile is only meaningful next to its cohort definition, so every result
returned here carries the industry, size band, platform mix and cohort size that
produced it -- the Portal renders them together (blueprint S16).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.config import SEED_DIR
from eairn.models import CohortStat, Tenant

COHORT_FILE = SEED_DIR / "cohorts.yaml"
FALLBACK_COHORT = "cross_industry.any.any"


@dataclass
class BenchmarkResult:
    metric_key: str
    score: float
    percentile: float
    cohort_key: str
    cohort_definition: dict = field(default_factory=dict)
    distribution: dict = field(default_factory=dict)
    reliable: bool = True

    def as_dict(self) -> dict:
        return {
            "metric_key": self.metric_key,
            "score": round(self.score, 2),
            "percentile": round(self.percentile, 1),
            "cohort_key": self.cohort_key,
            "cohort_definition": self.cohort_definition,
            "distribution": self.distribution,
            "reliable": self.reliable,
        }


def install_cohorts(session: Session, *, path: Path | None = None) -> int:
    """Load the seed cohort distributions. Idempotent."""
    file_path = path or COHORT_FILE
    with file_path.open("r", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)

    existing = {
        (row.cohort_key, row.metric_key): row
        for row in session.scalars(select(CohortStat))
    }
    written = 0
    for cohort in spec.get("cohorts", []):
        for metric_key, points in cohort.get("metrics", {}).items():
            row = existing.get((cohort["key"], metric_key))
            if row is None:
                row = CohortStat(cohort_key=cohort["key"], metric_key=metric_key)
                session.add(row)
            row.industry = cohort["industry"]
            row.size_band = cohort["size_band"]
            row.platform_mix = cohort.get("platform_mix", "any")
            row.metric_scope = "index" if metric_key in {"ARI", "RRI"} else (
                "composite" if metric_key == "composite" else "pillar"
            )
            row.n = int(cohort.get("n", 0))
            row.p25 = float(points["p25"])
            row.p50 = float(points["p50"])
            row.p75 = float(points["p75"])
            row.p90 = float(points["p90"])
            written += 1
    session.flush()
    return written


def minimum_cohort_size(path: Path | None = None) -> int:
    with (path or COHORT_FILE).open("r", encoding="utf-8") as fh:
        return int(yaml.safe_load(fh).get("minimum_cohort_size", 15))


def cohort_key_for(tenant: Tenant) -> str:
    return f"{tenant.industry}.{tenant.size_band}.any"


def percentile_of(score: float, stat: CohortStat) -> float:
    """Piecewise-linear percentile from the stored quartile summary.

    The summary is deliberately coarse -- it is what an anonymised cohort can
    publish without leaking a member's position -- so the estimate is clamped
    to [1, 99] rather than implying more precision than the data carries.
    """
    points = [(0.0, 0.0), (stat.p25, 25.0), (stat.p50, 50.0), (stat.p75, 75.0), (stat.p90, 90.0), (100.0, 100.0)]
    for (low_score, low_pct), (high_score, high_pct) in zip(points, points[1:]):
        if score <= high_score:
            span = high_score - low_score
            if span <= 0:
                return high_pct
            ratio = (score - low_score) / span
            return max(1.0, min(99.0, low_pct + ratio * (high_pct - low_pct)))
    return 99.0


def benchmark(
    session: Session, tenant: Tenant, metrics: dict[str, float], *, keys: Iterable[str] | None = None
) -> list[BenchmarkResult]:
    """Compare a tenant's scores to its peer cohort, falling back cross-industry."""
    minimum = minimum_cohort_size()
    preferred = cohort_key_for(tenant)
    results: list[BenchmarkResult] = []
    for metric_key, score in metrics.items():
        if score is None:
            continue
        if keys is not None and metric_key not in set(keys):
            continue
        stat = session.scalar(
            select(CohortStat).where(
                CohortStat.cohort_key == preferred, CohortStat.metric_key == metric_key
            )
        )
        if stat is None or stat.n < minimum:
            stat = session.scalar(
                select(CohortStat).where(
                    CohortStat.cohort_key == FALLBACK_COHORT, CohortStat.metric_key == metric_key
                )
            )
        if stat is None:
            continue
        results.append(
            BenchmarkResult(
                metric_key=metric_key,
                score=score,
                percentile=percentile_of(score, stat),
                cohort_key=stat.cohort_key,
                cohort_definition={
                    "industry": stat.industry,
                    "size_band": stat.size_band,
                    "platform_mix": stat.platform_mix,
                    "n": stat.n,
                },
                distribution={"p25": stat.p25, "p50": stat.p50, "p75": stat.p75, "p90": stat.p90},
                reliable=stat.n >= minimum,
            )
        )
    return results
