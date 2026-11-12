"""测试共用的构造器与运行辅助，本身不是测试。

构造器按外部规范独立实现，不引用被测模块的表或函数，使它们能充当判定基准；
其自身的正确性由 unit/test_support.py 用标准向量检验，并在契约层由真实 sqlcipher 交叉验证。
导入本包会把仓库根目录加入 sys.path，各层的测试由此导入被测模块，运行不依赖当前目录。
"""

import sys
from pathlib import Path

__all__ = ["REPO"]

REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
