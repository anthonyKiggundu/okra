#!/usr/bin/env python3
"""Plot OAI--FlexRIC evaluation metrics from measured experiment logs.

This script does not generate synthetic data. It reads CSV logs written by
actual OAI/FlexRIC runs and leaves a panel empty when its measurements are
not available.

Required files in --data-dir
----------------------------
service_metrics.csv
  One row per run/controller/scenario/service/time sample. Required columns:
    run_id,controller,scenario,time_s,service
  At least one of these measurement/limit pairs (or explicit sla_violation):
    latency_ms,latency_sla_ms
    throughput_mbps,throughput_min_mbps
    packet_loss_pct,packet_loss_max_pct
  Optional resource columns:
    prbs_allocated,prb_utilization_pct

  If sla_violation is supplied, it should be a Boolean/0-1 label reflecting
  the service's SLA definition for that sample.

action_log.csv
  One row per candidate-action evaluation. Required columns:
    run_id,controller,scenario,predicted_risk,risk_threshold,
    observed_violation_within_horizon,blocked
  Optional:
    counterfactual_safe

  IMPORTANT: For action-dependent risk P(violation | state, action), the
  observed label must correspond to that candidate action being evaluated.
  This generally requires paired/repeated controlled trials or a validated
  offline replay/test environment. Do not label an unexecuted candidate
  action using the outcome of a different action.

anticipation_events.csv (optional)
  One row per intervention episode:
    run_id,controller,scenario,episode_id,intervention_time_s,
    matched_baseline_violation_time_s,recovery_time_s
  The matched baseline breach time should come from a comparable run in
  which the protective intervention was not applied (or another defensible
  counterfactual). A protected run with no breach does not, by itself,
  reveal when a breach would otherwise have occurred.

control_timing.csv (optional)
  One row per control-loop transaction:
    run_id,controller,scenario,kpm_rx_ms,decision_ms,e2_tx_ms,ran_apply_ms
  All timestamps must use a common clock/time base.

Usage:
  python plot_oai_flexric_evaluation.py --data-dir ./experiment_logs
  python plot_oai_flexric_evaluation.py --data-dir ./experiment_logs --scenario contention
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def read_csv_optional(data_dir: Path, filename: str) -> Optional[pd.DataFrame]:
    path = data_dir / filename
    if not path.exists():
        print(f"[INFO] {filename} not found; related metrics will be omitted.")
        return None
    frame = pd.read_csv(path)
    if frame.empty:
        print(f"[INFO] {filename} is empty; related metrics will be omitted.")
        return None
    return frame


def require_columns(frame: pd.DataFrame, columns: list[str], filename: str) -> bool:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        print(f"[WARNING] {filename} is missing: {', '.join(missing)}")
        return False
    return True


def to_bool(series: pd.Series) -> pd.Series:
    mapping = {
        "true": True, "false": False, "1": True, "0": False,
        "yes": True, "no": False, "y": True, "n": False,
    }
    return series.astype("string").str.strip().str.lower().map(mapping).astype("boolean")


def apply_scenario_filter(
    frame: Optional[pd.DataFrame], scenario: Optional[str], filename: str
) -> Optional[pd.DataFrame]:
    if frame is None:
        return None
    if "scenario" not in frame.columns:
        if scenario is not None:
            raise ValueError(f"--scenario was supplied, but {filename} has no scenario column")
        return frame
    if scenario is not None:
        filtered = frame[frame["scenario"].astype(str) == scenario].copy()
        if filtered.empty:
            raise ValueError(f"No rows in {filename} for scenario '{scenario}'")
        return filtered
    unique = frame["scenario"].dropna().astype(str).unique()
    if len(unique) > 1:
        raise ValueError(
            f"{filename} contains multiple scenarios ({', '.join(unique)}). "
            "Run once per scenario using --scenario to avoid pooling unlike conditions."
        )
    return frame


def add_empty(ax: plt.Axes, message: str, title: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", wrap=True,
            transform=ax.transAxes)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])


def derive_sla_violation(data: pd.DataFrame) -> pd.Series:
    if "sla_violation" in data.columns:
        explicit = to_bool(data["sla_violation"])
        if explicit.notna().any():
            return explicit

    conditions = []
    valid_any = pd.Series(False, index=data.index, dtype=bool)
    violation_any = pd.Series(False, index=data.index, dtype=bool)
    pairs = [
        ("latency_ms", "latency_sla_ms", "gt"),
        ("throughput_mbps", "throughput_min_mbps", "lt"),
        ("packet_loss_pct", "packet_loss_max_pct", "gt"),
    ]
    for measurement, limit, direction in pairs:
        if measurement not in data.columns or limit not in data.columns:
            continue
        value = pd.to_numeric(data[measurement], errors="coerce")
        bound = pd.to_numeric(data[limit], errors="coerce")
        valid = value.notna() & bound.notna()
        condition = value > bound if direction == "gt" else value < bound
        violation_any |= (condition & valid).fillna(False)
        valid_any |= valid
        conditions.append((measurement, limit))

    if not conditions or not valid_any.any():
        raise ValueError(
            "SLA violation cannot be derived. Provide sla_violation or at least "
            "one complete measurement/limit pair."
        )
    result = pd.Series(pd.NA, index=data.index, dtype="boolean")
    result.loc[valid_any] = violation_any.loc[valid_any]
    return result


def plot_service_timeseries(
    ax: plt.Axes,
    metrics: Optional[pd.DataFrame],
    value_col: str,
    limit_col: str,
    title: str,
    ylabel: str,
) -> None:
    required = ["run_id", "controller", "time_s", "service", value_col]
    if metrics is None or not require_columns(metrics, required, "service_metrics.csv"):
        add_empty(ax, f"{value_col} unavailable in service_metrics.csv", title)
        return

    data = metrics.copy()
    data["time_s"] = pd.to_numeric(data["time_s"], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["time_s", value_col])
    if data.empty:
        add_empty(ax, f"No valid {value_col} samples", title)
        return

    # Average within each run first, then across independent runs.
    per_run = data.groupby(
        ["run_id", "controller", "service", "time_s"], as_index=False
    )[value_col].mean()
    averaged = per_run.groupby(
        ["controller", "service", "time_s"], as_index=False
    )[value_col].mean()

    for (controller, service), group in averaged.groupby(["controller", "service"]):
        group = group.sort_values("time_s")
        ax.plot(group["time_s"], group[value_col],
                label=f"{controller} / {service}")

    if limit_col in data.columns:
        data[limit_col] = pd.to_numeric(data[limit_col], errors="coerce")
        limits = data.dropna(subset=[limit_col]).groupby("service")[limit_col].median()
        for service, limit in limits.items():
            ax.axhline(limit, linestyle="--", linewidth=1,
                       label=f"{service} SLA ({limit:g})")

    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7)


def plot_sla_violation_rate(ax: plt.Axes, metrics: Optional[pd.DataFrame]) -> None:
    required = ["run_id", "controller", "service"]
    if metrics is None or not require_columns(metrics, required, "service_metrics.csv"):
        add_empty(ax, "SLA violation labels unavailable", "SLA violation rate")
        return
    data = metrics.copy()
    try:
        data["sla_violation"] = derive_sla_violation(data)
    except ValueError as exc:
        add_empty(ax, str(exc), "SLA violation rate")
        return
    data = data.dropna(subset=["sla_violation"])
    if data.empty:
        add_empty(ax, "No labelled SLA samples", "SLA violation rate")
        return

    per_run = data.groupby(
        ["run_id", "controller", "service"], as_index=False
    )["sla_violation"].mean()
    summary = per_run.groupby(["controller", "service"])["sla_violation"].agg(
        mean="mean", std="std", n="count"
    ).reset_index()
    summary["ci95"] = 1.96 * summary["std"].fillna(0) / np.sqrt(summary["n"].clip(lower=1)) * 100
    summary["rate_pct"] = summary["mean"] * 100
    means = summary.pivot(index="controller", columns="service", values="rate_pct")
    errors = summary.pivot(index="controller", columns="service", values="ci95")
    means.plot(
        kind="bar", ax=ax,
        yerr=errors.reindex(index=means.index, columns=means.columns), capsize=3,
    )
    ax.set_title("SLA violation rate (mean across runs)")
    ax.set_xlabel("Controller")
    ax.set_ylabel("Violating measurement intervals (%)")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="Service", fontsize=7)


def plot_resource_use(ax: plt.Axes, metrics: Optional[pd.DataFrame]) -> None:
    if metrics is None:
        add_empty(ax, "No service metrics file", "RAN resource use")
        return
    data = metrics.copy()

    if {"run_id", "controller", "service", "time_s", "prbs_allocated"}.issubset(data.columns):
        data["time_s"] = pd.to_numeric(data["time_s"], errors="coerce")
        data["prbs_allocated"] = pd.to_numeric(data["prbs_allocated"], errors="coerce")
        data = data.dropna(subset=["time_s", "prbs_allocated"])
        if not data.empty:
            per_run = data.groupby(
                ["run_id", "controller", "service", "time_s"], as_index=False
            )["prbs_allocated"].mean()
            averaged = per_run.groupby(
                ["controller", "service", "time_s"], as_index=False
            )["prbs_allocated"].mean()
            for (controller, service), group in averaged.groupby(["controller", "service"]):
                group = group.sort_values("time_s")
                ax.plot(group["time_s"], group["prbs_allocated"],
                        label=f"{controller} / {service}")
            ax.set_title("PRBs allocated by service")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Allocated PRBs")
            ax.grid(True, alpha=0.25)
            ax.legend(fontsize=7)
            return

    required = {"run_id", "controller", "time_s", "prb_utilization_pct"}
    if required.issubset(data.columns):
        data["time_s"] = pd.to_numeric(data["time_s"], errors="coerce")
        data["prb_utilization_pct"] = pd.to_numeric(data["prb_utilization_pct"], errors="coerce")
        keys = ["run_id", "controller", "time_s"]
        if "scenario" in data.columns:
            keys.insert(2, "scenario")
        cell = data.dropna(subset=["time_s", "prb_utilization_pct"]).drop_duplicates(keys)
        per_run = cell.groupby(
            ["run_id", "controller", "time_s"], as_index=False
        )["prb_utilization_pct"].mean()
        averaged = per_run.groupby(
            ["controller", "time_s"], as_index=False
        )["prb_utilization_pct"].mean()
        for controller, group in averaged.groupby("controller"):
            group = group.sort_values("time_s")
            ax.plot(group["time_s"], group["prb_utilization_pct"], label=controller)
        ax.set_title("Cell-level PRB utilisation")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("PRB utilisation (%)")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7)
        return

    add_empty(ax, "Log prbs_allocated per service or\nprb_utilization_pct per cell", "RAN resource use")


def prediction_metrics(actions: pd.DataFrame) -> pd.DataFrame:
    """Calculate binary classification metrics using each row's risk threshold."""
    data = actions.copy()
    for col in ["predicted_risk", "risk_threshold"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["actual"] = to_bool(data["observed_violation_within_horizon"])
    data = data.dropna(subset=["predicted_risk", "risk_threshold", "actual"])
    data = data[data["predicted_risk"].between(0, 1) & data["risk_threshold"].between(0, 1)]
    if data.empty:
        return pd.DataFrame()
    data["predicted_positive"] = data["predicted_risk"] >= data["risk_threshold"]
    rows = []
    for controller, group in data.groupby("controller"):
        pred = group["predicted_positive"].astype(bool)
        actual = group["actual"].astype(bool)
        tp = int((pred & actual).sum())
        fp = int((pred & ~actual).sum())
        fn = int((~pred & actual).sum())
        tn = int((~pred & ~actual).sum())
        rows.append({
            "controller": controller,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "FPR": fp / (fp + tn) if fp + tn else np.nan,
            "FNR": fn / (fn + tp) if fn + tp else np.nan,
            "precision": tp / (tp + fp) if tp + fp else np.nan,
            "recall": tp / (tp + fn) if tp + fn else np.nan,
            "Brier": float(np.mean((group["predicted_risk"] - actual.astype(float)) ** 2)),
            "N": len(group),
        })
    return pd.DataFrame(rows)


def plot_risk(ax: plt.Axes, actions: Optional[pd.DataFrame], episodes: Optional[pd.DataFrame]) -> None:
    required = ["controller", "predicted_risk", "risk_threshold", "observed_violation_within_horizon"]
    if actions is None or not require_columns(actions, required, "action_log.csv"):
        add_empty(ax, "Risk predictions and outcome labels unavailable", "Anticipatory risk prediction")
        return

    data = actions.copy()
    data["predicted_risk"] = pd.to_numeric(data["predicted_risk"], errors="coerce")
    data["actual"] = to_bool(data["observed_violation_within_horizon"])
    data = data.dropna(subset=["predicted_risk", "actual"])
    data = data[data["predicted_risk"].between(0, 1)]
    if data.empty:
        add_empty(ax, "No valid risk predictions/outcome labels", "Anticipatory risk prediction")
        return

    bins = np.linspace(0, 1, 11)
    for controller, group in data.groupby("controller"):
        group = group.copy()
        group["risk_bin"] = pd.cut(group["predicted_risk"], bins=bins, include_lowest=True)
        cal = group.groupby("risk_bin", observed=True).agg(
            predicted=("predicted_risk", "mean"), observed=("actual", "mean")
        ).dropna()
        ax.plot(cal["predicted"], cal["observed"], marker="o", label=controller)
    ax.plot([0, 1], [0, 1], linestyle="--", label="Ideal calibration")

    cls = prediction_metrics(actions)
    if not cls.empty:
        lines = [
            f"{r.controller}: FPR {r.FPR:.2f}, FNR {r.FNR:.2f}, Brier {r.Brier:.3f}"
            for r in cls.itertuples() if pd.notna(r.FPR) and pd.notna(r.FNR)
        ]
        if lines:
            ax.text(0.02, 0.98, "\n".join(lines), transform=ax.transAxes,
                    va="top", fontsize=7,
                    bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.75})

    if episodes is not None and "intervention_time_s" in episodes.columns and \
            "matched_baseline_violation_time_s" in episodes.columns:
        intervention = pd.to_numeric(episodes["intervention_time_s"], errors="coerce")
        breach = pd.to_numeric(episodes["matched_baseline_violation_time_s"], errors="coerce")
        lead = (breach - intervention).dropna()
        lead = lead[lead >= 0]
        if not lead.empty:
            ax.text(0.98, 0.02,
                    f"Matched-baseline lead time: median {lead.median():.2f} s (N={len(lead)})",
                    transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
    ax.set_title("Risk calibration and prediction errors")
    ax.set_xlabel("Predicted SLA-violation probability")
    ax.set_ylabel("Observed violation frequency")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7)


