import torch
import torch.nn as nn
import torch.nn.functional as F

class AmygdalaModule(nn.Module):
    """
    Simulates LA -> BA -> CeA pathway. 
    Processes sensory input and outputs a baseline threat/freezing reaction.
    """
    def __init__(self, input_dim, hidden_dim):
        super().__init__()
        self.feature_extraction = nn.Linear(input_dim, hidden_dim) # Lateral/Basal Amygdala
        self.threat_effector = nn.Linear(hidden_dim, 1)          # Central Amygdala (Freezing output)

    def forward(self, x):
        ba_representation = F.relu(self.feature_extraction(x))
        freezing_response = torch.sigmoid(self.threat_effector(ba_representation))
        return freezing_response, ba_representation


class PrefrontalCortexModule(nn.Module):
    """
    Simulates the Infralimbic/Prelimbic Cortex.
    Provides top-down inhibition to suppress amygdala-driven freezing and process safety cues.
    """
    def __init__(self, input_dim, hidden_dim):
        super().__init__()
        self.pfc_gate = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid() # Outputs an inhibition factor between 0 and 1
        )

    def forward(self, x):
        # Returns an inhibitory gain signal to suppress freezing
        return self.pfc_gate(x)


class NucleusAccumbensModule(nn.Module):
    """
    Simulates the Nucleus Accumbens Shell/Core and striatal loops.
    Handles active avoidance action selection and receives dopamine/relief signals.
    """
    def __init__(self, ba_dim, pfc_dim, action_dim):
        super().__init__()
        # Combines amygdalar drive and prefrontal context for active avoidance policy
        self.actor = nn.Sequential(
            nn.Linear(ba_dim + pfc_dim, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim) # e.g., [Do Nothing, Active Avoidance Action]
        )

    def forward(self, ba_repr, pfc_repr):
        combined = torch.cat([ba_repr, pfc_repr], dim=-1)
        action_logits = self.actor(combined)
        return action_logits


class AvoidanceCircuitModel(nn.Module):
    """
    Integrates Amygdala, PFC, and Accumbens into a unified network.
    """
    def __init__(self, input_dim, hidden_dim, action_dim):
        super().__init__()
        self.amygdala = AmygdalaModule(input_dim, hidden_dim)
        self.pfc = PrefrontalCortexModule(input_dim, hidden_dim)
        self.accumbens = NucleusAccumbensModule(hidden_dim, hidden_dim, action_dim)

    def forward(self, sensory_cue):
        # 1. Amygdala processes raw threat cues
        freezing, ba_repr = self.amygdala(sensory_cue)
        
        # 2. Prefrontal cortex evaluates context and outputs top-down inhibition
        inhibition_factor = self.pfc(sensory_cue)
        
        # Modulate freezing: PFC inhibition suppresses amygdala-driven freezing
        modulated_freezing = freezing * (1.0 - inhibition_factor)
        
        # 3. Accumbens evaluates active avoidance options based on BA and PFC states
        pfc_repr = F.relu(self.pfc.pfc_gate[0](sensory_cue)) # Feature representation from PFC
        action_logits = self.accumbens(ba_repr, pfc_repr)
        
        return {
            "freezing_response": modulated_freezing,
            "pfc_inhibition": inhibition_factor,
            "action_logits": action_logits
        }


import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

class AvoidanceActorCritic(nn.Module):
    """
    Combines the Amygdala, PFC, and Accumbens into an Actor-Critic architecture
    trained via Reinforcement Learning with a Dopamine RPE signal.
    """
    def __init__(self, input_dim, hidden_dim, action_dim):
        super().__init__()
        # Amygdala & PFC feature extractors
        self.amygdala_feature = nn.Linear(input_dim, hidden_dim)
        self.pfc_gate = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid()
        )
        
        # Actor: Nucleus Accumbens selects actions (e.g., 0: Freeze/Do Nothing, 1: Active Avoidance)
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim * 2, 64),
            nn.ReLU(),
            nn.Linear(64, action_dim)
        )
        
        # Critic: Estimates expected value (safety vs. threat state value)
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim * 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1)
        )

    def forward(self, x):
        ba_repr = F.relu(self.amygdala_feature(x))
        pfc_val = self.pfc_gate(x)
        
        # Combine representations for decision making
        combined = torch.cat([ba_repr, pfc_val.expand(-1, ba_repr.size(1))], dim=-1)
        
        action_logits = self.actor(combined)
        state_value = self.critic(combined)
        
        return action_logits, state_value

