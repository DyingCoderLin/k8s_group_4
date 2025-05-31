#!/bin/bash
# 设置环境变量，用于运行 k8s 项目

# 设置项目根目录的 PYTHONPATH
export PYTHONPATH="/Users/liang/code/cloud_OS/k8s/k8s_group_4:$PYTHONPATH"

# 激活虚拟环境（如果需要）
# source /Users/liang/opt/anaconda3/envs/k8s/bin/activate

echo "环境变量已设置："
echo "PYTHONPATH=$PYTHONPATH"
echo ""
echo "现在可以运行 Python 模块了，例如："
echo "python ./pkg/apiObject/pod.py"
echo "python -m pkg.apiObject.pod"
