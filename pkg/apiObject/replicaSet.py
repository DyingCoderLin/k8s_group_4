import uuid
import copy
from pkg.apiServer.apiClient import ApiClient
from pkg.config.uriConfig import URIConfig
from pkg.config.replicaSetConfig import ReplicaSetConfig


class STATUS:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


class ReplicaSet:
    def __init__(self, config):
        """初始化ReplicaSet"""
        # 保存原始配置
        self.config = config

        # 基本属性
        self.name = config.name
        self.namespace = config.namespace
        self.labels = config.labels

        # 复制属性
        self.status = getattr(config, "status", STATUS.PENDING)
        self.desired_replicas = config.replica_count
        self.current_replicas = getattr(config, "current_replicas", 0)
        self.selector = config.selector
        # self.pod_template = config.template
        self.pod_instances = getattr(config, "pod_instances", [])
        self.hpa_controlled = getattr(config, "hpa_controlled", False)

        # API通信
        self.api_client = None
        self.uri_config = None

    def set_api_client(self, api_client, uri_config=None):
        """设置API客户端，用于与API Server通信"""
        self.api_client = api_client
        self.uri_config = uri_config or URIConfig()
        return self

    def _ensure_api_client(self):
        """确保API客户端已初始化"""
        if not self.api_client:
            self.api_client = ApiClient()
            self.uri_config = URIConfig()

    def add_pod(self, pod_name):
        """添加Pod到ReplicaSet"""
        if pod_name not in self.pod_instances:
            self.pod_instances.append(pod_name)
            self.current_replicas = len(self.pod_instances)

    def remove_pod(self, pod_name):
        """从ReplicaSet中移除Pod"""
        if pod_name in self.pod_instances:
            self.pod_instances.remove(pod_name)
            self.current_replicas = len(self.pod_instances)

    def needs_scaling(self):
        """判断是否需要扩缩容"""
        return self.current_replicas != self.desired_replicas

    def scale_up_count(self):
        """需要创建的Pod数量"""
        return max(0, self.desired_replicas - self.current_replicas)

    def scale_down_count(self):
        """需要删除的Pod数量"""
        return max(0, self.current_replicas - self.desired_replicas)

    def scale_up(self):
        """标记需要扩容"""
        self.status = STATUS.PENDING
        return self.scale_up_count()

    def scale_down(self):
        """标记需要缩容"""
        self.status = STATUS.PENDING
        return self.scale_down_count()

    def update_status(self):
        """更新ReplicaSet状态"""
        if self.needs_scaling():
            self.status = STATUS.PENDING
        else:
            self.status = STATUS.RUNNING

    def to_config_dict(self):
        """将ReplicaSet转换为配置字典"""
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": self.labels,
            },
            "spec": {
                "replicas": self.desired_replicas,
                "selector": self.selector,
                # 'template': self.pod_template
            },
            "status": self.status,
            "current_replicas": self.current_replicas,
            "pod_instances": self.pod_instances,
            "hpa_controlled": self.hpa_controlled,
        }

    # API操作方法

    def create(self):
        """创建ReplicaSet"""
        self._ensure_api_client()

        # 构建API路径
        path = self.uri_config.REPLICA_SET_SPEC_URL.format(
            namespace=self.namespace, name=self.name
        )

        # 发送创建请求
        create_result = self.api_client.post(path, self.to_config_dict())
        if not create_result:
            print(f"[ERROR]Failed to create ReplicaSet {self.name}")
            return False

        # 确保有足够的Pod
        if self.desired_replicas > 0:
            self.scale(self.desired_replicas)

        return True

    def get(namespace, name, api_client=None, uri_config=None):
        """获取ReplicaSet（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()

        # 构建API路径
        path = _uri_config.REPLICA_SET_SPEC_URL.format(namespace=namespace, name=name)

        # 获取ReplicaSet配置
        rs_config_dict = _api_client.get(path)
        if not rs_config_dict:
            print(f"[ERROR]ReplicaSet {name} not found in namespace {namespace}")
            return None

        print(f"[INFO]获取ReplicaSet配置: {rs_config_dict}")

        # # 创建ReplicaSetConfig
        # rs_config = ReplicaSetConfig(rs_config_dict)

        # # 创建ReplicaSet并设置API客户端
        # rs = ReplicaSet(rs_config)
        # rs.set_api_client(_api_client, _uri_config)

        return rs_config_dict

    @staticmethod
    def list(namespace="default", api_client=None, uri_config=None):
        """列出命名空间下的所有ReplicaSet（静态方法）"""
        # 初始化API客户端
        _api_client = api_client or ApiClient()
        _uri_config = uri_config or URIConfig()

        # 构建API路径
        path = _uri_config.REPLICA_SETS_URL.format(namespace=namespace)

        # 获取ReplicaSet列表
        rs_list_data = _api_client.get(path)
        print(f"[INFO]获取ReplicaSet列表: {rs_list_data}")
        if not rs_list_data:
            return []

        # # 转换为ReplicaSet对象
        # replica_sets = []

        # if isinstance(rs_list_data, list):
        #     for rs_data in rs_list_data:
        #         try:
        #             rs_config = ReplicaSetConfig(rs_data)
        #             rs = ReplicaSet(rs_config)
        #             rs.set_api_client(_api_client, _uri_config)
        #             replica_sets.append(rs)
        #         except Exception as e:
        #             print(f"[ERROR]Failed to parse ReplicaSet: {e}")

        return rs_list_data

    def update(self):
        """更新ReplicaSet"""
        self._ensure_api_client()

        # 构建API路径
        path = self.uri_config.REPLICA_SET_SPEC_URL.format(
            namespace=self.namespace, name=self.name
        )

        # 发送更新请求
        update_result = self.api_client.put(path, self.to_config_dict())
        if not update_result:
            print(f"[ERROR]Failed to update ReplicaSet {self.name}")
            return False

        return True

    def scale(self, replicas):
        """调整ReplicaSet副本数"""
        self._ensure_api_client()

        # 如果副本数相同，无需调整
        if self.desired_replicas == replicas:
            return True

        # 更新期望副本数
        old_replicas = self.desired_replicas
        self.desired_replicas = replicas

        # 更新ReplicaSet
        update_success = self.update()
        if not update_success:
            # 如果更新失败，恢复原值
            self.desired_replicas = old_replicas
            return False

        print(f"[INFO]ReplicaSet {self.name} scaled to {replicas} replicas")
        return True

    def delete(self):
        """删除ReplicaSet"""
        self._ensure_api_client()

        # 构建API路径
        path = self.uri_config.REPLICA_SET_SPEC_URL.format(
            namespace=self.namespace, name=self.name
        )

        # 发送删除请求
        delete_result = self.api_client.delete(path)
        if not delete_result:
            print(f"[ERROR]Failed to delete ReplicaSet {self.name}")
            return False

        print(f"[INFO]ReplicaSet {self.name} deleted")
        return True

    # 不需要replicaSet里实现create_pod方法，因为pod的config已经在podConfig里实现了
    def create_pod(self):
        """为ReplicaSet创建单个Pod"""
        self._ensure_api_client()

        # 创建Pod配置
        pod_template = copy.deepcopy(self.pod_template)

        # 生成唯一的Pod名称
        pod_name = f"{self.name}-{uuid.uuid4().hex[:5]}"
        if "metadata" not in pod_template:
            pod_template["metadata"] = {}
        pod_template["metadata"]["name"] = pod_name

        # 添加所有者引用
        pod_template["metadata"]["ownerReferences"] = [
            {
                "apiVersion": "v1",
                "kind": "ReplicaSet",
                "name": self.name,
                "uid": self.name,  # 简化，实际应使用UID
            }
        ]

        # 添加命名空间
        pod_template["metadata"]["namespace"] = self.namespace

        # 创建Pod
        path = self.uri_config.POD_SPEC_URL.format(
            namespace=self.namespace, name=pod_name
        )
        create_result = self.api_client.post(path, pod_template)
        print(f"[INFO]create_result: {create_result}")

        if not create_result:
            print(f"[ERROR]Failed to create Pod {pod_name}")
            return None

        # 添加Pod到ReplicaSet
        self.add_pod(pod_name)

        # 更新ReplicaSet状态
        self.update()

        return pod_name

    def delete_pod(self, pod_name):
        """删除ReplicaSet中的单个Pod"""
        self._ensure_api_client()

        # 构建API路径
        path = self.uri_config.POD_SPEC_URL.format(
            namespace=self.namespace, name=pod_name
        )

        # 发送删除请求
        delete_result = self.api_client.delete(path)
        if not delete_result:
            print(f"[ERROR]Failed to delete Pod {pod_name}")
            return False

        # 从ReplicaSet中移除Pod
        self.remove_pod(pod_name)

        # 更新ReplicaSet状态
        self.update()

        return True


def test_replica_set(ci_mode=False):
    """测试ReplicaSet类的基本功能

    Args:
        ci_mode (bool): 是否在CI环境中运行测试

    Returns:
        bool: 测试是否成功
    """
    import yaml
    import os
    import time
    from pkg.config.globalConfig import GlobalConfig

    # 测试配置文件路径
    global_config = GlobalConfig()
    config_file = os.path.join(global_config.TEST_FILE_PATH, "test-replicaset.yaml")

    # 如果测试配置文件存在，则加载它
    if os.path.exists(config_file):
        print(f"[INFO]正在加载测试配置文件: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
    else:
        # 否则使用默认的测试配置
        print(f"[INFO]未找到测试配置文件，使用默认配置")
        config_dict = {
            "metadata": {
                "name": "test-replicaset",
                "namespace": "default",
                "labels": {"app": "test"},
            },
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "hello-world"}},
                # 'template': {
                #     'metadata': {
                #         'labels': {'app': 'hello-world'}
                #     },
                #     'spec': {
                #         'containers': [
                #             {
                #                 'name': 'hello-world',
                #                 'image': 'hello-world',
                #                 'ports': [{'containerPort': 80}]
                #             }
                #         ]
                #     }
                # }
            },
        }

    # 创建ReplicaSetConfig
    from pkg.config.replicaSetConfig import ReplicaSetConfig

    rs_config = ReplicaSetConfig(config_dict)

    # 创建ReplicaSet
    rs = ReplicaSet(rs_config)

    try:
        if ci_mode:
            # CI 环境中的简化测试
            print("[INFO]在CI模式下运行简化测试...")
            # 验证ReplicaSet对象属性
            assert rs.name == "test-replicaset", "名称不匹配"
            assert rs.namespace == "default", "命名空间不匹配"
            assert rs.desired_replicas == 2, "期望副本数不匹配"
            print("[PASS]ReplicaSet属性验证通过")

            # 测试扩缩容相关方法
            rs.scale(5)
            assert rs.desired_replicas == 5, "扩容后期望副本数不匹配"
            print("[PASS]ReplicaSet扩容方法验证通过")

            # 验证计算方法
            assert rs.scale_up_count() == 5, "扩容计算错误"

            rs.scale(2)
            assert rs.desired_replicas == 2, "缩容后期望副本数不匹配"
            print("[PASS]ReplicaSet缩容方法验证通过")

            # 添加Pod测试
            rs.add_pod("test-pod-1")
            rs.add_pod("test-pod-2")
            assert rs.current_replicas == 2, "添加Pod后当前副本数不匹配"
            print("[PASS]添加Pod方法验证通过")

            # 移除Pod测试
            rs.remove_pod("test-pod-1")
            assert rs.current_replicas == 1, "移除Pod后当前副本数不匹配"
            print("[PASS]移除Pod方法验证通过")

            print("[SUCCESS]CI模式测试完成！")
            return True
        else:
            # 设置API客户端
            rs.set_api_client(ApiClient(), URIConfig())

            # # 测试1: 创建ReplicaSet
            # print("\n[TEST]1. 创建ReplicaSet...")
            # create_success = rs.create()
            # assert create_success, "创建ReplicaSet失败"
            # print("[PASS]创建ReplicaSet成功")

            # return

            # 等待API Server处理
            print("[INFO]等待API Server和Replica Controller处理...")
            time.sleep(10)

            # return

            # 测试2: 获取ReplicaSet
            print("\n[TEST]2. 获取ReplicaSet...")
            retrieved_rs = ReplicaSet.get(rs.namespace, rs.name)
            print(f"rs.name: {rs.name}")
            print(f"retrieved_rs.name: {retrieved_rs['metadata']['name']}")
            assert retrieved_rs is not None, "获取ReplicaSet失败"
            assert (
                retrieved_rs["metadata"]["name"] == rs.name
            ), "获取的ReplicaSet名称不匹配"
            print("[PASS]获取ReplicaSet成功")

            # 测试3: 列出ReplicaSet
            print("\n[TEST]3. 列出ReplicaSet...")
            print("\n[TEST]3. 列出ReplicaSet...")
            rs_list = ReplicaSet.list(rs.namespace)
            assert len(rs_list) > 0, "列出ReplicaSet失败，列表为空"
            print(f"[PASS]列出ReplicaSet成功，找到 {len(rs_list)} 个ReplicaSet")

            # 测试4: 缩放ReplicaSet
            print("\n[TEST]4. 缩放ReplicaSet...")
            scale_success = rs.scale(3)  # 扩容到3个Pod
            assert scale_success, "缩放ReplicaSet失败"
            print("[PASS]缩放ReplicaSet成功")

            # 等待缩放完成
            print("[INFO]等待缩放完成...")
            time.sleep(10)

            # 测试5: 验证Pod创建
            print("\n[TEST]5. 验证Pod创建...")
            updated_rs = ReplicaSet.get(rs.namespace, rs.name)
            assert updated_rs is not None, "获取更新后的ReplicaSet失败"
            print(f"[INFO]当前Pod实例: {updated_rs['pod_instances']}")
            print(f"[INFO]当前副本数: {updated_rs['current_replicas'][0]}")
            assert (
                len(updated_rs["pod_instances"][0]) == updated_rs["current_replicas"][0]
                and updated_rs["current_replicas"][0] == 3
            ), "Pod创建数量不匹配"
            print("[PASS]验证Pod创建成功")

            # return

            # 测试6: 删除ReplicaSet
            print("\n[TEST]6. 删除ReplicaSet...")
            delete_success = rs.delete()
            assert delete_success, "删除ReplicaSet失败"
            print("[PASS]删除ReplicaSet成功")

            print("\n[SUCCESS]所有测试用例通过!")
        return True

    except AssertionError as e:
        print(f"[FAIL]测试失败: {str(e)}")
        return False
    except Exception as e:
        print(f"[ERROR]测试过程中出现错误: {str(e)}")
        return False


if __name__ == "__main__":
    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser(description="ReplicaSet management")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run the test sequence for ReplicaSet in CI mode",
    )
    args = parser.parse_args()

    if args.test:
        print("[INFO]Testing ReplicaSet in CI mode.")
        try:
            # 服务已通过 Travis CI 启动，无需在此检查或启动
            print("[INFO]Assuming services are already running via Travis CI.")

            # 运行测试
            success = test_replica_set(ci_mode=True)  # 使用CI测试模式
            print("[INFO]ReplicaSet test completed.")

            # 测试结束后不停止服务，因为后续测试还需要
            sys.exit(0 if success else 1)
        except Exception as e:
            print(f"[ERROR]Test failed: {str(e)}")
            import traceback

            print(f"[DEBUG]Detailed error: {traceback.format_exc()}")
            sys.exit(1)
    else:
        print("[INFO]Testing ReplicaSet in regular mode.")
        test_replica_set(ci_mode=False)
