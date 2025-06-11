# DNS与转发功能

### **1. 为什么 `/etc/hosts` 无法实现路径路由？**
- **`/etc/hosts` 的局限性**：
  - 仅支持 **域名到 IP 的映射**（如 `example.com → 192.168.1.100`），无法处理 **HTTP 路径**（如 `/path1`）。
  - 路径路由是 **L7（应用层）** 功能，而 `/etc/hosts` 是 **L3（网络层）** 工具。

- **示例尝试（无效）**：
  ```plaintext
  # /etc/hosts
  192.168.1.100 example.com/path1  # ❌ 无法生效
  192.168.1.101 example.com/path2  # ❌ 无法生效
  ```

---

### **2. 实现路径路由**
#### **方案 1：使用 Ingress Controller**
1. **创建 Ingress 资源**：
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: path-routing
   spec:
     rules:
     - host: example.com
       http:
         paths:
         - path: /path1
           pathType: Prefix
           backend:
             service:
               name: service1
               port:
                 number: 80
         - path: /path2
           pathType: Prefix
           backend:
             service:
               name: service2
               port:
                 number: 80
   ```

#### **方案 2：反向代理（非 Kubernetes 原生）** 
**Nginx 示例**：
```nginx
server {
    listen 80;
    server_name example.com;
    location /path1 {
        proxy_pass http://service1-ip:80;
    }
    location /path2 {
        proxy_pass http://service2-ip:80;
    }
}
```

---

