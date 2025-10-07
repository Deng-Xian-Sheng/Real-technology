fancyfeast/llama-joycaption-beta-one-hf-llava不会拒绝nsfw

```python
# 它需要vllm，用于启动vllm的命令：
#PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True" HF_HOME=/root/autodl-tmp/model vllm serve fancyfeast/llama-joycaption-beta-one-hf-llava --trust-remote-code --enforce-eager --dtype bfloat16 --gpu-memory-utilization 0.90 --max-model-len 4096 --max-num-batched-tokens 12288 --enable-prefix-caching --port 8000 --download-dir /root/autodl-tmp/model --generation-config vllm

import os
import base64
import time
import threading
from typing import List, Dict, Tuple
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# ========== 配置 ==========
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://127.0.0.1:8000/v1")
MODEL_ID = os.environ.get("VLLM_MODEL_ID", "fancyfeast/llama-joycaption-beta-one-hf-llava")

# 你的用户提示词（无系统提示词）
USER_PROMPT = (
    "Write a straightforward caption for this image within 100 words. Begin with the main subject and medium. "
    "Mention pivotal elements—people, objects, scenery—using confident, definite language. "
    "Focus on concrete details like color, shape, texture, and spatial relationships. "
    "Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. "
    "Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, "
    "or unobservable details. Vary your sentence structure and keep the description concise, without starting "
    "with “This image is…” or similar phrasing."
)

# 批量任务：一个目录对应一个触发词。
# 按需修改/增删，支持多个目录一次性执行。
TASKS: List[Dict[str, str]] = [
    # {"dir": "/root/autodl-tmp/dataset-aaa", "trigger": "xxxx, "},
    # {"dir": "/root/autodl-tmp/dataset-bbb", "trigger": "xxxxxxx, "},
]

# 并发度（每个目录的并发工作线程数）
CONCURRENCY = int(os.environ.get("CAPTION_CONCURRENCY", "8"))

# 生成参数
TEMPERATURE = 0.0   # 0 = 贪心解码，速度更稳定
TOP_P = 1.0
MAX_TOKENS = 128
REQUEST_TIMEOUT = 120  # 每个请求的超时（秒）
RETRIES = 3
BACKOFF = 1.5

IMAGE_EXTS = (".jpg", ".jpeg", ".png")
# =========================

_thread_local = threading.local()

def get_client() -> OpenAI:
    # 每个线程持有一个客户端，避免线程间共享连接的问题
    if not hasattr(_thread_local, "client"):
        _thread_local.client = OpenAI(base_url=VLLM_ENDPOINT, api_key="EMPTY", timeout=REQUEST_TIMEOUT)
    return _thread_local.client

def img_to_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".png":
        mime = "image/png"
    else:
        raise ValueError(f"Unsupported image extension: {ext}")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def generate_caption(data_url: str) -> str:
    client = get_client()
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                }],
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_tokens=MAX_TOKENS,
            )
            
            if resp.choices[0].finish_reason == "length":
                print(f"超过{MAX_TOKENS}tokens被截断：{resp.choices[0].message.content.strip()}")
                
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            if attempt == RETRIES:
                raise
            time.sleep(BACKOFF ** (attempt - 1))
    raise RuntimeError(f"Failed after retries: {last_err}")

def process_one(dir_path: str, filename: str, trigger: str) -> Tuple[str, bool, str]:
    img_path = os.path.join(dir_path, filename)
    out_txt = os.path.splitext(img_path)[0] + ".txt"
    try:
        data_url = img_to_data_url(img_path)
        cap = generate_caption(data_url)
        final_text = f"{trigger}{cap}"
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write(final_text)
        return filename, True, ""
    except Exception as e:
        return filename, False, str(e)

def process_dir(dir_path: str, trigger: str) -> int:
    files = [
        f for f in sorted(os.listdir(dir_path))
        if os.path.isfile(os.path.join(dir_path, f)) and os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ]
    if not files:
        print(f"[SKIP] No images in: {dir_path}")
        return 0

    done = 0
    pbar = tqdm(total=len(files), desc=dir_path, unit="img")
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(process_one, dir_path, fname, trigger): fname for fname in files}
        for fut in as_completed(futures):
            fname = futures[fut]
            ok = False
            try:
                _, ok, err = fut.result()
            except Exception as e:
                err = str(e)
            if ok:
                done += 1
                pbar.set_postfix_str(fname)
            else:
                pbar.set_postfix_str(f"error: {fname}")
                print(f"[ERROR] {os.path.join(dir_path, fname)}: {err}")
            pbar.update(1)
    pbar.close()
    return done

def main():
    total = 0
    for task in TASKS:
        dir_path = task["dir"]
        trigger = task["trigger"]
        if not os.path.isdir(dir_path):
            print(f"[SKIP] Not a directory: {dir_path}")
            continue
        total += process_dir(dir_path, trigger)
    print(f"All done. Captions written: {total}")

if __name__ == "__main__":
    main()
```
