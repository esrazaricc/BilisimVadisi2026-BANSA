from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd


PAGE = Path(__file__).resolve().parents[1] / "pages" / "4_Finansman_Karşılaştırması.py"


def _load_parser_functions():
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"has_value", "parse_scaled_amount", "parse_vehicle_rules_text"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    ns = {"re": re, "pd": pd}
    exec(compile(module, str(PAGE), "exec"), ns)
    return ns["parse_vehicle_rules_text"]


def test_vehicle_parser_does_not_truncate_turkish_million_separators():
    parse = _load_parser_functions()
    rules = parse(
        "≤ 400.000 TL: %70 / 48 ay · "
        "400.001–800.000 TL: %50 / 36 ay · "
        "800.001–1.200.000 TL: %30 / 24 ay · "
        "1.200.001–2.000.000 TL: %20 / 12 ay · "
        "> 2.000.000 TL: kullandırım yok"
    )
    assert [r["max_amount"] for r in rules[:4]] == [400000.0, 800000.0, 1200000.0, 2000000.0]
    assert rules[3]["min_amount"] == 1200001.0
    assert rules[4]["min_amount"] == 2000000.0
    assert rules[4]["blocked"] is True
