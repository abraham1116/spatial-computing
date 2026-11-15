"""Cost model. Every price is an ASSUMPTION with a stated basis; override via CostModel(...).

Local cost is derived from MEASURED time/energy. Remote/cloud cost is an ESTIMATE:
no cloud machine was rented for these experiments, so cloud rows are labelled
`estimated=True` and assume the measured local runtime scaled by `speed_ratio`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CloudOffer:
    name: str
    usd_per_hour: float
    vcpus: int
    gpu: str | None
    basis: str            # where the number comes from; to be re-checked before any business use


# List prices recalled from public price pages (us-east-1 on-demand). NOT re-verified today.
OFFERS = {
    "aws_c7i_large": CloudOffer("AWS c7i.large", 0.0893, 2, None, "AWS on-demand list price, unverified"),
    "aws_c7i_4xlarge": CloudOffer("AWS c7i.4xlarge", 0.714, 16, None, "AWS on-demand list price, unverified"),
    "aws_g4dn_xlarge": CloudOffer("AWS g4dn.xlarge (T4)", 0.526, 4, "T4", "AWS on-demand list price, unverified"),
}


@dataclass
class CostModel:
    usd_per_kwh: float = 0.17                 # assumption: ~US residential average
    laptop_price_usd: float = 0.0             # sunk by default; set to amortise hardware
    laptop_life_hours: float = 4 * 365 * 8    # 4 years x 8 h/day
    egress_usd_per_gb: float = 0.09           # assumption: typical hyperscaler internet egress
    min_billing_s: float = 60.0               # assumption: per-second billing, 60 s minimum
    offers: dict = field(default_factory=lambda: dict(OFFERS))

    def local(self, wall_s: float, energy_j: float | None, idle_watts: float | None = None) -> dict:
        """Cost of a measured local run. Energy cost uses the marginal energy above idle
        when an idle baseline is known, otherwise the whole-machine energy."""
        out = {"estimated": False, "hardware_usd": 0.0, "energy_usd": None, "total_usd": None}
        if self.laptop_price_usd:
            out["hardware_usd"] = self.laptop_price_usd / self.laptop_life_hours * wall_s / 3600
        if energy_j is not None:
            j = energy_j - (idle_watts * wall_s if idle_watts else 0.0)
            out["marginal_energy_j"] = max(j, 0.0)
            out["energy_usd"] = max(j, 0.0) / 3.6e6 * self.usd_per_kwh
            out["total_usd"] = out["hardware_usd"] + out["energy_usd"]
        return out

    def cloud(self, offer_key: str, local_wall_s: float, speed_ratio: float,
              payload_bytes: int = 0, result_bytes: int = 0, startup_s: float = 0.0) -> dict:
        """ESTIMATE of running the same job on a cloud offer.
        speed_ratio = assumed (cloud throughput / local throughput)."""
        o = self.offers[offer_key]
        run_s = local_wall_s / speed_ratio + startup_s
        billed = max(run_s, self.min_billing_s)
        compute = o.usd_per_hour * billed / 3600
        net = result_bytes / 1e9 * self.egress_usd_per_gb     # ingress assumed free
        return {"estimated": True, "offer": o.name, "basis": o.basis, "assumed_speed_ratio": speed_ratio,
                "run_s": run_s, "billed_s": billed, "compute_usd": compute, "network_usd": net,
                "total_usd": compute + net}

    def break_even_seconds(self, offer_key: str, local_watts_marginal: float) -> float | None:
        """Local run time above which cloud min-billing stops dominating (same speed)."""
        o = self.offers[offer_key]
        local_per_s = local_watts_marginal / 3.6e6 * self.usd_per_kwh
        cloud_per_s = o.usd_per_hour / 3600
        return None if cloud_per_s <= local_per_s else self.min_billing_s
