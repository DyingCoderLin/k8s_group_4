#!/bin/bash

# 进入容器的便捷脚本
# 使用方法: ./enter_container.sh [pod名称] [容器名称]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 容器进入工具${NC}"
echo "================================"

# 如果没有提供参数，显示所有运行中的容器
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}📋 当前运行中的容器：${NC}"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo -e "${BLUE}💡 使用方法：${NC}"
    echo "  $0 <容器名称>                    # 进入指定容器"
    echo "  $0 <pod名称> <容器名称>          # 进入指定Pod的容器"
    echo "  $0 -l <关键字>                   # 列出包含关键字的容器"
    exit 0
fi

# 列出匹配的容器
if [ "$1" = "-l" ]; then
    if [ -z "$2" ]; then
        echo -e "${RED}❌ 请提供搜索关键字${NC}"
        exit 1
    fi
    echo -e "${YELLOW}🔍 搜索包含 '$2' 的容器：${NC}"
    docker ps --filter "name=$2" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    exit 0
fi

CONTAINER_NAME=""

# 如果提供了两个参数，按Pod规则查找
if [ $# -eq 2 ]; then
    POD_NAME="$1"
    CONTAINER_NAME="$2"
    
    echo -e "${YELLOW}🔍 查找Pod: $POD_NAME, 容器: $CONTAINER_NAME${NC}"
    
    # 尝试多种可能的命名模式
    POSSIBLE_NAMES=(
        "${CONTAINER_NAME}"
        "${POD_NAME}_${CONTAINER_NAME}"
        "${POD_NAME}-${CONTAINER_NAME}"
        "pause_default_${POD_NAME}"
    )
    
    for name in "${POSSIBLE_NAMES[@]}"; do
        if docker ps -q --filter "name=^${name}$" | grep -q .; then
            CONTAINER_NAME="$name"
            break
        fi
    done
else
    # 单个参数，直接使用
    CONTAINER_NAME="$1"
fi

# 检查容器是否存在且运行中
if ! docker ps -q --filter "name=^${CONTAINER_NAME}$" | grep -q .; then
    echo -e "${RED}❌ 容器 '$CONTAINER_NAME' 未找到或未运行${NC}"
    echo ""
    echo -e "${YELLOW}📋 相似的容器名称：${NC}"
    docker ps --filter "name=$1" --format "{{.Names}}" | head -5
    exit 1
fi

echo -e "${GREEN}✅ 找到容器: $CONTAINER_NAME${NC}"

# 尝试不同的shell
SHELLS=("/bin/bash" "/bin/sh" "/bin/ash")
SHELL_FOUND=false

for shell in "${SHELLS[@]}"; do
    if docker exec "$CONTAINER_NAME" test -f "$shell" 2>/dev/null; then
        echo -e "${BLUE}🚀 进入容器 (使用 $shell)...${NC}"
        docker exec -it "$CONTAINER_NAME" "$shell"
        SHELL_FOUND=true
        break
    fi
done

if [ "$SHELL_FOUND" = false ]; then
    echo -e "${YELLOW}⚠️  未找到标准shell，尝试默认入口...${NC}"
    docker exec -it "$CONTAINER_NAME" /bin/sh
fi
