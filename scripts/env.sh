#!/bin/bash
# 快速环境设置 - 仅设置 PYTHONPATH
# 获取脚本所在的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "PYTHONPATH 已设置: $PYTHONPATH"
