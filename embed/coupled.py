"""
Integrated slicing xApp: avoidance circuit + counterfactual safety gate + FlexRIC loop.

Merges v2_wired.py (pipeline, tabular circuit, safety gate, mocks, experiments) with
wired.py (PyTorch amygdala/PFC/accumbens actor-critic and the live FlexRIC loop).

Flow implemented (numbers match the flow diagram)
  1. E2-KPM telemetry from the gNB           -> MockRAN, or the real gNB via FlexRICAdapter
  2. FlexRIC publishes metrics to the xApp   -> RIC.poll_indication
  3. Perception: telemetry -> state tensor   -> Perception.to_state
  4. Neural model: threat/congestion risk    -> CircuitPolicy (tabular) or NeuralCircuitPolicy (PyTorch)
  5. Safety gate: counterfactual checks      -> SafetyGate (digital twin predicts every candidate)
  6. Action selection: slice PRB quotas      -> ACTIONS table, chosen after the gate
  7. E2-RC control message                   -> RcControl built by SlicingXApp.step
  8. FlexRIC dispatches over E2              -> RIC.send_rc_control

Two RIC back ends expose the same four methods (init_xapp, poll_indication,
send_rc_control, close): MockFlexRIC (simulation) and FlexRICAdapter (live). The adapter
uses the `flexric` calls from wired.py; those names and the KPM packet layout are NOT
verified against a real FlexRIC SDK, so check them before running live.

Run:
  python slicing_xapp.py                                   # compare all variants in simulation
  python slicing_xapp.py --mode demo --policy neural       # closed loop on the mock RAN, with logging
  python slicing_xapp.py --mode live --policy circuit      # closed loop on a real FlexRIC RIC
PyTorch is needed only for the neural policy; everything else runs on NumPy.
"""
import argparse
import sys
import time

import numpy as np

try:                                   # optional: only the neural policy needs PyTorch
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.distributions import Categorical
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
from collections import deque
from dataclasses import dataclass, field

# ======================================================================
# 0. CONFIGURATION
# ======================================================================
TOTAL_PRB = 100          # PRBs in the cell
URLLC_MAX = 40           # cap on the URLLC slice


@dataclass(frozen=True)
class SliceConfig:
    """One selectable quota setting (the xApp's discrete action)."""
    name: str
    urllc_min: int       # PRBs reserved for URLLC
    embb_max: int        # PRB cap for eMBB


# Action 0 is the status quo; higher indices protect URLLC more at eMBB's expense.
# "strong" is deliberately unsafe for eMBB (its guaranteed rate), so the gate must refuse it.
ACTIONS = [SliceConfig("baseline", 10, 90),
           SliceConfig("moderate", 25, 70),
           SliceConfig("strong", 45, 40)]
N_ACTIONS = len(ACTIONS)


@dataclass(frozen=True)
class SLA:
    urllc_latency_ms: float = 10.0   # URLLC latency bound
    embb_gbr_mbps: float = 36.0      # eMBB guaranteed bit rate (illustrative, not a standard)


SLA_DEFAULT = SLA()


@dataclass(frozen=True)
class RanModel:
    """Parameters of the simple queueing/scheduler model shared by the RAN and its twin."""
    lat_base: float = 2.0    # ms at zero load
    lat_slope: float = 2.0   # ms per unit of rho/(1-rho)
    prb_mbps: float = 0.8    # eMBB Mbps per PRB


REAL_MODEL = RanModel()
TWIN_MODEL = RanModel(lat_base=2.0, lat_slope=1.8, prb_mbps=0.85)  # deliberately ~10% off


def schedule(demand_u, demand_e, urllc_min, embb_max, m: RanModel):
    """Scheduler + latency model. Returns latency, eMBB Mbps, utilisation %, URLLC/eMBB PRBs used."""
    # eMBB is greedy up to its cap, but cannot touch the URLLC reservation
    e_taken = min(demand_e, embb_max, TOTAL_PRB - urllc_min)
    # URLLC gets whatever eMBB leaves, up to its cap (always >= its reservation)
    c_u = min(URLLC_MAX, TOTAL_PRB - e_taken)
    u_used = min(demand_u, c_u)
    # Queueing delay grows sharply as URLLC load approaches its capacity
    rho = min(demand_u / max(c_u, 1e-6), 0.995)
    lat = m.lat_base + m.lat_slope * rho / (1.0 - rho)
    return lat, e_taken * m.prb_mbps, u_used + e_taken, u_used, e_taken


# ======================================================================
# 1-2, 7-8. MOCKED RAN AND FLEXRIC  ("Real FlexRIC boundary")
# ======================================================================
@dataclass
class Kpm:
    """One E2SM-KPM indication (the fields the xApp subscribes to)."""
    t: int
    dl_prb_util: float            # total PRB usage, percent
    urllc_prb_used: float
    embb_prb_used: float
    urllc_prb_demand: float       # offered-load estimate (from buffer status in a real RAN)
    embb_prb_demand: float
    urllc_latency_ms: float
    embb_tput_mbps: float
    dl_tput_mbps: float           # total downlink throughput


