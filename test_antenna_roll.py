"""Test script: pull Reachy Mini's antenna to roll a d20."""

import random
import time

from reachy_mini import ReachyMini

PULL_THRESHOLD = 0.25


def roll_d20() -> int:
    return random.randint(1, 20)


def main():
    print(r"""
    ╔════════════════════════════════════════╗
    ║   🎲  ANTENNA DICE ROLL TEST  🎲      ║
    ║                                        ║
    ║   Pull either antenna to roll a d20!   ║
    ║   Press Ctrl+C to quit.                ║
    ╚════════════════════════════════════════╝
    """)

    with ReachyMini() as mini:
        print("Connected to Reachy Mini. Waiting for antenna pull...\n")

        prev_left_pulled = False
        prev_right_pulled = False

        while True:
            antennas = mini.get_present_antenna_joint_positions()
            right_val, left_val = antennas[0], antennas[1]

            # Right antenna goes negative when pulled down
            right_pulled = right_val < -PULL_THRESHOLD
            # Left antenna goes positive when pulled down
            left_pulled = left_val > PULL_THRESHOLD

            triggered = False
            side = ""

            if right_pulled and not prev_right_pulled:
                triggered = True
                side = "RIGHT"
            elif left_pulled and not prev_left_pulled:
                triggered = True
                side = "LEFT"

            if triggered:
                result = roll_d20()
                print(f"  📡 {side} antenna pulled!")
                print(f"  🎲 Rolling d20 ... {result}!", end="")
                if result == 20:
                    print("  ⚡ NATURAL 20! CRITICAL HIT!")
                elif result == 1:
                    print("  💀 NATURAL 1! CRITICAL FAIL!")
                else:
                    print()
                print()

            prev_left_pulled = left_pulled
            prev_right_pulled = right_pulled
            time.sleep(0.02)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDone.")
