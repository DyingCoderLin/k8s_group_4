import random
from abc import ABC, abstractmethod
from typing import List, Optional


class LoadBalancer(ABC):
    """负载均衡器抽象基类"""
    
    def __init__(self):
        self.endpoints = []
        self.current_index = 0
    
    def update_endpoints(self, endpoints: List[str]):
        """更新端点列表"""
        self.endpoints = endpoints
        if self.current_index >= len(self.endpoints):
            self.current_index = 0
    
    @abstractmethod
    def get_next_endpoint(self) -> Optional[str]:
        """获取下一个端点"""
        pass


class RoundRobinBalancer(LoadBalancer):
    """轮询负载均衡器"""
    
    def get_next_endpoint(self) -> Optional[str]:
        if not self.endpoints:
            return None
            
        endpoint = self.endpoints[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.endpoints)
        return endpoint


class RandomBalancer(LoadBalancer):
    """随机负载均衡器"""

    def get_next_endpoint(self) -> Optional[str]:
        if not self.endpoints:
            return None
        return random.choice(self.endpoints)


class WeightedRoundRobinBalancer(LoadBalancer):
    """加权轮询负载均衡器（可扩展）"""
    
    def __init__(self):
        super().__init__()
        self.weights = {}  # endpoint -> weight
        self.current_weights = {}  # endpoint -> current_weight
    
    def update_endpoints_with_weights(self, endpoints_weights: dict):
        """更新带权重的端点列表"""
        self.endpoints = list(endpoints_weights.keys())
        self.weights = endpoints_weights.copy()
        self.current_weights = {ep: 0 for ep in self.endpoints}
    
    def get_next_endpoint(self) -> Optional[str]:
        if not self.endpoints:
            return None
            
        # 实现加权轮询算法
        total_weight = sum(self.weights.values())
        max_current_weight = -1
        selected_endpoint = None
        
        for endpoint in self.endpoints:
            weight = self.weights.get(endpoint, 1)
            self.current_weights[endpoint] += weight
            
            if self.current_weights[endpoint] > max_current_weight:
                max_current_weight = self.current_weights[endpoint]
                selected_endpoint = endpoint
        
        if selected_endpoint:
            self.current_weights[selected_endpoint] -= total_weight
            
        return selected_endpoint


def create_load_balancer(balancer_type: str = "round_robin") -> LoadBalancer:
    """负载均衡器工厂函数"""
    if balancer_type == "round_robin":
        return RoundRobinBalancer()
    elif balancer_type == "random":
        return RandomBalancer()
    elif balancer_type == "weighted_round_robin":
        return WeightedRoundRobinBalancer()
    else:
        raise ValueError(f"Unsupported load balancer type: {balancer_type}")
