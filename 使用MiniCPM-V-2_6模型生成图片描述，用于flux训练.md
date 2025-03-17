```python
import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import fcntl
from concurrent.futures import ThreadPoolExecutor
import logging
from PIL import Image, ImageFile
from transformers import AutoTokenizer
from vllm import LLM, SamplingParams
from tqdm import tqdm
import torch

ImageFile.LOAD_TRUNCATED_IMAGES = True  # 允许加载不完整的图片
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模型相关常量
MODEL_NAME = "openbmb/MiniCPM-V-2_6"
BATCH_SIZE = 32
CACHE_FILE = "image_descriptions_cache.json"
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png'}

@dataclass
class ImageBatch:
    """存储待处理图片批次的数据结构"""
    image_paths: List[str]
    images: List[Image.Image]
    hashes: List[str]

class ImageProcessor:
    def __init__(self, model_name: str):
        """初始化图片处理器
        
        Args:
            model_name: 模型路径
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        # 获取可见GPU数量
        # gpu_count = torch.cuda.device_count()
        self.llm = LLM(
            model=model_name,
            trust_remote_code=True,
            gpu_memory_utilization=1,
            max_model_len=2048,
            # tensor_parallel_size=gpu_count,
            # max_num_seqs=512, 
            # enforce_eager=True
        )
        self.sampling_params = self._setup_sampling_params()
        self.cache = self._load_cache()
        
    def _setup_sampling_params(self) -> SamplingParams:
        """设置采样参数"""
        stop_tokens = ['<|im_end|>', '<|endoftext|>']
        stop_token_ids = [self.tokenizer.convert_tokens_to_ids(i) for i in stop_tokens]
        return SamplingParams(
            stop_token_ids=stop_token_ids, 
            use_beam_search=True, #光束搜索，生成具有准确性，只能使用vllm==0.5.4
            temperature=0, 
            best_of=3,
            max_tokens=1024
        )

    def _load_cache(self) -> Dict[str, str]:
        """加载或创建缓存文件"""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    cache = json.load(f)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return cache
            return {}
        except Exception as e:
            logger.error(f"加载缓存文件失败: {e}")
            return {}

    def _save_cache(self, new_entries: Dict[str, str]):
        """保存缓存到文件

        Args:
            new_entries: 新的图片哈希与描述的映射
        """
        try:
            if os.path.exists(CACHE_FILE):
                # 如果文件存在，先读取现有内容
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        cache = json.load(f)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                cache = {}

            # 更新缓存
            cache.update(new_entries)

            # 写入更新后的缓存
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except Exception as e:
            logger.error(f"保存缓存文件失败: {e}")

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件的MD5哈希值
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件的MD5哈希值
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _save_description(self, image_path: str, description: str):
        """保存描述到文本文件
        
        Args:
            image_path: 图片路径
            description: 图片描述
        """
        txt_path = str(Path(image_path).with_suffix('.txt'))
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(description.strip())
        except Exception as e:
            logger.error(f"保存描述文件失败 {txt_path}: {e}")

    def _prepare_batch(self, image_paths: List[str], pbar: Optional[tqdm] = None) -> ImageBatch:
        """准备图片批次并确保正确释放内存

        Args:
            image_paths: 图片路径列表
            pbar: tqdm进度条对象

        Returns:
            包含图片数据的批次对象
        """
        images = []
        valid_paths = []
        hashes = []

        for path in image_paths:
            try:
                # 验证图片
                img = None
                try:
                    img = Image.open(path)
                    img.verify()
                except Exception:
                    logger.warning(f"图片可能不完整，但仍尝试处理: {path}")
                finally:
                    if img is not None:
                        img.close()

                # 重新打开并转换图片
                with Image.open(path) as img:
                    # 直接在内存中转换，避免保留原始图片
                    converted_img = img.convert("RGB")
                    # 计算哈希值
                    file_hash = self._calculate_file_hash(path)

                    images.append(converted_img)
                    valid_paths.append(path)
                    hashes.append(file_hash)

                    if pbar:
                        pbar.update(1)

            except Exception as e:
                logger.error(f"处理图片失败 {path}: {str(e)}")
                if pbar:
                    pbar.update(1)

        return ImageBatch(valid_paths, images, hashes)

    def _generate_descriptions(self, batch: ImageBatch) -> Dict[str, str]:
        """生成图片描述，确保释放内存

        Args:
            batch: 图片批次

        Returns:
            图片哈希与描述的映射
        """
        try:
            messages = [{
                "role": "user",
                "content": "(<image>./</image>)\n Describe this image in detail"
            }]
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            inputs = [{
                "prompt": prompt,
                "multi_modal_data": {
                    "image": image
                }
            } for image in batch.images]

            outputs = self.llm.generate(inputs, sampling_params=self.sampling_params)
            descriptions = {}

            for i, output in enumerate(outputs):
                descriptions[batch.hashes[i]] = output.outputs[0].text

            return descriptions

        except Exception as e:
            logger.error(f"生成描述失败: {e}")
            return {}

        finally:
            # 确保释放图片内存
            for image in batch.images:
                image.close()
    
    def _description_exists(self, image_path: str) -> bool:
        """检查对应的描述文件是否存在

        Args:
            image_path: 图片路径

        Returns:
            bool: 描述文件是否存在
        """
        txt_path = str(Path(image_path).with_suffix('.txt'))
        return os.path.exists(txt_path)

    def process_directory(self, directory: str):
        """处理指定目录下的所有图片

        Args:
            directory: 目录路径
        """
        # 首先收集需要处理的文件路径
        image_paths = []
        total_files = 0

        for root, _, files in os.walk(directory):
            for file in files:
                if Path(file).suffix.lower() in SUPPORTED_FORMATS:
                    image_paths.append(os.path.join(root, file))
                    total_files += 1

        if total_files == 0:
            logger.info(f"目录 {directory} 中没有找到支持的图片文件")
            return

        main_pbar = tqdm(total=total_files, desc="总进度", position=0)

        # 统计计数器
        processed_count = 0
        skipped_count = 0
        existing_txt_count = 0

        try:
            # 按批次处理图片
            for i in range(0, len(image_paths), BATCH_SIZE):
                batch_paths = image_paths[i:i + BATCH_SIZE]
                uncached_paths = []

                # 检查缓存和已存在的描述文件
                for path in batch_paths:
                    if self._description_exists(path):
                        logger.info(f"描述文件已存在，跳过: {path}")
                        existing_txt_count += 1
                        main_pbar.update(1)
                        continue

                    file_hash = self._calculate_file_hash(path)
                    if file_hash in self.cache:
                        self._save_description(path, self.cache[file_hash])
                        logger.info(f"使用缓存描述: {path}")
                        skipped_count += 1
                        main_pbar.update(1)
                    else:
                        uncached_paths.append(path)

                if not uncached_paths:
                    continue

                # 处理未缓存的图片
                batch = None
                try:
                    batch = self._prepare_batch(uncached_paths)
                    if not batch.images:
                        continue

                    descriptions = self._generate_descriptions(batch)
                    if descriptions:
                        # 保存描述文件并更新缓存
                        for path, file_hash in zip(batch.image_paths, batch.hashes):
                            if file_hash in descriptions:
                                self._save_description(path, descriptions[file_hash])
                                logger.info(f"生成描述完成: {path}")
                                processed_count += 1
                                main_pbar.update(1)

                        self._save_cache(descriptions)
                        self.cache.update(descriptions)

                finally:
                    # 确保批次中的图片被释放
                    if batch and batch.images:
                        for image in batch.images:
                            try:
                                image.close()
                            except Exception:
                                pass

        finally:
            main_pbar.close()

        # 输出统计信息
        logger.info(f"\n处理完成！总计：")
        logger.info(f"- 总文件数：{total_files}")
        logger.info(f"- 已有描述文件：{existing_txt_count}")
        logger.info(f"- 使用缓存：{skipped_count}")
        logger.info(f"- 新处理：{processed_count}")
        logger.info(f"- 失败：{total_files - existing_txt_count - skipped_count - processed_count}")

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='将目录下的图片转换为文字描述')
    parser.add_argument('directory', help='图片所在目录的路径')
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        logger.error(f"目录不存在: {args.directory}")
        return

    try:
        processor = ImageProcessor(MODEL_NAME)
        processor.process_directory(args.directory)
    except Exception as e:
        logger.error(f"程序执行失败: {e}")

if __name__ == "__main__":
    main()
```