# --- Simulated Training Loop with Dopamine RPE ---

input_dim = 10
action_dim = 2
model = AvoidanceActorCritic(input_dim, hidden_dim=32, action_dim=action_dim)
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

# Hyperparameters
gamma = 0.99  # Discount factor for future safety/threat outcomes

# Simulate a training episode
state = torch.randn(1, input_dim) # Sensory cue (e.g., warning tone)
done = False

print("--- Starting Avoidance RL Training Episode ---")

# 1. Model chooses an action (e.g., Active Avoidance vs Freezing)
action_logits, state_value = model(state)
dist = Categorical(logits=action_logits)
action = dist.sample()
log_prob = dist.log_prob(action)

# 2. Environment response simulation
# If action == 1 (Avoidance) and threat was present -> Success! Reward = +1.0 (Relief/Safety)
# If action == 0 (Freezing) and threat was present -> Failure/Shock -> Reward = -1.0
simulated_reward = 1.0 if action.item() == 1 else -1.0
next_state = torch.randn(1, input_dim)

with torch.no_grad():
    _, next_state_value = model(next_state)

# 3. Compute Dopamine Reward Prediction Error (RPE)
# RPE = Actual Reward + Discounted Next Value - Current Expected Value
reward_tensor = torch.tensor([simulated_reward], dtype=torch.float32)
rpe = reward_tensor + gamma * next_state_value - state_value
dopamine_signal = rpe.item() # Biological correlate: transient dopamine burst/dip

print(f"Action Taken: {'Active Avoidance' if action.item() == 1 else 'Freezing'}")
print(f"Reward Received: {simulated_reward}")
print(f"Computed Dopamine RPE (Signal): {dopamine_signal:.4f}")

# 4. Actor-Loss and Critic-Loss optimization using the RPE
actor_loss = -log_prob * rpe.detach()         # Reinforces actions that generated positive dopamine
critic_loss = F.mse_loss(state_value, reward_tensor + gamma * next_state_value)
total_loss = actor_loss + critic_loss

optimizer.zero_grad()
total_loss.backward()
optimizer.step()

print("Model weights updated via Dopamine-driven RPE feedback loop successfully!")

# --- Example instantiation ---
model = AvoidanceCircuitModel(input_dim=10, hidden_dim=32, action_dim=2)
dummy_cue = torch.randn(1, 10) # Batch of 1 sensory input
outputs = model(dummy_cue)
print("Model Outputs:", outputs)

import numpy as np

class DualSystemAvoidanceAgent:
    def __init__(self, n_states, n_actions, learning_rate=0.1, gamma=0.9):
        self.n_states = n_states
        self.n_actions = n_actions
        self.lr = learning_rate
        self.gamma = gamma

        # 1. Model-Free (Habitual) Q-Table -> Dorsolateral Striatum
        self.Q_habit = np.zeros((n_states, n_actions))

        # 2. Model-Based (Goal-Directed) Transition & Reward models -> Prefrontal/DMS
        self.transition_model = np.zeros((n_states, n_actions, n_states)) # T(s' | s, a)
        self.reward_model = np.zeros((n_states, n_actions))               # R(s, a)

        # 3. Arbitration weight (0 = fully goal-directed, 1 = fully habitual)
        self.habit_weight = 0.0
        self.trial_count = 0

    def update_models(self, state, action, reward, next_state):
        self.trial_count += 1

        # --- Update Model-Free (Habit) System (Q-learning) ---
        best_next_q = np.max(self.Q_habit[next_state])
        td_error = reward + self.gamma * best_next_q - self.Q_habit[state, action]
        self.Q_habit[state, action] += self.lr * td_error

        # --- Update Model-Based (Goal-Directed) System ---
        # Increment transition counts and normalize
        self.transition_model[state, action, next_state] += 1
        self.reward_model[state, action] += self.lr * (reward - self.reward_model[state, action])

        # --- Mathematically Drive the Striatal Takeover ---
        # The habit weight increases asymptotically toward 1.0 as a function of training repetition/trials.
        # Biologically, this reflects chunking or uncertainty reduction over extended overtraining.
        self.habit_weight = 1.0 - np.exp(-0.005 * self.trial_count)

    def select_action(self, state):
        # Compute Goal-Directed Q-values from the Model-Based tree search / Bellman backup
        # For simplicity, estimated via expected 1-step model lookahead:
        Q_goal = self.reward_model[state] + self.gamma * np.sum(
            self.transition_model[state] * np.max(self.Q_habit, axis=1), axis=1
        )

        # Blended value combining Goal-Directed and Habitual systems
        Q_combined = (1.0 - self.habit_weight) * Q_goal + self.habit_weight * self.Q_habit[state]

        # Epsilon-greedy action selection
        if np.random.rand() < 0.1:
            return np.random.choice(self.n_actions)
        return np.argmax(Q_combined)

