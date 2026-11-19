"""
Integrated model of the amygdala / prefrontal / accumbens avoidance circuit.

Mechanisms implemented
  1. Freezing (CeA output) and avoidance (BA -> NAc) are SEPARATE outputs that COMPETE.
  2. Two-factor learning: Pavlovian fear is learned first; avoidance is then
     reinforced by FEAR REDUCTION (relief), not by shock delivery.
  3. Safety-signal pathway (vHPC -> PL) that suppresses fear to a safety cue,
     learned from "expected shock that did not occur".
  4. Infralimbic gate (IL -> ITC) that suppresses freezing but spares the
     BA -> NAc motivational route, and grows with successful avoidance.
  5. Environment where the threat can be removed, so persistence can be tested.
  6. Goal-directed vs habitual arbitration driven by each system's recent
     reliability (prediction error), not by a trial counter.

Run:  python avoidance_circuit.py
"""
import numpy as np
from dataclasses import dataclass

# Action indices: 0 = wait (freeze / do nothing), 1 = active avoidance
WAIT, AVOID = 0, 1
# Cue feature indices: [tone, safety cue, context]
TONE, SAFE, CTX = 0, 1, 2


@dataclass
class Params:
    # --- learning rates ---
    lr_ba: float = 0.10       # BA fear learning (Rescorla-Wagner style)
    lr_safe: float = 0.10     # vHPC -> PL safety learning
    lr_il: float = 0.10       # IL gate growth with successful avoidance
    lr_hab: float = 0.10      # habit (model-free) value learning, driven by dopamine RPE
    lr_model: float = 0.10    # goal-directed outcome-model learning
    # --- value terms ---
    shock_cost: float = 1.0   # aversiveness of the shock
    effort: float = 0.3       # cost of making the avoidance response
    relief_gain: float = 1.0  # how much fear reduction is worth
    # --- action selection ---
    beta: float = 5.0         # inverse temperature on action values
    freeze_gain: float = 8.0  # strength of freezing competing with avoidance
    eps: float = 0.05         # random exploration
    avoid_exposure: float = 0.05  # fraction of the cue experienced if avoidance ends it early
    # --- arbitration ---
    arb_tau: float = 0.05     # smoothing of each system's running error
    arb_k: float = 20.0       # sharpness of the arbitration sigmoid
    mb_cost: float = 0.02     # computational cost that biases control toward habit
    # --- lesions (for ablation) ---
    il_enabled: bool = True
    pl_enabled: bool = True


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class AvoidanceAgent:
    def __init__(self, p: Params, rng: np.random.Generator):
        self.p, self.rng = p, rng
        # BA associative weights over [tone, safety, context]; safety weight is
        # masked out because safety is learned in the PL pathway instead
        self.w_ba = np.zeros(3)
        self.alpha = np.array([1.0, 0.0, 0.1])  # feature salience (context is weak)
        self.w_safe = 0.0                        # vHPC -> PL safety strength
        self.il_gate = 0.0                       # IL suppression of CeA freezing
        # Habit system: cached values per (cue type, action)
        self.q_hab = np.zeros((2, 2))
        # Goal-directed system: learned P(shock | cue type, action), uncertain start
        self.p_shock = np.full((2, 2), 0.5)
        # Running prediction errors for each system (reliability tracking)
        self.err_mb, self.err_hab = 0.3, 0.3

    # ---------------- circuit read-outs ----------------
    def amygdala(self, x):
        """BA fear, PL safety gate, and gated CeA freezing for cue vector x."""
        fear_raw = float(np.clip(self.w_ba @ (x * np.array([1, 0, 1])), 0, 1))
        # vHPC -> PL: safety cue scales down BA fear
        gate_pl = float(np.clip(self.w_safe * x[SAFE], 0, 1)) if self.p.pl_enabled else 0.0
        fear_ba = fear_raw * (1 - gate_pl)
        # IL -> ITC: suppresses CeA freezing only (BA -> NAc motivation is spared)
        freeze = fear_ba * (1 - self.il_gate)
        return fear_raw, gate_pl, fear_ba, freeze

    def context_fear(self):
        """Fear that remains once the cue is gone (the post-avoidance 'safe' state)."""
        return float(np.clip(self.w_ba[CTX], 0, 1))

    def arbitration_weight(self):
        """Habit weight: rises when habit is at least as reliable as the model."""
        return sigmoid(self.p.arb_k * (self.err_mb - self.err_hab + self.p.mb_cost))

    def policy(self, x, k):
        """Return action probabilities plus quantities needed for learning/logging."""
        p = self.p
        fear_raw, gate_pl, fear_ba, freeze = self.amygdala(x)
        # Goal-directed values from the outcome model and current fear (relief expectation)
        exp_relief = np.array([0.0, max(0.0, fear_ba - self.context_fear())])
        effort = np.array([0.0, p.effort])
        q_mb = -p.shock_cost * self.p_shock[k] - effort + p.relief_gain * exp_relief
        # Habit values are cached; arbitration blends the two
        w_h = self.arbitration_weight()
        q = (1 - w_h) * q_mb + w_h * self.q_hab[k]
        # Freezing biases the choice toward WAIT and away from AVOID (competition)
        logits = p.beta * q + p.freeze_gain * freeze * np.array([1.0, -1.0])
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        probs = (1 - p.eps) * probs + p.eps * 0.5
        return dict(probs=probs, q_mb=q_mb, w_habit=w_h, fear_raw=fear_raw,
                    gate_pl=gate_pl, fear_ba=fear_ba, freeze=freeze)

    # ---------------- learning ----------------
    def learn(self, x, k, a, us, exposure, info):
        """Update every plastic site after one trial. Returns the dopamine RPE."""
        p = self.p
        fear_ba = info["fear_ba"]
        # Relief = fear drop when avoidance ends the cue (two-factor reinforcement)
        relief = max(0.0, fear_ba - self.context_fear()) if a == AVOID else 0.0
        effort = p.effort if a == AVOID else 0.0
        r = -p.shock_cost * us - effort + p.relief_gain * relief

        # Dopamine RPE trains the habit system
        dopamine = r - self.q_hab[k, a]
        # Reliability tracking for arbitration (errors before updating)
        e_mb, e_hab = abs(r - info["q_mb"][a]), abs(dopamine)
        self.err_mb += p.arb_tau * (e_mb - self.err_mb)
        self.err_hab += p.arb_tau * (e_hab - self.err_hab)
        self.q_hab[k, a] += p.lr_hab * dopamine

        # Goal-directed outcome model: only learns about the action that was taken
        self.p_shock[k, a] += p.lr_model * (us - self.p_shock[k, a])

        # BA fear learning, scaled by how much of the cue was actually experienced
        err = us - fear_ba
        self.w_ba += p.lr_ba * err * (1 - info["gate_pl"]) * self.alpha * x * exposure

        # vHPC -> PL: strengthen when fear was expected but shock was omitted
        if p.pl_enabled:
            self.w_safe -= p.lr_safe * err * info["fear_raw"] * x[SAFE] * exposure
            self.w_safe = float(np.clip(self.w_safe, 0, 1))

        # IL gate grows with successful (relief-producing) avoidance
        if p.il_enabled and a == AVOID and relief > 0:
            self.il_gate += p.lr_il * (1 - self.il_gate)
        return dopamine


