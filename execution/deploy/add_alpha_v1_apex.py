#!/usr/bin/env python3
"""Merge the ALPHA-V1-APEX profile into the server's exec_configs.json.

deploy.sh intentionally excludes config/exec_configs.json from rsync (the
server copy owns live webhook/enabled state), so new profiles must be merged
into the server file explicitly. Run this ON THE DROPLET, then restart:

    scp execution/deploy/add_alpha_v1_apex.py root@143.110.148.234:/tmp/
    ssh root@143.110.148.234 "python3 /tmp/add_alpha_v1_apex.py && systemctl restart orb-trader"

Creates a timestamped .bak alongside the target before writing. Idempotent:
exits without changes if the profile already exists.
"""
import json
import shutil
import sys
import time
from collections import OrderedDict

PROFILE_NAME = "ALPHA-V1-APEX"

PROFILE = {
    "enabled": True,
    "max_open_contracts": 20,
    "webhooks": [],
    "adaptive_risk": {
        "enabled": True,
        "anchor": {"date": "2026-07-22", "balance": 50000.0},
        "payouts": [],
        "balance_override": None,
        "tiers": [
            {"profit_below": 1500.0, "risk_scale": 0.8, "max_open_contracts": 20},
            {"profit_below": 3000.0, "risk_scale": 1.0, "max_open_contracts": 30},
            {"profit_below": 6000.0, "risk_scale": 1.0, "max_open_contracts": 40},
        ],
        "default_tier": {"risk_scale": 1.0, "max_open_contracts": 40},
        "consistency": {"best_day_frac": 0.5, "blocked_risk_scale": 0.5},
    },
    "sessions": {
        "NQ_NY": {
            "orb_start": "09:30", "orb_end": "09:45",
            "entry_start": "09:45", "entry_end": "12:00",
            "flat_start": "15:30", "flat_end": "16:00",
            "stop_basis": "atr", "gap_filter_basis": "atr",
            "stop_atr_pct": 7.0, "min_gap_atr_pct": 2.5, "atr_length": 12,
            "rr": 3.5, "tp1_ratio": 0.4,
            "risk_usd": 250, "max_single_risk_usd": 375,
            "long_only": True, "excluded_dow": [4],
            "min_stop_pts": 0.0, "min_tp1_pts": 0.0,
        },
        "NQ_Asia": {
            "orb_start": "20:00", "orb_end": "20:15",
            "entry_start": "20:15", "entry_end": "22:30",
            "flat_start": "04:00", "flat_end": "04:10",
            "stop_basis": "orb", "gap_filter_basis": "orb",
            "stop_orb_pct": 100.0, "min_gap_orb_pct": 10.0, "atr_length": 5,
            "rr": 6.0, "tp1_ratio": 0.3,
            "risk_usd": 250, "max_single_risk_usd": 375,
            "long_only": True, "excluded_dow": [1],
            "half_days": ["20250703", "20251128", "20251224", "20250109", "20260119"],
        },
        "ES_Asia": {
            "orb_start": "20:00", "orb_end": "20:15",
            "entry_start": "20:15", "entry_end": "03:00",
            "flat_start": "07:00", "flat_end": "07:10",
            "stop_basis": "orb", "gap_filter_basis": "atr",
            "min_gap_atr_pct": 0.5, "atr_length": 14,
            "rr": 1.5, "tp1_ratio": 0.7,
            "risk_usd": 250, "max_single_risk_usd": 375,
            "long_only": True, "min_stop_pts": 3.0, "min_tp1_pts": 3.0,
        },
        "ES_NY": {
            "orb_start": "09:30", "orb_end": "09:45",
            "entry_start": "09:45", "entry_end": "13:00",
            "flat_start": "15:50", "flat_end": "16:00",
            "stop_basis": "atr", "gap_filter_basis": "atr",
            "stop_atr_pct": 5.0, "min_gap_atr_pct": 0.25, "atr_length": 7,
            "rr": 5.0, "tp1_ratio": 0.2,
            "risk_usd": 250, "max_single_risk_usd": 375,
            "long_only": True, "excluded_dow": [3],
            "min_stop_pts": 3.0, "min_tp1_pts": 3.0,
        },
    },
    "lsi_sessions": {
        "NQ_NY_LSI": {
            "sweep_start": "08:30", "sweep_end": "15:00",
            "entry_start": "08:30", "entry_end": "13:30",
            "flat_start": "15:50", "flat_end": "16:00",
            "rr": 3.5, "tp1_ratio": 0.4,
            "min_gap_atr_pct": 3.0, "atr_length": 14,
            "risk_usd": 250, "max_single_risk_usd": 375,
            "qty_multiplier": 1.0, "min_stop_points": 0.0,
            "fvg_window_left": 20, "fvg_window_right": 2,
            "lsi_entry_mode": "fvg_limit", "lsi_variant": "htf-LSI",
            "htf_level_tf_minutes": 60, "htf_n_left": 3,
            "htf_trade_max_per_session": 2, "max_fvg_to_inversion_bars": 24,
            "long_only": True, "excluded_dow": None,
        },
    },
}


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/opt/orb-trader/config/exec_configs.json"
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path) as fh:
        data = json.load(fh, object_pairs_hook=OrderedDict)
    if PROFILE_NAME in data:
        print(f"{PROFILE_NAME} already present; file untouched. Backup: {backup}")
        return
    data[PROFILE_NAME] = PROFILE
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"Merged {PROFILE_NAME} into {path}")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
