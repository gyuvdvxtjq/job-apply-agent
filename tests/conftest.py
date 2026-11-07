# -*- coding: utf-8 -*-
"""tools/ 使用扁平导入（python tools/cli.py 直接执行），测试同样把 tools/ 加到 sys.path。"""
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
