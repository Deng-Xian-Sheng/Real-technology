## 用于 Qwen-Image-2.1 推理的 gradio

它被设计为：在 autodl 上部署。（**32GB**）（**第一次运行会在加载模型时等待许久，正常现象，我不知道 autodl 用了什么魔法实现的 32GB，不知道是 qwen 的问题还是 autodl 的问题，加载模型比较慢。**）

但是实际上，与本地部署只有非常微小的差别。

```bash
# python app.py 
[ERROR] `image_like_kwargs` is part of BaseImageProcessor.preprocess's signature, but not documented. Make sure to add it to the docstring of the function in /root/miniconda3/lib/python3.12/site-packages/transformers/image_processing_utils.py.
Loading model: ./Qwen-Image-2.1
/root/miniconda3/lib/python3.12/site-packages/diffusers/utils/deprecation_utils.py:23: FutureWarning: `torch_dtype` is deprecated and will be removed in version 1.0.0. Please use `dtype` instead.
  deprecate("torch_dtype", "1.0.0", _TORCH_DTYPE_DEPRECATION_MESSAGE)
Loading checkpoint shards: 100%|█████████████████████████████████████████| 2/2 [00:00<00:00,  3.71it/s]
Loading weights: 100%|██████████████████████████████████████████████| 750/750 [00:00<00:00, 790.91it/s]
Loading pipeline components...: 100%|████████████████████████████████████| 5/5 [00:06<00:00,  1.29s/it]
Model loaded.
* Running on local URL:  http://0.0.0.0:7860
* To create a public link, set `share=True` in `launch()`.
```

该错误是库源码的文档错误，不影响模型推理。
```
[ERROR] `image_like_kwargs` is part of BaseImageProcessor.preprocess's signature, but not documented. Make sure to add it to the docstring of the function in /root/miniconda3/lib/python3.12/site-packages/transformers/image_processing_utils.py.
```

WebUI界面和支持的字段参数：
<img width="2345" height="1695" alt="image" src="https://github.com/user-attachments/assets/f48ab923-3653-4e6a-866e-b516f5b8f3d5" />
<img width="2341" height="1723" alt="image" src="https://github.com/user-attachments/assets/46fd6e3f-0791-4cc2-aa3d-769198273a14" />

建议通过ssh隧道访问：`ssh -CNg -L 7860:127.0.0.1:7860 root@xxx.com -p 12345`

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

## Help

代码中的:

```python
if False:
    pipe.to("cuda")
    # Decode large outputs in tiles so a 2K VAE decode fits next to the weights.
    pipe.vae.enable_tiling(
        tile_sample_min_height=1536,
        tile_sample_min_width=1536,
        tile_sample_stride_height=1152,
        tile_sample_stride_width=1152,
    )
else:
    pipe.vae.enable_slicing()
    # Decode large outputs in tiles so a 2K VAE decode fits next to the weights.
    pipe.vae.enable_tiling(
        tile_sample_min_height=1536,
        tile_sample_min_width=1536,
        tile_sample_stride_height=1152,
        tile_sample_stride_width=1152,
    )
    pipe.enable_model_cpu_offload()
```

对于32-48GB的显卡，生成1024x1024可以使用cuda，更大的2K图片需要使用enable_model_cpu_offload

代码中，编辑图片时，默认采用2k（这是为了不降低原始图片清晰度，特别是在原始图片很清晰时）。
