#!/bin/bash
# filepath: /Users/liang/code/cloud_OS/k8s/k8s_group_4/deploy.sh
# 部署脚本 - 用于在服务器上正确设置环境并启动服务

# 设置颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 设置工作目录
DEPLOY_DIR="$(pwd)"
echo -e "${BLUE}部署目录: ${DEPLOY_DIR}${NC}"

# 设置Python路径
export PYTHONPATH="${DEPLOY_DIR}:${PYTHONPATH}"
echo -e "${BLUE}Python路径: ${PYTHONPATH}${NC}"

# 创建必要的目录
mkdir -p "${DEPLOY_DIR}/logs"
mkdir -p "${DEPLOY_DIR}/testFile"

# 检查依赖服务是否运行
echo -e "${YELLOW}检查依赖服务是否运行...${NC}"

# 检查etcd (2379端口)
nc -z localhost 2379 > /dev/null 2>&1
ETCD_RUNNING=$?

# 检查kafka (9092端口)
nc -z localhost 9092 > /dev/null 2>&1
KAFKA_RUNNING=$?

if [ $ETCD_RUNNING -ne 0 ] || [ $KAFKA_RUNNING -ne 0 ]; then
    echo -e "${RED}etcd或kafka服务未运行，启动所需容器...${NC}"
    
    # 检查docker是否运行
    docker info > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}Docker未运行，请先启动Docker服务${NC}"
        exit 1
    fi
    
    # 停止可能存在的冲突容器
    docker-compose -f ./yamls/docker-compose.yml down || true
    
    # 启动docker-compose
    echo -e "${GREEN}使用docker-compose启动依赖服务...${NC}"
    docker-compose -f ./yamls/docker-compose.yml up -d
    
    # 等待服务启动
    echo -e "${BLUE}等待服务启动 (30秒)...${NC}"
    sleep 30
    
    # 再次检查服务
    nc -z localhost 2379 > /dev/null 2>&1
    ETCD_RUNNING=$?
    nc -z localhost 9092 > /dev/null 2>&1
    KAFKA_RUNNING=$?
    
    if [ $ETCD_RUNNING -ne 0 ] || [ $KAFKA_RUNNING -ne 0 ]; then
        echo -e "${RED}服务启动失败，请检查docker-compose日志${NC}"
        docker-compose -f ./yamls/docker-compose.yml logs
        exit 1
    fi
else
    echo -e "${GREEN}依赖服务已经在运行${NC}"
fi

# 检查Python版本
echo -e "${BLUE}Python版本:${NC}"
python3 --version

# 安装依赖
echo -e "${YELLOW}安装依赖...${NC}"
pip install -r requirements.txt

# 先停止现有服务
echo -e "${YELLOW}停止现有服务...${NC}"
bash ./start.sh --stop || true
sleep 3

# 启动服务
echo -e "${YELLOW}启动服务...${NC}"
bash ./start.sh

# 等待服务启动
echo -e "${BLUE}等待服务启动...${NC}"
sleep 20

# 检查服务状态
echo -e "${YELLOW}检查服务状态:${NC}"
ps -ef | grep python | grep -v grep

# 检查API服务器健康状态
echo -e "${YELLOW}检查API服务器健康状态:${NC}"
curl -f http://localhost:5050/health || echo -e "${RED}API Server健康检查失败${NC}"

echo -e "${GREEN}部署完成!${NC}"
