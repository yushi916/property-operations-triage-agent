import argparse
from pathlib import Path

from evals.scenarios import create_scenario_database


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(
        description="从模拟数据创建全新的演示数据库"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "property.db",
    )
    parser.add_argument(
        "--scenario",
        choices=("base", "active_notice"),
        default="base",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    create_scenario_database(
        output,
        ROOT / "data" / "demo_case.json",
        args.scenario,
    )
    print(f"已创建演示数据库：{output}")
    print(f"场景：{args.scenario}")


if __name__ == "__main__":
    main()