@dataclass
class RcControl:
    """One E2SM-RC slice-level PRB quota control message."""
    primitive: str = "SLICE_LEVEL_PRB_QUOTA"
    slices: list = field(default_factory=list)   # [{"id", "min_prb", "max_prb"}, ...]


def envelope(t, start, ramp, end, fall):
    """0 -> 1 -> 0 trapezoid used to shape surges."""
    if t < start or t >= end:
        return 0.0
    if t < start + ramp:
        return (t - start) / ramp
    if t >= end - fall:
        return (end - t) / fall
    return 1.0


def eval_profile(t, rng):
    """Evaluation traffic: calm, surge 1, long calm, harder 'unseen' surge 2, calm."""
    du = 12 + 1.5 * rng.normal()
    de = 55 + 3 * rng.normal()
    de += envelope(t, 300, 20, 400, 20) * (100 - 55)            # surge 1: eMBB to ~100 PRBs
    s2 = envelope(t, 700, 20, 800, 20)
    de += s2 * (115 - 55)                                       # surge 2: heavier eMBB
    du += s2 * 6                                                # ... plus more URLLC load
    return max(du, 1.0), max(de, 1.0)


def train_profile(t, rng):
    """Sandbox traffic for pre-training: repeated surges of random size."""
    du = 12 + 1.5 * rng.normal()
    de = 55 + 3 * rng.normal()
    phase = t % 160
    peak = 90 + 25 * ((t // 160) % 3) / 2.0                     # peaks 90, 102, 115
    de += envelope(phase, 60, 20, 120, 20) * (peak - 55)
    return max(du, 1.0), max(de, 1.0)


class MockRAN:
    """Stands in for the OAI gNB: applies the active quota and emits KPM."""

    def __init__(self, profile, rng, model=REAL_MODEL):
        self.profile, self.rng, self.model = profile, rng, model
        self.t = 0
        self.pending = (ACTIONS[0].urllc_min, ACTIONS[0].embb_max)   # (urllc_min, embb_max)

    def step(self) -> Kpm:
        urllc_min, embb_max = self.pending                    # control takes effect this step
        du, de = self.profile(self.t, self.rng)
        lat, tput, util, u_used, e_taken = schedule(du, de, urllc_min, embb_max, self.model)
        lat *= float(np.exp(0.03 * self.rng.normal()))        # measurement noise
        kpm = Kpm(self.t, util, u_used, e_taken, du, de, lat, tput, tput + u_used * 0.2)
        self.t += 1
        return kpm

    def apply_quota(self, urllc_min, embb_max):
        self.pending = (urllc_min, embb_max)


class MockFlexRIC:
    """Simulated Near-RT RIC: the same four-method surface as FlexRICAdapter."""

    def __init__(self, ran: MockRAN):
        self.ran, self.sent = ran, []

    def init_xapp(self, name):
        self.name = name

    def poll_indication(self) -> Kpm:
        # Steps 1-2: gNB emits E2-KPM, RIC forwards it to the subscribed xApp
        return self.ran.step()

    def send_rc_control(self, msg: RcControl):
        # Steps 7-8: RIC receives the E2-RC message and dispatches it to the gNB
        by_id = {s["id"]: s for s in msg.slices}
        self.ran.apply_quota(by_id[1]["min_prb"], by_id[2]["max_prb"])
        self.sent.append(msg)
        return True

    def close(self):
        pass


class FlexRICAdapter:
    """
    Live Near-RT RIC back end, built from the calls in wired.py.

    UNVERIFIED: `flexric.init_xapp`, `poll_indication_message`, `send_e2_control` and
    `free_xapp` are the names wired.py used; they were not checked against a FlexRIC SDK.
    `_parse_kpm` must be written for your KPM subscription. It raises instead of returning
    constants (wired.py's placeholder returned fixed values, so the agent never saw real load).
    """

    def __init__(self, timeout_ms=1000):
        import flexric                                   # imported lazily: simulation runs without it
        self.flexric, self.timeout_ms, self.t = flexric, timeout_ms, 0

    def init_xapp(self, name):
        self.handle = self.flexric.init_xapp(name)

    def poll_indication(self):
        packet = self.flexric.poll_indication_message(timeout_ms=self.timeout_ms)
        if not packet:
            return None                                  # timeout: no new indication this period
        kpm = self._parse_kpm(packet)
        self.t += 1
        return kpm

    def _parse_kpm(self, packet) -> Kpm:
        # Map your E2SM-KPM measurement names onto every Kpm field, e.g.
        #   DRB.UEThpDl -> embb_tput_mbps, RRU.PrbUsedDl -> dl_prb_util / *_prb_used,
        #   buffer-status reports -> *_prb_demand, per-slice delay -> urllc_latency_ms.
        raise NotImplementedError("Map the FlexRIC KPM indication onto Kpm fields for your gNB.")

    def send_rc_control(self, msg: RcControl):
        payload = {"service_model": "E2SM-RC",
                   "control_primitive": msg.primitive,
                   "slices": msg.slices}
        return self.flexric.send_e2_control(payload)

    def close(self):
        self.flexric.free_xapp()


# ======================================================================
# 3. PERCEPTION: telemetry -> state tensor
# ======================================================================
@dataclass
class State:
    x: np.ndarray        # feature vector the circuit reads (the "state tensor")
    x_safe: float        # headroom cue, read by the safety pathway
    cue: int             # discrete cue type (utilisation bin) for the value tables
    util: float
    latency: float
    du_hat: float        # one-step-ahead URLLC demand estimate (for the twin)
    de_hat: float        # one-step-ahead eMBB demand estimate


class Perception:
    """Normalises KPM, adds a trend feature, and extrapolates demand one step ahead."""

    def __init__(self, sla=SLA_DEFAULT, window=3):
        self.sla, self.window = sla, window
        self.util_hist = deque(maxlen=window + 1)
        self.du_hist = deque(maxlen=window + 1)
        self.de_hist = deque(maxlen=window + 1)

    @staticmethod
    def _slope(hist, window):
        # Average per-step change over the history window (0 until enough data)
        return (hist[-1] - hist[0]) / (len(hist) - 1) if len(hist) > 1 else 0.0

    def to_state(self, k: Kpm) -> State:
        self.util_hist.append(k.dl_prb_util)
        self.du_hist.append(k.urllc_prb_demand)
        self.de_hist.append(k.embb_prb_demand)
        trend = np.clip(self._slope(self.util_hist, self.window) * self.window / 100.0, 0, 0.15) / 0.15
        x = np.array([k.dl_prb_util / 100.0,                                   # cell load
                      k.embb_prb_used / 100.0,                                 # eMBB share
                      np.clip(k.urllc_latency_ms / self.sla.urllc_latency_ms, 0, 2) / 2.0,
                      k.urllc_prb_used / URLLC_MAX,                            # URLLC share
                      trend,                                                   # rising load
                      1.0])                                                    # context / bias
        x_safe = float(np.clip((0.7 - k.dl_prb_util / 100.0) / 0.7, 0, 1))     # headroom cue
        cue = 0 if k.dl_prb_util < 70 else (1 if k.dl_prb_util < 88 else 2)
        du_hat = max(0.0, k.urllc_prb_demand + self._slope(self.du_hist, self.window))
        de_hat = max(0.0, k.embb_prb_demand + self._slope(self.de_hist, self.window))
        return State(x, x_safe, cue, k.dl_prb_util, k.urllc_latency_ms, du_hat, de_hat)


# ======================================================================
# 4. NEURAL MODEL: the avoidance circuit, generalised to feature vectors and N actions
# ======================================================================
@dataclass
class CircuitParams:
    lr_ba: float = 0.10          # BA threat learning (delta rule on SLA violations)
    lr_safe: float = 0.10        # safety-pathway learning
    lr_il: float = 0.10          # IL gate growth with successful protection
    lr_hab: float = 0.02         # habit values, driven by the dopamine RPE
    lr_model: float = 0.10       # goal-directed violation-model learning
    shock_cost: float = 1.0      # cost of an SLA violation
    relief_gain: float = 1.0     # value of risk reduction
    effort: tuple = (0.0, 0.15, 0.40)   # cost of each action (eMBB opportunity cost)
    beta: float = 5.0            # action-selection sharpness
    freeze_gain: float = 8.0     # strength of status-quo bias under threat
    eps: float = 0.05            # exploration
    protect_exposure: float = 0.25  # share of the threat experienced while protected
    ba_unlearning: float = 0.30  # threat memory is slow to unlearn
    arb_tau: float = 0.05
    arb_k: float = 20.0
    mb_cost: float = 0.05
    il_enabled: bool = True
    pl_enabled: bool = True


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class AvoidanceCircuit:
    def __init__(self, n_features, n_actions, n_cues, p: CircuitParams, rng):
        self.p, self.rng, self.n_actions = p, rng, n_actions
        self.w_ba = np.zeros(n_features)                       # BA threat weights over the state tensor
        self.alpha = np.array([1, 1, 1, 1, 1, 0.1])[:n_features]  # feature salience (bias is weak)
        self.w_safe = 0.0                                      # prelimbic safety pathway strength
        self.il_gate = 0.0                                     # infralimbic suppression of status-quo bias
        self.q_hab = np.zeros((n_cues, n_actions))             # cached (habit) values
        self.p_viol = np.full((n_cues, n_actions), 0.3)        # goal-directed P(violation | cue, action)
        self.err_mb, self.err_hab = 0.3, 0.3                   # reliability trackers for arbitration

    def context_fear(self):
        """Risk attributable to the bias/context term (what remains once the cue is gone)."""
        return float(np.clip(self.w_ba[-1], 0, 1))

    def policy(self, st: State):
        p = self.p
        # BA: threat estimate = predicted probability of an SLA violation
        fear_raw = float(np.clip(self.w_ba @ st.x, 0, 1))
        # Safety pathway: headroom cue scales the threat estimate down
        gate_pl = float(np.clip(self.w_safe * st.x_safe, 0, 1)) if p.pl_enabled else 0.0
        fear_ba = fear_raw * (1 - gate_pl)
        # IL gate: suppresses the status-quo bias (CeA freezing analogue), not the BA motivation
        freeze = fear_ba * (1 - self.il_gate)
        # Goal-directed values: violation model plus expected relief from protecting
        exp_relief = np.array([0.0] + [max(0.0, fear_ba - self.context_fear())] * (self.n_actions - 1))
        eff = np.array(p.effort)
        q_mb = -p.shock_cost * self.p_viol[st.cue] - eff + p.relief_gain * exp_relief
        # Arbitration between goal-directed and habit values by reliability
        w_h = sigmoid(p.arb_k * (self.err_mb - self.err_hab + p.mb_cost))
        q = (1 - w_h) * q_mb + w_h * self.q_hab[st.cue]
        # Status-quo bias competes with every protective action
        bias = np.array([1.0] + [-1.0] * (self.n_actions - 1))
        logits = p.beta * q + p.freeze_gain * freeze * bias
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        probs = (1 - p.eps) * probs + p.eps / self.n_actions
        return dict(probs=probs, q=q, q_mb=q_mb, w_habit=w_h, fear_raw=fear_raw, gate_pl=gate_pl,
                    fear_ba=fear_ba, freeze=freeze, x=st.x, x_safe=st.x_safe, cue=st.cue)

    def learn(self, info, a, us):
        """Update every plastic site after observing whether the executed action ended in a violation."""
        p, k = self.p, info["cue"]
        exposure = 1.0 if a == 0 else p.protect_exposure       # protection truncates exposure to the threat
        fear_ba = info["fear_ba"]
        relief = max(0.0, fear_ba - self.context_fear()) if a > 0 else 0.0
        r = -p.shock_cost * us - p.effort[a] + p.relief_gain * relief
        dopamine = r - self.q_hab[k, a]                        # RPE trains the habit system
        self.err_mb += p.arb_tau * (abs(r - info["q_mb"][a]) - self.err_mb)
        self.err_hab += p.arb_tau * (abs(dopamine) - self.err_hab)
        self.q_hab[k, a] += p.lr_hab * dopamine
        self.p_viol[k, a] += p.lr_model * (us - self.p_viol[k, a])
        err = us - fear_ba
        err_ba = err if err > 0 else p.ba_unlearning * err     # slow unlearning of the threat trace
        self.w_ba += p.lr_ba * err_ba * (1 - info["gate_pl"]) * self.alpha * info["x"] * exposure
        if p.pl_enabled:                                       # safety learned from expected-but-omitted violations
            self.w_safe -= p.lr_safe * err * info["fear_raw"] * info["x_safe"] * exposure
            self.w_safe = float(np.clip(self.w_safe, 0, 1))
        if p.il_enabled and a > 0 and relief > 0:              # IL gate grows with successful protection
            self.il_gate += p.lr_il * (1 - self.il_gate)
        return dopamine


# ======================================================================
# POLICIES: every controller exposes propose() / observe() so they are interchangeable
# ======================================================================
@dataclass
class Proposal:
    action: int
    values: np.ndarray            # per-action value, used by the gate to rank safe alternatives
    extras: dict = field(default_factory=dict)


class StaticPolicy:
    """Always proposes the status quo. With the gate attached this is the 'shield only' control."""

    def propose(self, st):
        return Proposal(0, np.array([1.0, 0.5, 0.0]))

    def observe(self, st_prev, prop, executed, kpm, st_now, sla):
        pass


class CircuitPolicy:
    """Wraps the avoidance circuit as an xApp policy."""

    def __init__(self, circuit: AvoidanceCircuit, rng):
        self.circuit, self.rng = circuit, rng

    def propose(self, st):
        info = self.circuit.policy(st)
        a = int(self.rng.choice(N_ACTIONS, p=info["probs"]))
        return Proposal(a, info["q"].copy(), {"info": info})

    def observe(self, st_prev, prop, executed, kpm, st_now, sla):
        # Learn from what was actually executed (the gate may have overridden the proposal)
        us = float(kpm.urllc_latency_ms > sla.urllc_latency_ms)
        self.circuit.learn(prop.extras["info"], executed, us)


class PEBasedArbitrationAgent:
    """
    The original wired_avoidance.py agent, bug-fixed and kept as a baseline.
    Fixes: removed the undefined/stale `action` reference, normalised the transition model,
    and made it return per-action values so the gate can rank alternatives.
    Unchanged: tabular Q-table + count-based model, reliability = 1/(1+|PE|), epsilon-greedy.
    """

    def __init__(self, rng, n_states=2, n_actions=2, lr=0.1, gamma=0.9):
        self.rng, self.n_states, self.n_actions, self.lr, self.gamma = rng, n_states, n_actions, lr, gamma
        self.Q_habit = np.zeros((n_states, n_actions))                       # model-free system
        self.transition = np.zeros((n_states, n_actions, n_states)) + 0.1    # model-based counts (smoothed)
        self.reward_model = np.zeros((n_states, n_actions))
        self.rel_habit, self.rel_goal = 0.5, 0.5                             # running reliabilities

    @staticmethod
    def discrete_state(util, latency, sla):
        # State 1 = congestion/threat (the original thresholds, with the SLA as the latency bound)
        return 1 if (util >= 85.0 or latency > sla.urllc_latency_ms) else 0

    def _values(self, s):
        q_goal = np.zeros(self.n_actions)
        for a in range(self.n_actions):
            probs = self.transition[s, a] / self.transition[s, a].sum()
            q_goal[a] = self.reward_model[s, a] + self.gamma * probs @ self.Q_habit.max(axis=1)
        w_h = self.rel_habit / (self.rel_habit + self.rel_goal + 1e-8)       # reliability-based arbitration
        return (1 - w_h) * q_goal + w_h * self.Q_habit[s]

    def propose(self, st, sla=SLA_DEFAULT):
        s = self.discrete_state(st.util, st.latency, sla)
        q = self._values(s)
        a = int(self.rng.integers(self.n_actions)) if self.rng.random() < 0.1 else int(np.argmax(q))
        values = np.full(N_ACTIONS, -1e9)
        values[:self.n_actions] = q                                          # action 2 does not exist here
        return Proposal(a, values, {"s": s})

    def observe(self, st_prev, prop, executed, kpm, st_now, sla):
        s, a = prop.extras["s"], min(executed, self.n_actions - 1)
        s2 = self.discrete_state(st_now.util, st_now.latency, sla)
        reward = 1.0 if kpm.urllc_latency_ms <= sla.urllc_latency_ms else -2.0   # original reward
        td_h = reward + self.gamma * self.Q_habit[s2].max() - self.Q_habit[s, a]
        td_g = reward - self.reward_model[s, a]
        self.Q_habit[s, a] += self.lr * td_h
        self.transition[s, a, s2] += 1
        self.reward_model[s, a] += self.lr * td_g
        self.rel_habit = 0.9 * self.rel_habit + 0.1 / (1 + abs(td_h))
        self.rel_goal = 0.9 * self.rel_goal + 0.1 / (1 + abs(td_g))


# ======================================================================
# 4b. NEURAL MODEL: wired.py's PyTorch circuit, fixed and given the policy interface
# ======================================================================
# Changes from wired.py:
#  * Freezing and PFC inhibition now drive behaviour: freezing (BA threat x (1 - PFC
#    inhibition)) adds a status-quo bias to the accumbens logits, as in AvoidanceCircuit.
#    In wired.py both were computed and printed but never used or trained.
#  * The amygdala threat output is trained (binary cross-entropy) to predict an SLA
#    violation, weighted by exposure like the tabular BA. The PFC gate learns through
#    the policy gradient: it is rewarded for releasing action when releasing pays.
#  * Stale-graph bug fixed: wired.py back-propagated through the previous step's graph
#    after optimizer.step() had changed the weights in place, which raises a RuntimeError
#    on the second update. Here the previous state is re-evaluated at update time.
#  * Reward includes each action's eMBB cost (CircuitParams.effort). In wired.py
#    protecting was free, so the agent had no reason ever to stop protecting.
#  * Three actions (ACTIONS) instead of two, and the 6-feature state plus the headroom
#    cue from Perception instead of 4 hand-normalised KPIs.
if HAS_TORCH:
    class AmygdalaModule(nn.Module):
        """Lateral/basal amygdala: state features -> threat representation and violation risk."""

        def __init__(self, input_dim, hidden_dim):
            super().__init__()
            self.feature_extraction = nn.Linear(input_dim, hidden_dim)
            self.threat_effector = nn.Linear(hidden_dim, 1)

        def forward(self, x):
            ba_repr = F.relu(self.feature_extraction(x))
            threat_logit = self.threat_effector(ba_repr).squeeze(-1)
            return threat_logit, ba_repr


    class PrefrontalCortexModule(nn.Module):
        """Infralimbic-like gate: inhibition in [0, 1] that releases action from freezing."""

        def __init__(self, input_dim, hidden_dim):
            super().__init__()
            self.encoder = nn.Linear(input_dim, hidden_dim)
            self.gate = nn.Linear(hidden_dim, 1)

        def forward(self, x):
            pfc_repr = F.relu(self.encoder(x))
            inhibition = torch.sigmoid(self.gate(pfc_repr)).squeeze(-1)
            return inhibition, pfc_repr


    class NucleusAccumbensModule(nn.Module):
        """Accumbens shell: BA + PFC representations -> action preferences."""

        def __init__(self, ba_dim, pfc_dim, action_dim):
            super().__init__()
            self.actor_layer = nn.Sequential(nn.Linear(ba_dim + pfc_dim, 64), nn.ReLU(),
                                             nn.Linear(64, action_dim))

        def forward(self, ba_repr, pfc_repr):
            return self.actor_layer(torch.cat([ba_repr, pfc_repr], dim=-1))


    class WiredAvoidanceActorCritic(nn.Module):
        def __init__(self, input_dim, hidden_dim, action_dim, freeze_gain):
            super().__init__()
            self.amygdala = AmygdalaModule(input_dim, hidden_dim)
            self.pfc = PrefrontalCortexModule(input_dim, hidden_dim)
            self.accumbens = NucleusAccumbensModule(hidden_dim, hidden_dim, action_dim)
            self.critic = nn.Sequential(nn.Linear(hidden_dim * 2, 64), nn.ReLU(), nn.Linear(64, 1))
            self.freeze_gain = freeze_gain
            bias = torch.full((action_dim,), -1.0)
            bias[0] = 1.0                                   # freezing favours the status quo
            self.register_buffer("status_quo_bias", bias)

        def forward(self, x):
            threat_logit, ba_repr = self.amygdala(x)
            inhibition, pfc_repr = self.pfc(x)
            # Threat is detached here so freezing cannot distort the threat estimate itself
            freezing = torch.sigmoid(threat_logit).detach() * (1.0 - inhibition)
            logits = (self.accumbens(ba_repr, pfc_repr)
                      + self.freeze_gain * freezing.unsqueeze(-1) * self.status_quo_bias)
            value = self.critic(torch.cat([ba_repr, pfc_repr], dim=-1)).squeeze(-1)
            return logits, value, threat_logit, freezing, inhibition


class NeuralCircuitPolicy:
    """PyTorch avoidance actor-critic (from wired.py) behind the propose()/observe() interface."""

    def __init__(self, seed=0, hidden_dim=32, lr=5e-3, gamma=0.95, p: CircuitParams = None,
                 entropy_coef=0.01, threat_coef=1.0):
        if not HAS_TORCH:
            raise ImportError("NeuralCircuitPolicy needs PyTorch: pip install torch")
        torch.manual_seed(seed)
        self.p = p or CircuitParams()
        self.gamma, self.entropy_coef, self.threat_coef = gamma, entropy_coef, threat_coef
        self.model = WiredAvoidanceActorCritic(7, hidden_dim, N_ACTIONS, self.p.freeze_gain)
        self.opt = torch.optim.Adam(self.model.parameters(), lr=lr)

    @staticmethod
    def _tensor(st: State):
        return torch.tensor(np.append(st.x, st.x_safe), dtype=torch.float32).unsqueeze(0)

    def propose(self, st):
        with torch.no_grad():
            logits, value, threat_logit, freezing, inhibition = self.model(self._tensor(st))
        action = int(Categorical(logits=logits[0]).sample())
        probs = torch.softmax(logits[0], dim=-1).numpy()
        return Proposal(action, probs, {"threat": float(torch.sigmoid(threat_logit)),
                                        "freezing": float(freezing), "inhibition": float(inhibition)})

    def observe(self, st_prev, prop, executed, kpm, st_now, sla):
        p = self.p
        us = float(kpm.urllc_latency_ms > sla.urllc_latency_ms)
        reward = -p.shock_cost * us - p.effort[executed]
        x_prev, x_now = self._tensor(st_prev), self._tensor(st_now)
        # Fresh graph for the previous state (fixes wired.py's in-place modification error)
        logits, value, threat_logit, _, _ = self.model(x_prev)
        with torch.no_grad():
            _, next_value, _, _, _ = self.model(x_now)
        rpe = reward + self.gamma * next_value - value                    # dopamine RPE
        critic_loss = rpe.pow(2).mean()
        # Threat learning: predict the violation; protection truncates exposure (as in the tabular BA)
        exposure = 1.0 if executed == 0 else p.protect_exposure
        threat_loss = exposure * F.binary_cross_entropy_with_logits(
            threat_logit, torch.tensor([us], dtype=torch.float32))
        loss = critic_loss + self.threat_coef * threat_loss
        # Actor update only for the agent's own choice: a gate override was not sampled from
        # this policy, so its log-probability would bias the policy gradient.
        if executed == prop.action:
            dist = Categorical(logits=logits[0])
            actor_loss = -dist.log_prob(torch.tensor(executed)) * rpe.detach().squeeze()
            loss = loss + actor_loss - self.entropy_coef * dist.entropy()
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()


# ======================================================================
# 5. SAFETY GATE: counterfactual check of every candidate against a digital twin
# ======================================================================
@dataclass
class Prediction:
    latency: float
    embb_tput: float
    safe: bool
    harm: float                   # size of the predicted violation (0 when safe)


@dataclass
class GateDecision:
    action: int
    blocked: bool
    reason: str
    preds: list


class SafetyGate:
    """Independent of the learner: predicts what each action WOULD do, then filters."""

    def __init__(self, sla=SLA_DEFAULT, twin_model=TWIN_MODEL, margin=0.10):
        self.sla, self.twin, self.margin = sla, twin_model, margin

    def predict(self, st: State, a: int) -> Prediction:
        cfg = ACTIONS[a]
        lat, tput, *_ = schedule(st.du_hat, st.de_hat, cfg.urllc_min, cfg.embb_max, self.twin)
        # URLLC must stay inside its bound with a safety margin; eMBB must keep its guaranteed rate
        lat_ok = lat <= self.sla.urllc_latency_ms * (1 - self.margin)
        tput_ok = tput >= self.sla.embb_gbr_mbps
        harm = max(0.0, lat / self.sla.urllc_latency_ms - 1) + max(0.0, 1 - tput / self.sla.embb_gbr_mbps)
        return Prediction(lat, tput, lat_ok and tput_ok, harm)

    def filter(self, prop: Proposal, st: State) -> GateDecision:
        preds = [self.predict(st, a) for a in range(N_ACTIONS)]       # counterfactual for EVERY action
        safe = [a for a, p in enumerate(preds) if p.safe]
        if prop.action in safe:
            return GateDecision(prop.action, False, "ok", preds)
        if safe:                                                       # best-valued safe alternative
            return GateDecision(max(safe, key=lambda a: prop.values[a]), True, "unsafe proposal", preds)
        # Nothing predicted safe: fail toward the least predicted harm
        return GateDecision(min(range(N_ACTIONS), key=lambda a: preds[a].harm), True,
                            "no safe alternative", preds)


class NoGate:
    """Pass-through used for the ungated variants."""

    def filter(self, prop, st):
        return GateDecision(prop.action, False, "ungated", [])


# ======================================================================
# THE xAPP: steps 1-8 in order
# ======================================================================
class SlicingXApp:
    def __init__(self, ric: MockFlexRIC, policy, gate, sla=SLA_DEFAULT, name="avoidance_slicing_xapp"):
        self.ric, self.policy, self.gate, self.sla = ric, policy, gate, sla
        self.perception = Perception(sla)
        self.prev = None                                   # (state, proposal, executed action)
        self.log = []
        ric.init_xapp(name)

    def step(self):
        # Steps 1-2: receive the KPM indication forwarded by the RIC
        kpm = self.ric.poll_indication()
        if kpm is None:                                    # live RIC timed out: keep the current quota
            return None
        # Step 3: perception, telemetry -> state tensor
        st = self.perception.to_state(kpm)
        # Credit assignment: this KPM reports the outcome of the previous decision
        if self.prev is not None:
            p_state, p_prop, p_exec = self.prev
            self.policy.observe(p_state, p_prop, p_exec, kpm, st, self.sla)
        # Step 4: neural model proposes an action from its risk estimate
        prop = self.policy.propose(st)
        # Step 5: safety gate checks the proposal (and all alternatives) counterfactually
        decision = self.gate.filter(prop, st)
        # Step 6: final action selection -> slice PRB quotas
        action = decision.action
        cfg = ACTIONS[action]
        # Steps 7-8: build the E2-RC message; the RIC dispatches it to the gNB scheduler
        msg = RcControl(slices=[{"id": 1, "min_prb": cfg.urllc_min, "max_prb": URLLC_MAX},
                                {"id": 2, "min_prb": 20, "max_prb": cfg.embb_max}])
        self.ric.send_rc_control(msg)
        self.prev = (st, prop, action)
        self.log.append(dict(t=kpm.t, proposed=prop.action, executed=action, blocked=decision.blocked,
                             reason=decision.reason,
                             urllc_viol=kpm.urllc_latency_ms > self.sla.urllc_latency_ms,
                             embb_viol=kpm.embb_tput_mbps < self.sla.embb_gbr_mbps,
                             embb_tput=kpm.embb_tput_mbps, util=kpm.dl_prb_util,
                             latency=kpm.urllc_latency_ms))
        return kpm


# ======================================================================
# EXPERIMENTS
# ======================================================================
def make_circuit_policy(seed, p=None):
    rng = np.random.default_rng(seed + 1000)
    circuit = AvoidanceCircuit(6, N_ACTIONS, 3, p or CircuitParams(), rng)
    return CircuitPolicy(circuit, rng)


PRETRAIN_STEPS = {"circuit": 800, "neural": 3000}   # the network needs more sandbox experience


def make_policy(kind, seed, circuit_params=None):
    """Build a learning policy by name, pre-trained in the sandbox where it needs it."""
    if kind == "circuit":
        policy = make_circuit_policy(seed, circuit_params)
    elif kind == "neural":
        policy = NeuralCircuitPolicy(seed=seed, p=circuit_params)
    elif kind == "legacy_pe":
        return PEBasedArbitrationAgent(np.random.default_rng(seed + 2000))
    elif kind == "static":
        return StaticPolicy()
    else:
        raise ValueError(kind)
    pretrain(policy, seed, PRETRAIN_STEPS[kind])
    return policy


def pretrain(policy, seed, steps=800):
    """Sandbox training on the digital twin: violations are free there, so no gate is used."""
    rng = np.random.default_rng(seed + 5000)
    ran = MockRAN(train_profile, rng, REAL_MODEL)
    app = SlicingXApp(MockFlexRIC(ran), policy, NoGate())
    for _ in range(steps):
        app.step()


def build_variant(name, seed, circuit_params=None):
    """Return a fresh xApp on the mocked RIC for a variant named '<policy>' or '<policy>+gate'."""
    if name == "gate_only":
        kind, gated = "static", True
    else:
        kind, _, suffix = name.partition("+")
        gated = suffix == "gate"
    policy = make_policy(kind, seed, circuit_params)
    gate = SafetyGate() if gated else NoGate()
    ran = MockRAN(eval_profile, np.random.default_rng(seed), REAL_MODEL)
    return SlicingXApp(MockFlexRIC(ran), policy, gate)


WINDOWS = {"surge1": (300, 400), "calm1": (400, 700), "surge2": (700, 800), "calm2": (800, 1000)}


def run_variant(name, seed, steps=1000, circuit_params=None):
    app = build_variant(name, seed, circuit_params)
    for _ in range(steps):
        app.step()
    return app.log


def summarize(logs):
    """Average metrics over seeds. Violation rates in surges, protection (over-blocking) in calms."""
    def rate(key, lo, hi, f=lambda v: float(v)):
        return float(np.mean([np.mean([f(r[key]) for r in log[lo:hi]]) for log in logs]))
    out = {}
    for w in ("surge1", "surge2"):
        out[f"{w}_urllc_viol"] = rate("urllc_viol", *WINDOWS[w])
    for w in ("calm1", "calm2"):
        out[f"{w}_protect"] = rate("executed", *WINDOWS[w], f=lambda a: float(a > 0))
    out["urllc_viol_all"] = rate("urllc_viol", 0, 1000)
    out["embb_viol_all"] = rate("embb_viol", 0, 1000)
    out["embb_tput"] = rate("embb_tput", 0, 1000)
    out["blocked"] = rate("blocked", 0, 1000)
    out["proposed_protect_surges"] = float(np.mean([np.mean(
        [r["proposed"] > 0 for w in ("surge1", "surge2") for r in log[WINDOWS[w][0]:WINDOWS[w][1]]]) for log in logs]))
    return out


def experiment_compare(n_seeds=10):
    names = ["static", "legacy_pe", "gate_only", "legacy_pe+gate", "circuit", "circuit+gate"]
    if HAS_TORCH:
        names += ["neural", "neural+gate"]
    return {n: summarize([run_variant(n, s) for s in range(n_seeds)]) for n in names}


def print_comparison(res):
    cols = [("surge1_urllc_viol", "viol s1"), ("surge2_urllc_viol", "viol s2"),
            ("calm1_protect", "prot c1"), ("calm2_protect", "prot c2"),
            ("embb_viol_all", "eMBB viol"), ("embb_tput", "eMBB Mbps"), ("blocked", "gate blk")]
    print(f"{'variant':16s}" + "".join(f"{h:>11s}" for _, h in cols))
    for n, m in res.items():
        print(f"{n:16s}" + "".join(f"{m[k]:11.2f}" for k, _ in cols))
    print("\nviol s1/s2: URLLC SLA violation rate in surge 1 / unseen surge 2")
    print("prot c1/c2: fraction of calm steps spent in a protective quota (over-protection)")
    print("gate blk  : fraction of all steps where the gate overrode the proposal")


# ======================================================================
# CLOSED-LOOP RUNTIME (from wired.py): demo on the mock RAN, or live on FlexRIC
# ======================================================================
def describe(app, kpm):
    """One telemetry line per step, as wired.py printed."""
    r = app.log[-1]
    extra = app.prev[1].extras
    neural = (f" | threat {extra['threat']:.2f} freeze {extra['freezing']:.2f} "
              f"inhib {extra['inhibition']:.2f}") if "threat" in extra else ""
    gate = f" | GATE: {r['reason']}" if r["blocked"] else ""
    return (f"[t={kpm.t:4d}] PRB {kpm.dl_prb_util:5.1f}% | URLLC {kpm.urllc_latency_ms:5.1f} ms | "
            f"eMBB {kpm.embb_tput_mbps:5.1f} Mbps | proposed {ACTIONS[r['proposed']].name:8s} "
            f"-> executed {ACTIONS[r['executed']].name:8s}{gate}{neural}")


def run_closed_loop(ric, policy, gate, period_s=0.5, max_steps=None, verbose=True):
    app = SlicingXApp(ric, policy, gate)
    steps = 0
    try:
        while max_steps is None or steps < max_steps:
            kpm = app.step()
            if kpm is not None and verbose:
                print(describe(app, kpm))
            steps += 1
            if period_s:
                time.sleep(period_s)
    except KeyboardInterrupt:
        print("\n[xApp] Interrupted.")
    finally:
        print("[xApp] Freeing RIC resources.")
        ric.close()
    return app.log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["sim", "demo", "live"], default="sim")
    ap.add_argument("--policy", choices=["circuit", "neural", "legacy_pe", "static"], default="circuit")
    ap.add_argument("--no-gate", action="store_true", help="disable the counterfactual safety gate")
    ap.add_argument("--seeds", type=int, default=10, help="seeds for --mode sim")
    ap.add_argument("--steps", type=int, default=1000, help="steps for --mode demo")
    ap.add_argument("--period", type=float, default=None, help="seconds between polls (demo 0, live 0.5)")
    args = ap.parse_args()

    if args.mode == "sim":
        print_comparison(experiment_compare(args.seeds))
        if not HAS_TORCH:
            print("(neural variants skipped: PyTorch is not installed)")
        return

    policy = make_policy(args.policy, seed=0)          # pre-trained in the sandbox first
    gate = NoGate() if args.no_gate else SafetyGate()
    if args.mode == "demo":
        ric = MockFlexRIC(MockRAN(eval_profile, np.random.default_rng(0), REAL_MODEL))
        period = 0.0 if args.period is None else args.period
        log = run_closed_loop(ric, policy, gate, period, args.steps)
        print_comparison({f"{args.policy}{'' if args.no_gate else '+gate'}": summarize([log])})
    else:
        if args.no_gate:
            print("[xApp] WARNING: running live without the safety gate.")
        ric = FlexRICAdapter()
        run_closed_loop(ric, policy, gate, 0.5 if args.period is None else args.period)


if __name__ == "__main__":
    main()
