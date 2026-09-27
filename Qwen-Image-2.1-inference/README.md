## 用于 Qwen-Image-2.1 推理的 gradio

它被设计为：在 autodl 上部署。
但是实际上，与本地部署只有非常微小的差别。

## 快速开始

### 环境变量

几条bash命令，可以放到`~/.bashrc`或者手动执行，用于：
- 设置镜像站环境变量
- 设置HF模型缓存目录环境变量
- 修复autodl上错误的OMP_NUM_THREADS环境变量

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/hf-cache
unset OMP_NUM_THREADS
```

### 依赖

```bash
source /etc/network_turbo # 因为需要从GitHub下载依赖的源码
pip install -U pip
pip install -r requirements.txt
```

### 跑

```bash
unset OMP_NUM_THREADS
HF_ENDPOINT=https://hf-mirror.com HF_HOME=/root/autodl-tmp/hf-cache python app.py
```

or

if you set `~/.bashrc`

```bash
python app.py
```

推荐使用有卡模式，直接模型下载+推理一键OK。否则，无卡模式下载时可能会OOM，你需要手动下载模型，并修改代码中的模型为本地路径，并禁用 Xet 下载后端，并限制并发数：
```bash
HF_ENDPOINT=https://hf-mirror.com \
HF_HOME=/root/autodl-tmp/hf-cache \
HF_HUB_DISABLE_XET=1 \
hf download Qwen/Qwen-Image-2.1 \
  --local-dir ./Qwen-Image-2.1 \
  --max-workers 1
```