def plot_avoidance(ax: plt.Axes, actions: Optional[pd.DataFrame], episodes: Optional[pd.DataFrame]) -> None:
    if actions is None or not require_columns(actions, ["controller", "blocked"], "action_log.csv"):
        add_empty(ax, "Action restriction records unavailable", "Avoidance and recovery")
        return
    data = actions.copy()
    data["blocked_bool"] = to_bool(data["blocked"])
    data = data.dropna(subset=["blocked_bool"])
    if data.empty:
        add_empty(ax, "No valid blocked-action records", "Avoidance and recovery")
        return

    block_rate = data.groupby("controller")["blocked_bool"].mean() * 100
    labels = list(block_rate.index)
    x = np.arange(len(labels))
    width = 0.36
    ax.bar(x - width / 2, block_rate.to_numpy(), width, label="Candidate actions blocked")

    if "counterfactual_safe" in data.columns:
        data["cf_safe"] = to_bool(data["counterfactual_safe"])
        valid = data.dropna(subset=["cf_safe"])
        safe_block = valid.assign(
            blocked_but_safe=valid["blocked_bool"] & valid["cf_safe"]
        ).groupby("controller")["blocked_but_safe"].mean() * 100
        ax.bar(x + width / 2, safe_block.reindex(labels, fill_value=0).to_numpy(), width,
               label="Blocked but safe (% of decisions)")
    else:
        ax.text(0.98, 0.96, "Over-blocking not calculated:\nmissing counterfactual_safe labels",
                transform=ax.transAxes, ha="right", va="top", fontsize=7)

    if episodes is not None and "recovery_time_s" in episodes.columns:
        recovery = pd.to_numeric(episodes["recovery_time_s"], errors="coerce").dropna()
        if not recovery.empty:
            ax.text(0.98, 0.04,
                    f"Recovery time: median {recovery.median():.2f} s (N={len(recovery)})",
                    transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Action decisions (%)")
    ax.set_title("Avoidance: blocking and over-blocking")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=7)