# ---------------- environment ----------------
def cue_vector(safety=False):
    """Tone is always on; safety cue optionally accompanies it; context always present."""
    return np.array([1.0, float(safety), 1.0])


def run_trial(agent, safety=False, shock_prob=1.0, avoid_allowed=True, learn=True):
    """One signaled-avoidance trial. Returns a dict of logged quantities."""
    p = agent.p
    x = cue_vector(safety)
    k = int(safety)  # cue-type index: 0 = tone, 1 = tone + safety
    info = agent.policy(x, k)
    # Choose an action; if avoidance is blocked the agent is forced to wait
    a = AVOID if (avoid_allowed and agent.rng.random() < info["probs"][AVOID]) else WAIT
    if a == AVOID:
        us, exposure = 0.0, p.avoid_exposure  # tone terminated early, shock escaped
    else:
        # Shock only if the cue is dangerous (no safety cue) and the threat is still active
        us = float(agent.rng.random() < shock_prob) if not safety else 0.0
        exposure = 1.0
    dopamine = agent.learn(x, k, a, us, exposure, info) if learn else 0.0
    return dict(avoid=a == AVOID, freeze=info["freeze"], fear=info["fear_ba"],
                w_habit=info["w_habit"], il=agent.il_gate, da=dopamine,
                p_avoid=info["probs"][AVOID])


def run_phase(agent, n, **kw):
    logs = [run_trial(agent, **kw) for _ in range(n)]
    return {key: np.array([l[key] for l in logs], dtype=float) for key in logs[0]}


def block_means(log, key, size):
    return log[key].reshape(-1, size).mean(axis=1)


