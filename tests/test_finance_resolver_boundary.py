import ast
from pathlib import Path


# FINANCE_RESOLVER_BOUNDARY_REGRESSION_V2
#
# Application-layer finance execution must not bypass the
# verified resolver and call compare_financing directly from
# finance_live_compare.


APPLICATION_CONSUMERS = (
    Path("src/chatbot_orchestrator.py"),
    Path("src/local_agent_tools.py"),
)


def _raw_compare_import_lines(
    path: Path,
):
    source = path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(path),
    )

    lines = []

    for node in ast.walk(tree):

        if not isinstance(
            node,
            ast.ImportFrom,
        ):
            continue

        if (
            node.module
            !=
            "src.finance_live_compare"
        ):
            continue

        if any(
            alias.name
            ==
            "compare_financing"
            for alias in node.names
        ):

            lines.append(
                node.lineno
            )

    return lines


def test_application_consumers_do_not_bypass_resolver():

    for path in APPLICATION_CONSUMERS:

        assert (
            _raw_compare_import_lines(
                path
            )
            ==
            []
        ), path


def test_application_consumers_reference_verified_resolver():

    for path in APPLICATION_CONSUMERS:

        source = path.read_text(
            encoding="utf-8",
        )

        assert (
            "src.finance_verified_resolver"
            in source
        ), path


def test_resolver_owns_raw_live_engine_boundary():

    source = Path(
        "src/finance_verified_resolver.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "compare_financing as "
        "_compare_financing_engine"
        in source
    )

    assert (
        "FINANCE_VERIFIED_RESOLVER_PUBLIC_FACADE_V1"
        in source
    )

    assert (
        "compare_financing = "
        "resolve_finance_results"
        in source
    )
