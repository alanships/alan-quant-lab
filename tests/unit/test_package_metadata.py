"""Package-level smoke checks. / 包级别 smoke 测试。"""

from importlib import metadata

import okx_perp_reliable as sdk


def test_public_symbols_present() -> None:
    """Verify package exports are importable.

    验证包导出的公开符号可以导入。
    """
    assert sdk.ReliablePerpClient is not None
    assert sdk.OrderResult is not None
    assert sdk.OrderRequest is not None
    assert sdk.OrderSide.BUY.value == "buy"
    assert sdk.OrderType.LIMIT.value == "limit"
    assert sdk.ResultStatus.CONFIRMED.value == "CONFIRMED"


def test_distribution_metadata_matches_pyproject() -> None:
    """Verify installed distribution metadata.

    验证已安装包的分发元数据。
    """
    dist = metadata.distribution("okx-perp-reliable")
    assert dist.metadata["Name"] == "okx-perp-reliable"
    assert "MIT" in dist.metadata.get("License", "") + " ".join(
        dist.metadata.get_all("Classifier") or []
    )


def test_classifiers_contain_python_311_minimum() -> None:
    """Verify Python classifier floor matches pyproject.

    验证 Python classifier 下限与 pyproject 一致。
    """
    classifiers = metadata.metadata("okx-perp-reliable").get_all("Classifier") or []
    py_versions = [
        c for c in classifiers if c.startswith("Programming Language :: Python ::")
    ]
    assert "Programming Language :: Python :: 3.10" not in py_versions
    assert "Programming Language :: Python :: 3.11" in py_versions
