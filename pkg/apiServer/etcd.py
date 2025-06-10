import etcd3
import pickle

from pkg.config.etcdConfig import EtcdConfig

class Etcd():
    def __init__(self, host, port, config = EtcdConfig):
        self.config = config
        self.etcd = etcd3.client(host=host, port=port)
        print(f'[INFO]Etcd Init at {host}:{port}')

    def reset(self):
        """
        开发阶段调用，清空所有键值
        """
        keys = self.config.RESET_PREFIX
        for key in keys:
            self.etcd.delete_prefix(key)

    def get_prefix(self, prefix):
        """
        get前缀查找，返回值的列表，不会报错
        场景：查看某个namespace的所有pod
        """
        range_response = self.etcd.get_prefix(prefix)

        return [pickle.loads(v) if v else None for v, meta in range_response]

    def get(self, key, ret_meta = False):
        """
        获取一个python类，如果没有返回None，不会报错
        场景：修改某个pod信息，None的判断在接口之外
        """
        val, meta = self.etcd.get(key)
        val = pickle.loads(val) if val else None
        if ret_meta:
            return val, meta
        else:
            return val

    def put(self, key, val):
        val = pickle.dumps(val)
        self.etcd.put(key, val)

    def delete(self, key):
        self.etcd.delete(key)