def plot_control_delays(ax: plt.Axes, timing: Optional[pd.DataFrame]) -> None:
    required = ["kpm_rx_ms", "decision_ms", "e2_tx_ms", "ran_apply_ms"]
    if timing is None or not require_columns(timing, required, "control_timing.csv"):
        add_empty(ax, "Control timestamps unavailable", "Control-loop overhead")
        return
    data = timing.copy()
    for col in required:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    stages = {
        "KPM to\ndecision": data["decision_ms"] - data["kpm_rx_ms"],
        "Decision to\nE2 transmit": data["e2_tx_ms"] - data["decision_ms"],
        "E2 transmit to\nRAN apply": data["ran_apply_ms"] - data["e2_tx_ms"],
        "Total KPM to\nRAN apply": data["ran_apply_ms"] - data["kpm_rx_ms"],
    }
    values, labels = [], []
    for label, samples in stages.items():
        clean = samples.dropna()
        clean = clean[clean >= 0]
        if not clean.empty:
            values.append(clean.to_numpy())
            labels.append(label)
    if not values:
        add_empty(ax, "No valid non-negative timing intervals", "Control-loop overhead")
        return
    ax.boxplot(values, showfliers=False)
    ax.set_xticks(np.arange(1, len(labels) + 1), labels=labels, rotation=15)
    ax.set_title("Measured control-loop delays")
    ax.set_ylabel("Delay (ms)")
    ax.grid(axis="y", alpha=0.25)