# ---------------- experiments ----------------
def experiment_avoidance(n_seeds=30, **param_overrides):
    """Pavlovian fear -> avoidance training -> threat removed (avoidance available)."""
    out = {k: [] for k in ["avoid_train", "freeze_train", "avoid_ext", "fear_ext",
                           "habit_ext", "il_ext"]}
    for s in range(n_seeds):
        agent = AvoidanceAgent(Params(**param_overrides), np.random.default_rng(s))
        # Phase 1: Pavlovian conditioning, avoidance unavailable
        run_phase(agent, 60, avoid_allowed=False)
        # Phase 2: avoidance training, shock if the agent waits
        tr = run_phase(agent, 400, shock_prob=1.0)
        # Phase 3: threat removed, avoidance still available
        ex = run_phase(agent, 400, shock_prob=0.0)
        out["avoid_train"].append(block_means(tr, "avoid", 50))
        out["freeze_train"].append(block_means(tr, "freeze", 50))
        out["avoid_ext"].append(block_means(ex, "avoid", 50))
        out["fear_ext"].append(block_means(ex, "fear", 50))
        out["habit_ext"].append(block_means(ex, "w_habit", 50))
        out["il_ext"].append(block_means(ex, "il", 50))
    return {k: np.mean(v, axis=0) for k, v in out.items()}


def experiment_fear_after_removal(avoid_allowed, n_seeds=30):
    """BA fear during threat removal, with avoidance either available or blocked."""
    fear = []
    for s in range(n_seeds):
        agent = AvoidanceAgent(Params(), np.random.default_rng(s))
        run_phase(agent, 60, avoid_allowed=False)
        run_phase(agent, 400, shock_prob=1.0)
        ex = run_phase(agent, 200, shock_prob=0.0, avoid_allowed=avoid_allowed)
        fear.append(block_means(ex, "fear", 50))
    return np.mean(fear, axis=0)


def experiment_safety(n_seeds=30, pl_enabled=True):
    """Conditioned inhibition: tone -> shock, tone + safety cue -> no shock."""
    res = []
    for s in range(n_seeds):
        agent = AvoidanceAgent(Params(pl_enabled=pl_enabled), np.random.default_rng(s))
        run_phase(agent, 60, avoid_allowed=False)  # Pavlovian fear to the tone
        for _ in range(120):                       # alternate danger / safety trials
            run_trial(agent, safety=False, avoid_allowed=False)
            run_trial(agent, safety=True, avoid_allowed=False)
        # Read out (no learning): amygdala state for tone vs tone + safety cue
        t = agent.policy(cue_vector(False), 0)
        c = agent.policy(cue_vector(True), 1)
        res.append((t["freeze"], c["freeze"], t["fear_ba"], c["fear_ba"]))
    return np.mean(res, axis=0)


if __name__ == "__main__":
    np.set_printoptions(linewidth=120)
    print("=== 1. Intact circuit: avoidance acquisition, then threat removed ===")
    r = experiment_avoidance()
    print("Avoid rate, training (blocks of 50)       :", np.round(r["avoid_train"], 2))
    print("Freezing,   training (blocks of 50)       :", np.round(r["freeze_train"], 2))
    print("Avoid rate, threat removed (blocks of 50) :", np.round(r["avoid_ext"], 2))
    print("BA fear,    threat removed (blocks of 50) :", np.round(r["fear_ext"], 2))
    print("Habit wt,   threat removed (blocks of 50) :", np.round(r["habit_ext"], 2))
    print("IL gate,    threat removed (blocks of 50) :", np.round(r["il_ext"], 2))
    print("(avoid rate settles near 0.2: the floor from the effort cost + exploration)")

    print("\n=== 2. IL lesion: freezing is never gated ===")
    r = experiment_avoidance(il_enabled=False)
    print("Avoid rate, training (blocks of 50)       :", np.round(r["avoid_train"], 2))
    print("Freezing,   training (blocks of 50)       :", np.round(r["freeze_train"], 2))

    print("\n=== 3. Does avoidance protect fear from extinction? (BA fear, blocks of 50) ===")
    print("Threat removed, avoidance allowed :", np.round(experiment_fear_after_removal(True), 2))
    print("Threat removed, avoidance blocked :", np.round(experiment_fear_after_removal(False), 2))

    print("\n=== 4. Safety signal (conditioned inhibition) ===")
    for label, flag in [("PL pathway intact", True), ("PL pathway lesioned", False)]:
        f_t, f_c, b_t, b_c = experiment_safety(pl_enabled=flag)
        print(f"{label:20s} freezing: tone={f_t:.2f} tone+safety={f_c:.2f} | "
              f"BA fear: tone={b_t:.2f} tone+safety={b_c:.2f}")
