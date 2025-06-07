"""
Kafka配置工具模块
提供统一的Kafka客户端配置，解决超时和连接问题
"""

def get_kafka_consumer_config(bootstrap_servers, group_id, auto_offset_reset='latest', 
                             enable_auto_commit=False, additional_config=None):
    """
    获取优化的Kafka消费者配置
    
    Args:
        bootstrap_servers: Kafka服务器地址
        group_id: 消费者组ID
        auto_offset_reset: 自动偏移重置策略
        enable_auto_commit: 是否启用自动提交
        additional_config: 额外的配置项
    
    Returns:
        dict: 优化的Kafka消费者配置
    """
    config = {
        'bootstrap.servers': bootstrap_servers,
        'group.id': group_id,
        'auto.offset.reset': auto_offset_reset,
        'enable.auto.commit': enable_auto_commit,
        
        # 超时配置 - 解决max.poll.interval.ms超时问题
        'max.poll.interval.ms': 600000,      # 10分钟 - 最大轮询间隔
        'session.timeout.ms': 30000,         # 30秒 - 会话超时
        'heartbeat.interval.ms': 10000,      # 10秒 - 心跳间隔
        'request.timeout.ms': 60000,         # 60秒 - 请求超时
        
        # 连接配置
        'connections.max.idle.ms': 540000,   # 9分钟 - 最大空闲连接时间
        'reconnect.backoff.ms': 50,          # 重连退避时间
        'reconnect.backoff.max.ms': 1000,    # 最大重连退避时间
        
        # 获取配置
        'fetch.min.bytes': 1,                # 最小获取字节数
        'fetch.wait.max.ms': 500,            # 最大等待时间
        'max.poll.records': 500,             # 每次轮询最大记录数
        
        # 安全和稳定性配置
        'api.version.request': True,         # 启用API版本请求
        'allow.auto.create.topics': False,   # 禁止自动创建主题
    }
    
    # 合并额外配置
    if additional_config:
        config.update(additional_config)
    
    return config


def get_kafka_producer_config(bootstrap_servers, additional_config=None):
    """
    获取优化的Kafka生产者配置
    
    Args:
        bootstrap_servers: Kafka服务器地址
        additional_config: 额外的配置项
    
    Returns:
        dict: 优化的Kafka生产者配置
    """
    config = {
        'bootstrap.servers': bootstrap_servers,
        
        # 可靠性配置
        'acks': 'all',                       # 等待所有副本确认
        'retries': 3,                        # 重试次数
        'retry.backoff.ms': 100,             # 重试退避时间
        
        # 超时配置
        'request.timeout.ms': 60000,         # 60秒 - 请求超时
        'delivery.timeout.ms': 120000,       # 2分钟 - 投递超时
        
        # 批处理配置
        'batch.size': 16384,                 # 批处理大小
        'linger.ms': 5,                      # 等待时间
        
        # 连接配置
        'connections.max.idle.ms': 540000,   # 9分钟 - 最大空闲连接时间
        'reconnect.backoff.ms': 50,          # 重连退避时间
        'reconnect.backoff.max.ms': 1000,    # 最大重连退避时间
        
        # 压缩配置
        'compression.type': 'snappy',        # 压缩类型
        
        # 安全配置
        'api.version.request': True,         # 启用API版本请求
    }
    
    # 合并额外配置
    if additional_config:
        config.update(additional_config)
    
    return config


def get_kafka_admin_config(bootstrap_servers, additional_config=None):
    """
    获取优化的Kafka管理员配置
    
    Args:
        bootstrap_servers: Kafka服务器地址
        additional_config: 额外的配置项
    
    Returns:
        dict: 优化的Kafka管理员配置
    """
    config = {
        'bootstrap.servers': bootstrap_servers,
        'request.timeout.ms': 60000,         # 60秒 - 请求超时
        'connections.max.idle.ms': 540000,   # 9分钟 - 最大空闲连接时间
        'api.version.request': True,         # 启用API版本请求
    }
    
    # 合并额外配置
    if additional_config:
        config.update(additional_config)
    
    return config


# 常用的配置模板
KAFKA_TIMEOUT_CONFIG = {
    'max.poll.interval.ms': 600000,      # 10分钟
    'session.timeout.ms': 30000,         # 30秒
    'heartbeat.interval.ms': 10000,      # 10秒
    'request.timeout.ms': 60000,         # 60秒
}

KAFKA_RELIABILITY_CONFIG = {
    'acks': 'all',
    'retries': 3,
    'retry.backoff.ms': 100,
}

KAFKA_CONNECTION_CONFIG = {
    'connections.max.idle.ms': 540000,
    'reconnect.backoff.ms': 50,
    'reconnect.backoff.max.ms': 1000,
}
