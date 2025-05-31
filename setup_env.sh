#!/bin/bash# K8s 项目环境设置脚本# 用于设置正确的 PYTHONPATH 以解决模块导入问题# 获取脚本所在目录的绝对路径SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"# 设置项目根目录的 PYTHONPATHexport PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"echo "================================================================"echo "K8s 项目环境已设置"echo "================================================================"echo "项目根目录: $SCRIPT_DIR"echo "PYTHONPATH: $PYTHONPATH"echo ""
echo "现在可以运行以下命令："
echo "  python ./pkg/apiObject/pod.py"
echo "  python ./pkg/apiObject/replicaSet.py" 
echo "  python ./pkg/apiObject/hpa.py"
echo "  python ./pkg/apiServer/apiServer.py"
echo "  python ./pkg/kubelet/kubelet.py"
echo ""
echo "或者使用模块方式："
echo "  python -m pkg.apiObject.pod"
echo "  python -m pkg.apiServer.apiServer"
echo "================================================================"

# 如果作为 source 执行，保持在当前 shell
# 如果直接执行，启动新的 shell
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "启动新的 shell 会话..."
    exec $SHELL
fi