# --- Simulation Run ---
agent = DualSystemAvoidanceAgent(n_states=2, n_actions=2)
state = 0

print("--- Simulating Training Trials (Goal-Directed -> Habitual Transition) ---")
for trial in range(1, 1001):
    action = agent.select_action(state)
    # Simulate environment: action 1 (avoidance) yields reward +1, next state 1
    next_state = 1 if action == 1 else 0
    reward = 1.0 if action == 1 else -1.0

    agent.update_models(state, action, reward, next_state)

    if trial % 200 == 0:
        print(f"Trial {trial:4d} | Habit Weight (W): {agent.habit_weight:.3f} (System is {'Habitual' if agent.habit_weight > 0.5 else 'Goal-Directed'})")


import time
import sys
import numpy as np
import flexric

# ==========================================================
# 1. PE-BASED DUAL-SYSTEM ARBITRATION AGENT
# ==========================================================
class PEBasedArbitrationAgent:
    def __init__(self, n_states=2, n_actions=2, learning_rate=0.1, gamma=0.9):
        self.n_states = n_states
        self.n_actions = n_actions
        self.lr = learning_rate
        self.gamma = gamma
        
        # Model-Free (Habitual) Q-Table -> Dorsolateral Striatum analogue
        self.Q_habit = np.zeros((n_states, n_actions))
        
        # Model-Based (Goal-Directed) System -> Prefrontal / DMS analogue
        self.transition_model = np.zeros((n_states, n_actions, n_states)) + 0.1 # Laplace smoothing
        self.reward_model = np.zeros((n_states, n_actions))
        
        # Reliability tracking for dynamic arbitration
        self.reliability_habit = 0.5
        self.reliability_goal = 0.5

    def update_models(self, state, action, reward, next_state):
        # Model-Free TD Update & Error
        best_next_q = np.max(self.Q_habit[next_state])
        td_error_habit = reward + self.gamma * best_next_q - self.Q_habit[state, action]
        self.Q_habit[state, action] += self.lr * td_error_habit
        
        # Model-Based Update & Error
        expected_reward = self.reward_model[state, action]
        td_error_goal = reward - expected_reward
        
        self.transition_model[state, action, next_state] += 1
        self.reward_model[state, action] += self.lr * (reward - self.reward_model[state, action])
        
        # Update system reliabilities based on prediction errors (surprise reduction)
        self.reliability_habit = 0.9 * self.reliability_habit + 0.1 * (1.0 / (1.0 + abs(td_error_habit)))
        self.reliability_goal = 0.9 * self.reliability_goal + 0.1 * (1.0 / (1.0 + abs(td_error_goal)))

    def select_action(self, state):
        # Compute Goal-Directed Q-values using internal transition and reward models
        # Sum over possible next states weighted by transition probabilities
        transition_probs = self.transition_model[state, action] / np.sum(self.transition_model[state, action]) if np.sum(self.transition_model[state, action]) > 0 else np.ones(self.n_states) / self.n_states
        
        Q_goal = np.zeros(self.n_actions)
        for a in range(self.n_actions):
            expected_next_state_value = np.sum(self.transition_model[state, a] / np.sum(self.transition_model[state, a]) * np.max(self.Q_habit, axis=1))
            Q_goal[a] = self.reward_model[state, a] + self.gamma * expected_next_state_value

        # Dynamic Arbitration Weight (W_habit)
        total_reliability = self.reliability_habit + self.reliability_goal
        habit_weight = self.reliability_habit / (total_reliability + 1e-8)
        
        # Blended value combining goal-directed and habitual systems
        Q_combined = (1.0 - habit_weight) * Q_goal + habit_weight * self.Q_habit[state]
        
        # Epsilon-greedy exploration
        if np.random.rand() < 0.1:
            return np.random.choice(self.n_actions), habit_weight
            
        return np.argmax(Q_combined), habit_weight