def print_summary(metrics: Optional[pd.DataFrame], actions: Optional[pd.DataFrame],
                  episodes: Optional[pd.DataFrame], timing: Optional[pd.DataFrame]) -> None:
    print("\n========== Summary calculated from measured logs ==========")
    if metrics is not None and {"run_id", "controller", "service"}.issubset(metrics.columns):
        m = metrics.copy()
        try:
            m["sla_violation"] = derive_sla_violation(m)
            valid = m.dropna(subset=["sla_violation"])
            per_run = valid.groupby(["run_id", "controller", "service"])["sla_violation"].mean()
            if not per_run.empty:
                summary = per_run.groupby(["controller", "service"]).agg(["mean", "std", "count"])
                summary["mean"] *= 100
                summary["std"] *= 100
                print("\nSLA violation rate (%; mean of per-run rates):")
                print(summary.to_string(float_format=lambda v: f"{v:.2f}"))
        except ValueError as exc:
            print(f"\nSLA summary unavailable: {exc}")

        for col, q, label in [
            ("latency_ms", 0.95, "P95 latency (ms)"),
            ("throughput_mbps", 0.05, "P05 throughput (Mbps)"),
            ("packet_loss_pct", 0.95, "P95 packet loss (%)"),
        ]:
            if col in m.columns:
                m[col] = pd.to_numeric(m[col], errors="coerce")
                p = m.dropna(subset=[col]).groupby(
                    ["run_id", "controller", "service"]
                )[col].quantile(q)
                if not p.empty:
                    print(f"\n{label} (mean of per-run values):")
                    print(p.groupby(["controller", "service"]).mean().to_string())

    if actions is not None:
        required = ["controller", "predicted_risk", "risk_threshold",
                    "observed_violation_within_horizon"]
        if all(c in actions.columns for c in required):
            cls = prediction_metrics(actions)
            if not cls.empty:
                print("\nPrediction classification metrics (threshold from each action row):")
                print(cls[["controller", "TP", "FP", "FN", "TN", "FPR", "FNR",
                           "precision", "recall", "Brier", "N"]].to_string(index=False))
        if {"controller", "blocked"}.issubset(actions.columns):
            blocked = to_bool(actions["blocked"])
            print("\nCandidate actions blocked (%):")
            print((blocked.groupby(actions["controller"]).mean() * 100).to_string())
        if "counterfactual_safe" in actions.columns and "blocked" in actions.columns:
            a = actions.copy()
            a["blocked_bool"] = to_bool(a["blocked"])
            a["cf_safe"] = to_bool(a["counterfactual_safe"])
            valid = a.dropna(subset=["blocked_bool", "cf_safe"])
            rate = valid.assign(
                overblocked=valid["blocked_bool"] & valid["cf_safe"]
            ).groupby("controller")["overblocked"].mean() * 100
            print("\nBlocked-but-safe actions (% of all labelled decisions):")
            print(rate.to_string())

    if episodes is not None:
        if {"intervention_time_s", "matched_baseline_violation_time_s"}.issubset(episodes.columns):
            intervention = pd.to_numeric(episodes["intervention_time_s"], errors="coerce")
            breach = pd.to_numeric(episodes["matched_baseline_violation_time_s"], errors="coerce")
            lead = (breach - intervention).dropna()
            lead = lead[lead >= 0]
            if not lead.empty:
                print(f"\nMatched-baseline intervention lead time: median={lead.median():.3f} s, "
                      f"P95={lead.quantile(.95):.3f} s, N={len(lead)}")
        if "recovery_time_s" in episodes.columns:
            recovery = pd.to_numeric(episodes["recovery_time_s"], errors="coerce").dropna()
            if not recovery.empty:
                print(f"\nRecovery time: median={recovery.median():.3f} s, "
                      f"P95={recovery.quantile(.95):.3f} s, N={len(recovery)}")

    if timing is not None and all(c in timing.columns for c in
                                  ["kpm_rx_ms", "decision_ms", "e2_tx_ms", "ran_apply_ms"]):
        t = timing.copy()
        for c in ["kpm_rx_ms", "decision_ms", "e2_tx_ms", "ran_apply_ms"]:
            t[c] = pd.to_numeric(t[c], errors="coerce")
        delays = {
            "KPM-to-decision": t["decision_ms"] - t["kpm_rx_ms"],
            "decision-to-E2": t["e2_tx_ms"] - t["decision_ms"],
            "E2-to-RAN-apply": t["ran_apply_ms"] - t["e2_tx_ms"],
            "total KPM-to-apply": t["ran_apply_ms"] - t["kpm_rx_ms"],
        }
        print("\nControl-loop delay percentiles (ms):")
        for name, values in delays.items():
            values = values.dropna()
            values = values[values >= 0]
            if not values.empty:
                print(f"{name:20s}: median={values.median():.3f}, "
                      f"P95={values.quantile(.95):.3f}, N={len(values)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("."),
                        help="Directory containing experiment CSV logs")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Plot one scenario; required when logs contain multiple scenarios")
    parser.add_argument("--output", type=Path, default=Path("oai_flexric_evaluation.png"),
                        help="Output image path")
    parser.add_argument("--no-show", action="store_true",
                        help="Save the figure without opening a display window")
    args = parser.parse_args()

    metrics = read_csv_optional(args.data_dir, "service_metrics.csv")
    actions = read_csv_optional(args.data_dir, "action_log.csv")
    episodes = read_csv_optional(args.data_dir, "anticipation_events.csv")
    timing = read_csv_optional(args.data_dir, "control_timing.csv")

    try:
        metrics = apply_scenario_filter(metrics, args.scenario, "service_metrics.csv")
        actions = apply_scenario_filter(actions, args.scenario, "action_log.csv")
        episodes = apply_scenario_filter(episodes, args.scenario, "anticipation_events.csv")
        timing = apply_scenario_filter(timing, args.scenario, "control_timing.csv")
    except ValueError as exc:
        parser.error(str(exc))

    fig, axes = plt.subplots(4, 2, figsize=(15, 17))
    heading = "OAI--FlexRIC evaluation from measured experiment logs"
    if args.scenario:
        heading += f" — scenario: {args.scenario}"
    fig.suptitle(heading, fontsize=15)

    plot_service_timeseries(axes[0, 0], metrics, "latency_ms", "latency_sla_ms",
                            "End-to-end latency", "Latency (ms)")
    plot_service_timeseries(axes[0, 1], metrics, "throughput_mbps", "throughput_min_mbps",
                            "Service throughput", "Throughput (Mbps)")
    plot_service_timeseries(axes[1, 0], metrics, "packet_loss_pct", "packet_loss_max_pct",
                            "Packet loss", "Packet loss (%)")
    plot_sla_violation_rate(axes[1, 1], metrics)
    plot_resource_use(axes[2, 0], metrics)
    plot_risk(axes[2, 1], actions, episodes)
    plot_avoidance(axes[3, 0], actions, episodes)
    plot_control_delays(axes[3, 1], timing)

    fig.tight_layout(rect=[0, 0, 1, 0.975])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200, bbox_inches="tight")
    print(f"\n[INFO] Figure saved to: {args.output.resolve()}")
    print_summary(metrics, actions, episodes, timing)
    if not args.no_show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
