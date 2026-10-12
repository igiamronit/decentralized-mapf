from pathlib import Path

from pogema import (pogema_v0, GridConfig, AnimationWrapper,
                    AStarAgent, ISRMetric, CSRMetric, SumOfCostsAndMakespanMetric)

grid_config = GridConfig(
    num_agents=16, size=24, density=0.3, seed=7,
    obs_radius=3, max_episode_steps=128,
    observation_type='POMAPF',
)

env = pogema_v0(grid_config=grid_config)
env = ISRMetric(env)
env = CSRMetric(env)
env = SumOfCostsAndMakespanMetric(env)
env = AnimationWrapper(env)

env.enable_animation()          # must come before reset()
obs, info = env.reset()

agents = [AStarAgent() for _ in range(grid_config.num_agents)]

while True:
    actions = [a.act(o) for a, o in zip(agents, obs)]
    obs, reward, terminated, truncated, info = env.step(actions)
    if all(terminated) or all(truncated):
        break

print("metrics:", info)

output_dir = Path(__file__).resolve().parents[2] / "outputs" / "renders"
output_dir.mkdir(parents=True, exist_ok=True)
env.save_animation(str(output_dir / "demo.svg"))
env.save_html_animation(str(output_dir / "demo.html"))
