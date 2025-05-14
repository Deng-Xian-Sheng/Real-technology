```python
import os
import hashlib
import shutil
from PIL import Image
from tqdm import tqdm

import torch
from transformers import CLIPProcessor
from aesthetics_predictor import AestheticsPredictorV1

# 评分阈值
SCORE_THRESHOLD = 9.5
# 分辨率阈值（宽度和高度）
# 横拍时：width >= MIN_WIDTH 且 height >= MIN_HEIGHT
# 竖拍时：width >= MIN_HEIGHT 且 height >= MIN_WIDTH
MIN_WIDTH = 4032
MIN_HEIGHT = 3024

# 支持的图像格式
VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

# 源目录和目标目录
SOURCE_DIR = './source_dir'
TARGET_DIR = './target_dir'

# 初始化模型（仅在确实需要时才加载到 GPU/CPU）
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model_id = "shunk031/aesthetics-predictor-v1-vit-large-patch14"
predictor = AestheticsPredictorV1.from_pretrained(model_id).to(device)
processor = CLIPProcessor.from_pretrained(model_id)

def calculate_md5(image_path):
    """计算图像文件内容的 MD5 哈希"""
    with open(image_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def evaluate_image(image_path):
    """使用模型预测美学分数"""
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        logits = predictor(**inputs).logits
    probs = torch.nn.functional.softmax(logits, dim=-1)
    scores = torch.arange(1, 11, device=logits.device).float()
    return (probs * scores).sum().item()

def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    copied = 0

    for root, _, files in os.walk(SOURCE_DIR):
        for file in tqdm(files, desc="处理图片"):
            ext = os.path.splitext(file)[1].lower()
            if ext not in VALID_EXTENSIONS:
                continue

            image_path = os.path.join(root, file)
            try:
                # 1. 先读取分辨率
                with Image.open(image_path) as img:
                    width, height = img.size
            except Exception as e:
                print(f"无法打开文件，跳过: {image_path}, 错误: {e}")
                continue

            # 横/竖拍都允许
            if not (
                (width >= MIN_WIDTH and height >= MIN_HEIGHT)
                or
                (width >= MIN_HEIGHT and height >= MIN_WIDTH)
            ):
                # 分辨率不够，跳过
                continue

            # 2. 再做 MD5 去重
            md5_hash = calculate_md5(image_path)
            target_path = os.path.join(TARGET_DIR, md5_hash + ext)
            if os.path.exists(target_path):
                # 已复制过同内容文件，跳过
                continue

            # 3. 最后才做美学评分
            try:
                score = evaluate_image(image_path)
            except Exception as e:
                print(f"评分失败，跳过: {image_path}, 错误: {e}")
                continue

            if score >= SCORE_THRESHOLD:
                shutil.copy2(image_path, target_path)
                copied += 1

    print(f"\n✅ 已复制 {copied} 张高评分且高分辨率图片到 {TARGET_DIR}")

if __name__ == "__main__":
    main()

```