# ==========================================================
# 2. MAIN XAPP RUNTIME LOOP WITH FLEXRIC
# ==========================================================
def main():
    print("==========================================================")
    print("Starting PE-Driven Slicing xApp: FlexRIC + OAI Integration")
    print("==========================================================")
    
    # Initialize connection to Near-RT RIC
    xapp = flexric.init_xapp("pe_slicing_xapp")
    
    # Instantiate the dual-system arbitration agent
    agent = PEBasedArbitrationAgent(n_states=2, n_actions=2)
    
    # Slice configuration states
    current_slices = {
        "URLLC": {"id": 1, "min_prb": 10, "max_prb": 30},
        "EMBB":  {"id": 2, "min_prb": 20, "max_prb": 90}
    }
    
    # Track previous state for reinforcement learning transition updates
    prev_state = 0
    prev_action = 0

    print("[xApp] Entering closed-loop PE arbitration execution...")

    try:
        while True:
            # Step A: Poll live KPM indication packet from FlexRIC
            indication = flexric.poll_indication_message(timeout_ms=1000)
            
            if indication:
                metrics = parse_kpm_packet(indication)
                dl_prb_util = metrics["dl_prb_util"]
                urllc_latency = metrics["urllc_lat"]
                
                # Step B: Map continuous metrics to discrete system state
                # State 0: Normal operation (PRB util < 85%)
                # State 1: Congestion / Threat detected (PRB util >= 85% or high latency)
                current_state = 1 if (dl_prb_util >= 85.0 or urllc_latency > 10.0) else 0
                
                # Step C: Compute environment reward based on SLA performance
                # Reward is high if URLLC latency is safe, heavily penalized if violated
                if urllc_latency <= 10.0:
                    reward = 1.0
                else:
                    reward = -2.0 # Penalty for SLA violation

                # Update agent models using experience from previous step
                if 'prev_state' in locals():
                    agent.update_models(prev_state, prev_action, reward, current_state)

                # Step D: Select next action using PE arbitration
                chosen_action, habit_weight = agent.select_action(current_state)
                
                print(f"[Telemetry] PRB: {dl_prb_util:.1f}% | Latency: {urllc_latency:.1f}ms | State: {current_state} | W_habit: {habit_weight:.2f}")

                # Step E: Actuate based on model decision
                # Action 0: Maintain baseline quotas
                # Action 1: Active avoidance (Protect URLLC by expanding min PRBs)
                if chosen_action == 1 and current_slices["URLLC"]["min_prb"] != 25:
                    print("[PE Agent] Avoidance triggered! Expanding URLLC resource floor.")
                    current_slices["URLLC"]["min_prb"] = 25
                    current_slices["EMBB"]["max_prb"] = 60
                    dispatch_e2_rc_command(current_slices)
                    
                elif chosen_action == 0 and current_slices["URLLC"]["min_prb"] != 10:
                    print("[PE Agent] Normal conditions. Reverting slice quotas.")
                    current_slices["URLLC"]["min_prb"] = 10
                    current_slices["EMBB"]["max_prb"] = 90
                    dispatch_e2_rc_command(current_slices)

                # Store state/action for next iteration update
                prev_state = current_state
                prev_action = chosen_action
                
            else:
                pass

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[xApp] Termination caught. Freeing FlexRIC resources...")
        flexric.free_xapp()
        sys.exit(0)

def parse_kpm_packet(packet):
    """Extracts structured telemetry from FlexRIC KPM indication streams."""
    return {
        "dl_prb_util": 88.5,
        "urllc_lat": 8.2
    }

def dispatch_e2_rc_command(slice_config):
    """Dispatches E2SM-RC control message to OAI gNB."""
    payload = {
        "service_model": "E2SM-RC",
        "control_primitive": "SET_SLICE_PRB_LIMITS",
        "slices": slice_config
    }
    # flexric.send_e2_control(payload)
    print(f"--> [E2-RC Dispatch]: {slice_config}\n")

if __name__ == "__main__":
    main()
