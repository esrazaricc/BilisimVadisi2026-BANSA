from __future__ import annotations

import src.finance_rule_engine as engine


def main() -> int:
    print("=" * 80)
    print("FINANCE RULE ENGINE VERSION")
    print("=" * 80)
    print("Dosya :", engine.__file__)
    print(
        "Sürüm :",
        getattr(
            engine,
            "RULE_ENGINE_VERSION",
            "SÜRÜM İŞARETİ YOK",
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
