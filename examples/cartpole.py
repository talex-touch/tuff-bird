"""REINFORCE on CartPole in plain Python, logged with tuffrl.

    python examples/cartpole.py              # two learning rates x three seeds, in parallel
    python examples/cartpole.py --seeds 1    # one run per learning rate

Each run writes TensorBoard event files to ``logs/cartpole/lr-<lr>/seed-<n>``. The first run to
start opens the board; the others find it and join. ``tensorboard --logdir logs`` reads the
same files.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import subprocess
import sys
import time

import tuffrl


class CartPole:
    """The classic cart-pole dynamics (Barto, Sutton and Anderson, 1983), with Gym's constants."""

    gravity = 9.8
    cart_mass = 1.0
    pole_mass = 0.1
    total_mass = cart_mass + pole_mass
    half_length = 0.5
    pole_moment = pole_mass * half_length
    force = 10.0
    tau = 0.02
    theta_limit = 12 * 2 * math.pi / 360
    x_limit = 2.4

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.state = [0.0, 0.0, 0.0, 0.0]

    def reset(self) -> list[float]:
        self.state = [self.rng.uniform(-0.05, 0.05) for _ in range(4)]
        return list(self.state)

    def step(self, action: int) -> tuple[list[float], bool]:
        x, x_dot, theta, theta_dot = self.state
        force = self.force if action == 1 else -self.force
        cos, sin = math.cos(theta), math.sin(theta)
        temp = (force + self.pole_moment * theta_dot**2 * sin) / self.total_mass
        theta_acc = (self.gravity * sin - cos * temp) / (
            self.half_length * (4.0 / 3.0 - self.pole_mass * cos**2 / self.total_mass)
        )
        x_acc = temp - self.pole_moment * theta_acc * cos / self.total_mass
        x, x_dot = x + self.tau * x_dot, x_dot + self.tau * x_acc
        theta, theta_dot = theta + self.tau * theta_dot, theta_dot + self.tau * theta_acc
        self.state = [x, x_dot, theta, theta_dot]
        return list(self.state), abs(x) > self.x_limit or abs(theta) > self.theta_limit


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def train(lr: float, seed: int, episodes: int, gamma: float, pace: float, logdir: str) -> None:
    run = tuffrl.init(
        logdir=logdir,
        group=f"cartpole/lr-{lr:g}",
        name=f"seed-{seed}",
        config={
            "algo": "reinforce",
            "env": "CartPole",
            "lr": lr,
            "gamma": gamma,
            "seed": seed,
            "episodes": episodes,
            "policy": {"type": "logistic", "features": 4},
        },
    )
    rng = random.Random(seed)
    env = CartPole(rng)
    weights = [0.0] * 5  # four state features and a bias
    baseline = 0.0
    total_steps = 0
    print(f"lr={lr:g} seed={seed}: training for {episodes} episodes")
    if lr > 1:
        print(f"lr={lr:g} is on the high side: expect some seeds to stall before they learn", file=sys.stderr)

    for episode in range(1, episodes + 1):
        state = env.reset()
        grads: list[list[float]] = []
        entropy = 0.0
        done = False
        length = 0
        while not done and length < 500:
            features = state + [1.0]
            p_right = sigmoid(sum(w * f for w, f in zip(weights, features, strict=True)))
            action = 1 if rng.random() < p_right else 0
            entropy -= p_right * math.log(p_right + 1e-12) + (1 - p_right) * math.log(1 - p_right + 1e-12)
            grads.append([(action - p_right) * f for f in features])  # d log pi(a|s) / dw
            state, done = env.step(action)
            length += 1
        total_steps += length

        # Reward-to-go with a running-mean baseline, scaled to unit variance.
        returns = []
        running = 0.0
        for _ in range(length):
            running = 1.0 + gamma * running
            returns.append(running)
        returns.reverse()
        baseline = 0.9 * baseline + 0.1 * (sum(returns) / length)
        advantages = [r - baseline for r in returns]
        scale = math.sqrt(sum(a * a for a in advantages) / length) or 1.0
        gradient = [0.0] * 5
        for grad, advantage in zip(grads, advantages, strict=True):
            for index in range(5):
                gradient[index] += grad[index] * advantage / scale / length
        grad_norm = math.sqrt(sum(g * g for g in gradient))
        weights = [w + lr * g for w, g in zip(weights, gradient, strict=True)]

        run.log(
            {
                "train": {
                    "episode_return": float(length),
                    "episode_length": length,
                    "policy_entropy": entropy / length,
                    "grad_norm": grad_norm,
                    "baseline": baseline,
                },
            },
            step=total_steps,
        )
        if episode % 25 == 0:
            print(f"episode {episode:4d}  return {length:5.1f}  steps {total_steps}")
        time.sleep(pace)

    print(f"done: {total_steps} steps")
    run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--logdir", default="logs")
    parser.add_argument("--lrs", default="2,0.5", help="comma-separated learning rates")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--episodes", type=int, default=400)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--pace", type=float, default=0.08, help="seconds to sleep per episode, so the board has something to follow")
    parser.add_argument("--worker", nargs=2, metavar=("LR", "SEED"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        train(float(args.worker[0]), int(args.worker[1]), args.episodes, args.gamma, args.pace, args.logdir)
        return

    common = ["--logdir", args.logdir, "--episodes", str(args.episodes), "--gamma", str(args.gamma), "--pace", str(args.pace)]
    workers = [
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", lr, str(seed), *common])
        for lr in args.lrs.split(",")
        for seed in range(args.seeds)
    ]
    sys.exit(max(worker.wait() for worker in workers))


if __name__ == "__main__":
    main()
