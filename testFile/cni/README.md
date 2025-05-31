### 机器一执行
```
docker run -d --name server-container --net=bridge -p 5000:5000 nyteplus/cni-server:latest
docker inspect server-container | grep IPAddress
```
这里假设机器一是10.119.15.182，这个机器我设置flannel网络是bridge。假如ip是<server-ip>

### 机器二执行
```
docker run --rm alpine --net=flannel sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://<server-ip>:5000"
```
这里假设机器一是10.119.15.183，这个机器我设置flannel网络是bridge

运行结果应该为`Hello from Flask Server!`