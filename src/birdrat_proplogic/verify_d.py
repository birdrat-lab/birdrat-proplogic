from __future__ import annotations

import argparse

from birdrat_proplogic.dproof import render_dproof_verification


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m birdrat_proplogic.verify_d")
    parser.add_argument("dproof", help="prefix condensed-detachment proof, e.g. DD211")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    print(render_dproof_verification(args.dproof))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
