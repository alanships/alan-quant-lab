"""Test-suite-wide pytest setup.

测试级 pytest 配置。

Why this file exists / 为什么需要这个文件：

* The SDK package lives under ``src/okx_perp_reliable/``. The existing
  unit tests assume an editable install (``poetry install`` makes the
  package importable). To let the tests run with just the PyPI deps
  installed, we also prepend ``src/`` to ``sys.path``.
* The mock OKX server lives under ``tests/mock/`` and is imported as
  ``tests.mock.server`` in :mod:`tests.mock.test_mock_server`. For this
  to work, the project root must be on ``sys.path`` and ``tests/`` must
  resolve as a (namespace) package.

This conftest does both, in a way that is no-op when an editable install
is already present.

* SDK 包位于 ``src/okx_perp_reliable/`` 下。既有单测依赖 editable 安装
  （``poetry install`` 后包可导入）。为了让仅安装 PyPI 依赖的环境也能跑
  通测试，这里把 ``src/`` 加入 ``sys.path``。
* Mock OKX 服务器位于 ``tests/mock/``，自测文件以 ``tests.mock.server``
  导入。为此项目根目录必须在 ``sys.path`` 上，``tests/`` 自动作为 PEP 420
  namespace package。

若已经 editable 安装，本文件等同于 no-op。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"

for _p in (str(_ROOT), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
