import json
import time
import threading
import logging
from typing import Dict, List
from pkg.apiObject.service import Service
from pkg.config.serviceConfig import ServiceConfig
from pkg.apiServer.apiClient import ApiClient


class ServiceController:
    """Service控制器，负责Service的生命周期管理"""
    
    def __init__(self, etcd_client, uri_config, namespace="default"):
        self.etcd_client = etcd_client
        self.uri_config = uri_config
        self.namespace = namespace
        self.logger = logging.getLogger(__name__)
        
        # API客户端
        self.api_client = ApiClient(uri_config.HOST, uri_config.PORT)
        
        # Service缓存
        self.services: Dict[str, Service] = {}  # service_name -> Service
        self.service_configs: Dict[str, ServiceConfig] = {}  # service_name -> ServiceConfig
        
        # 控制器状态
        self.running = False
        self.sync_thread = None
        self.sync_interval = 10  # 同步间隔（秒）
        
        self.logger.info(f"ServiceController初始化完成，namespace: {namespace}")
    
    def start(self):
        """启动Service控制器"""
        if self.running:
            self.logger.warning("ServiceController已经在运行")
            return
        
        self.running = True
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        self.logger.info("ServiceController已启动")
    
    def stop(self):
        """停止Service控制器"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        
        # 清理所有Service
        for service in self.services.values():
            try:
                service.stop()
            except Exception as e:
                self.logger.error(f"停止Service失败: {e}")
        
        self.services.clear()
        self.service_configs.clear()
        self.logger.info("ServiceController已停止")
    
    def _sync_loop(self):
        """同步循环"""
        while self.running:
            try:
                self._sync_services()
                time.sleep(self.sync_interval)
            except Exception as e:
                self.logger.error(f"同步Service失败: {e}")
                time.sleep(self.sync_interval)
    
    def _sync_services(self):
        """同步所有Service"""
        try:
            # 获取所有Pod
            pods = self._get_all_pods()
            
            # 同步每个Service
            for service_name, service in list(self.services.items()):
                try:
                    # 过滤匹配的Pod
                    matching_pods = [
                        pod for pod in pods 
                        if service.config.matches_pod(getattr(pod, 'labels', {}))
                    ]
                    
                    # 更新Service端点
                    service.update_endpoints(matching_pods)
                    
                except Exception as e:
                    self.logger.error(f"同步Service {service_name} 失败: {e}")
            
        except Exception as e:
            self.logger.error(f"同步所有Service失败: {e}")
    
    def _get_all_pods(self) -> List:
        """获取所有Pod"""
        try:
            # 从etcd获取所有Pod
            # 这里需要根据实际的etcd key格式调整
            from pkg.config.etcdConfig import EtcdConfig
            etcd_config = EtcdConfig()
            
            # 获取指定namespace的Pod
            pods_key = etcd_config.PODS_KEY.format(namespace=self.namespace)
            pods = self.etcd_client.get_prefix(pods_key)
            
            # 也获取全局Pod（如果需要跨namespace）
            try:
                global_pods = self.etcd_client.get_prefix(etcd_config.GLOBAL_PODS_KEY)
                # 过滤指定namespace的Pod
                namespace_pods = [
                    pod for pod in global_pods
                    if getattr(pod, 'namespace', 'default') == self.namespace
                ]
                pods.extend(namespace_pods)
            except:
                pass
            
            return pods
            
        except Exception as e:
            self.logger.error(f"获取Pod列表失败: {e}")
            return []
    
    def create_service(self, service_config: ServiceConfig) -> Service:
        """创建Service"""
        try:
            service_name = service_config.name
            
            if service_name in self.services:
                raise ValueError(f"Service {service_name} 已存在")
            
            # 创建Service实例
            service = Service(service_config, self.etcd_client)
            
            # 获取匹配的Pod并启动Service
            pods = self._get_all_pods()
            matching_pods = [
                pod for pod in pods 
                if service_config.matches_pod(getattr(pod, 'labels', {}))
            ]
            
            service.start(matching_pods)
            
            # 缓存Service
            self.services[service_name] = service
            self.service_configs[service_name] = service_config
            
            self.logger.info(f"Service {service_name} 创建成功")
            return service
            
        except Exception as e:
            self.logger.error(f"创建Service失败: {e}")
            raise
    
    def delete_service(self, service_name: str):
        """删除Service"""
        try:
            if service_name not in self.services:
                raise ValueError(f"Service {service_name} 不存在")
            
            service = self.services[service_name]
            service.stop()
            
            # 从缓存中移除
            del self.services[service_name]
            del self.service_configs[service_name]
            
            self.logger.info(f"Service {service_name} 删除成功")
            
        except Exception as e:
            self.logger.error(f"删除Service失败: {e}")
            raise
    
    def get_service(self, service_name: str) -> Service:
        """获取Service"""
        if service_name not in self.services:
            raise ValueError(f"Service {service_name} 不存在")
        return self.services[service_name]
    
    def list_services(self) -> List[Service]:
        """列出所有Service"""
        return list(self.services.values())
    
    def update_service(self, service_name: str, new_config: ServiceConfig):
        """更新Service配置"""
        try:
            if service_name not in self.services:
                raise ValueError(f"Service {service_name} 不存在")
            
            old_service = self.services[service_name]
            old_service.stop()
            
            # 创建新的Service
            new_service = Service(new_config, self.etcd_client)
            
            # 获取匹配的Pod并启动Service
            pods = self._get_all_pods()
            matching_pods = [
                pod for pod in pods 
                if new_config.matches_pod(getattr(pod, 'labels', {}))
            ]
            
            new_service.start(matching_pods)
            
            # 更新缓存
            self.services[service_name] = new_service
            self.service_configs[service_name] = new_config
            
            self.logger.info(f"Service {service_name} 更新成功")
            
        except Exception as e:
            self.logger.error(f"更新Service失败: {e}")
            raise
    
    def get_service_stats(self, service_name: str = None) -> Dict:
        """获取Service统计信息"""
        if service_name:
            if service_name not in self.services:
                return {"error": f"Service {service_name} 不存在"}
            return self.services[service_name].get_stats()
        else:
            # 返回所有Service的统计信息
            stats = {
                "total_services": len(self.services),
                "namespace": self.namespace,
                "services": []
            }
            
            for service in self.services.values():
                stats["services"].append(service.get_stats())
            
            return stats
    
    def handle_pod_event(self, event_type: str, pod):
        """处理Pod事件（添加、删除、更新）"""
        try:
            self.logger.info(f"处理Pod事件: {event_type}, Pod: {getattr(pod, 'name', 'unknown')}")
            
            # 对于Pod变化，我们简单地触发一次同步
            # 在生产环境中，可以更精细地只更新相关的Service
            self._sync_services()
            
        except Exception as e:
            self.logger.error(f"处理Pod事件失败: {e}")
    
    def force_sync(self):
        """强制同步所有Service"""
        try:
            self._sync_services()
            self.logger.info("强制同步完成")
        except Exception as e:
            self.logger.error(f"强制同步失败: {e}")
            raise
