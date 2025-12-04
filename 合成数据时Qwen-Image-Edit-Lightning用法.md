# 胡写的，摘抄自与GPT5.1-high的对话，我不知道如何整理这个，但是想记录到这里。

我又发现了一个盲点，我发现`Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors`这个模型有独特的加载方式。

这个模型来自于`https://huggingface.co/lightx2v/Qwen-Image-Lightning`，这个仓库里面有很多的模型文件，不仅仅是Qwen-Image也有Edit，这些模型归属于`https://github.com/ModelTC/Qwen-Image-Lightning`这个项目。

然后，我之前忽视了lightx2v/Qwen-Image-Lightning的模型卡，里面有关于如何加载这个lora的代码。

但，最一眼就能搞清楚的加载方法在于这个文件`https://github.com/ModelTC/Qwen-Image-Lightning/blob/main/generate_with_diffusers.py`，我根据它修改了`run_qwen_image_edit_generation.py`并调整了传入的命令行参数，从而获得了更好的图片生成效果，出合格图的稳定性也更高了！

generate_with_diffusers.py
```
import argparse
import math
import os
from PIL import Image

from diffusers import (
    DiffusionPipeline,
    FlowMatchEulerDiscreteScheduler,
    QwenImageEditPipeline,
    QwenImageEditPlusPipeline,
)
from diffusers.models import QwenImageTransformer2DModel
import torch


def main(
    model_name,
    prompt_list_file: str,
    image_path_list_file: str | None,
    lora_path: str | None,
    out_dir: str,
    base_seed: int,
    num_inference_steps: int = 8,
    true_cfg_scale: float = 1.0,
):
    if torch.cuda.is_available():
        torch_dtype = torch.bfloat16
        device = "cuda"
    else:
        torch_dtype = torch.float32
        device = "cpu"
    
    if "2509" in model_name:
        is_edit_plus = True
    else:
        is_edit_plus = False

    if image_path_list_file is None:
        pipe_cls = DiffusionPipeline
    else:
        if is_edit_plus:
            pipe_cls = QwenImageEditPlusPipeline
        else:
            pipe_cls = QwenImageEditPipeline

    if lora_path is not None:
        model = QwenImageTransformer2DModel.from_pretrained(
            model_name, subfolder="transformer", torch_dtype=torch_dtype
        )
        assert os.path.exists(lora_path), f"Lora path {lora_path} does not exist"
        scheduler_config = {
            "base_image_seq_len": 256,
            "base_shift": math.log(3),  # We use shift=3 in distillation
            "invert_sigmas": False,
            "max_image_seq_len": 8192,
            "max_shift": math.log(3),  # We use shift=3 in distillation
            "num_train_timesteps": 1000,
            "shift": 1.0,
            "shift_terminal": None,  # set shift_terminal to None
            "stochastic_sampling": False,
            "time_shift_type": "exponential",
            "use_beta_sigmas": False,
            "use_dynamic_shifting": True,
            "use_exponential_sigmas": False,
            "use_karras_sigmas": False,
        }
        scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler_config)
        pipe = pipe_cls.from_pretrained(
            model_name, transformer=model, scheduler=scheduler, torch_dtype=torch_dtype
        )
        pipe.load_lora_weights(lora_path)
    else:
        pipe = pipe_cls.from_pretrained(model_name, torch_dtype=torch_dtype)
    pipe = pipe.to(device)

    positive_magic = {
        "en": ", Ultra HD, 4K, cinematic composition.",  # for english prompt
        "zh": ", 超清，4K，电影级构图.",  # for chinese prompt
    }

    # Generate with different aspect ratios
    if image_path_list_file is None:
        aspect_ratios = {
            "1:1": (1328, 1328),
            "16:9": (1664, 928),
            "9:16": (928, 1664),
            "4:3": (1472, 1104),
            "3:4": (1104, 1472),
            "3:2": (1584, 1056),
            "2:3": (1056, 1584),
        }
    else:
        aspect_ratios = {"not_used": ("auto", "auto")}

    with open(prompt_list_file, "r") as f:
        prompt_list = f.read().splitlines()
    if image_path_list_file is not None:
        with open(image_path_list_file, "r") as f:
            image_path_list = f.read().splitlines()
        assert len(prompt_list) == len(image_path_list)
    else:
        image_path_list = None

    os.makedirs(out_dir, exist_ok=True)
    
    for _, (width, height) in aspect_ratios.items():
        for i, prompt in enumerate(prompt_list):
            if image_path_list is None:
                prompt = prompt + positive_magic["en"]
            input_args = {
                "prompt": prompt,
                "generator": torch.Generator(device=device).manual_seed(base_seed),
                "true_cfg_scale": true_cfg_scale,
                "negative_prompt": " ",
                "num_inference_steps": num_inference_steps,
            }
            if image_path_list is None:
                input_args["width"] = width
                input_args["height"] = height
            else:
                if is_edit_plus:
                    image_paths = image_path_list[i].split(" ")
                    input_args["image"] = [Image.open(image_path).convert("RGB") for image_path in image_paths]
                else:
                    input_args["image"] = Image.open(image_path_list[i]).convert("RGB")

            image = pipe(**input_args).images[0]

            image.save(
                f"{out_dir}/{i:02d}_{width}x{height}_{num_inference_steps}steps_cfg{true_cfg_scale}_example.png"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt_list_file", type=str, default="examples/prompt_list.txt"
    )
    parser.add_argument("--image_path_list_file", type=str, default=None)
    parser.add_argument("--out_dir", type=str, default="results")
    parser.add_argument("--lora_path", type=str, default=None)
    parser.add_argument("--base_seed", type=int, default=42)
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen-Image")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--cfg", type=float, default=None)
    args = parser.parse_args()
    if args.steps is None:
        num_inference_steps = 50 if args.lora_path is None else 8
    else:
        num_inference_steps = args.steps
    if args.cfg is None:
        true_cfg_scale = 4.0 if args.lora_path is None else 1.0
    else:
        true_cfg_scale = args.cfg
    if args.lora_path is not None:
        assert os.path.exists(args.lora_path), (
            f"Lora path {args.lora_path} does not exist"
        )

    main(
        model_name=args.model_name,
        prompt_list_file=args.prompt_list_file,
        image_path_list_file=args.image_path_list_file,
        lora_path=args.lora_path,
        out_dir=args.out_dir,
        base_seed=args.base_seed,
        num_inference_steps=num_inference_steps,
        true_cfg_scale=true_cfg_scale,
    )
```

run_qwen_image_edit_generation.py
```
import argparse
import os
import uuid
import torch
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

from openpyxl import load_workbook
from PIL import Image
from diffusers import QwenImageEditPlusPipeline, FlowMatchEulerDiscreteScheduler
import random
import math

def resolve_path(base_dir: str, path: str) -> str:
    """将 Excel 中的相对路径转为绝对路径；若本身是绝对路径则直接返回。"""
    if not path:
        return None
    path = str(path).strip()
    if not path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)


def main():
    parser = argparse.ArgumentParser(description="根据 Excel 用 Qwen-Image-Edit-2509 合成缺失图像")
    parser.add_argument("--excel", required=True, help="标注用 Excel 文件路径，例如 data.xlsx")
    parser.add_argument("--sheet", default=None, help="Sheet 名称，默认为活动表")
    parser.add_argument("--base-dir", default=".",
                        help="Excel 中路径所相对的根目录（raw_image、generated 等都在这里之下）")
    parser.add_argument("--out-subdir-raw", default="generated/raw",
                        help="生成样本图(raw_image)的相对子目录")
    parser.add_argument("--out-subdir-ref", default="generated/ref",
                        help="生成参考图(ref_image_x)的相对子目录")
    parser.add_argument("--model-id", default="Qwen/Qwen-Image-Edit-2509",
                        help="Hugging Face 模型 ID")
    parser.add_argument("--device", default="cuda", help="cuda 或 cpu")
    parser.add_argument("--true-cfg-scale", type=float, default=4.0)
    parser.add_argument("--guidance-scale", type=float, default=1.0)
    parser.add_argument("--num-steps", type=int, default=40)
    parser.add_argument("--negative-prompt", default=" ")
    # parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-rows", type=int, default=None,
                        help="最多处理多少行（调试用，可选）")
    parser.add_argument("--quantize", action="store_true",
                    help="使用 optimum-quanto 将 transformer 量化为 int8 权重")
    parser.add_argument("--cpu_offload", action="store_true",
                    help="使用 diffusers 的 CPU offload（而不是整个模型 .to(cuda)）")

    args = parser.parse_args()

    # 加载模型
    print("Loading Qwen-Image-Edit-2509 pipeline...")
    
    # From https://github.com/ModelTC/Qwen-Image-Lightning/blob/342260e8f5468d2f24d084ce04f55e101007118b/generate_with_diffusers.py#L82C9-L97C10
    scheduler_config = {
        "base_image_seq_len": 256,
        "base_shift": math.log(3),  # We use shift=3 in distillation
        "invert_sigmas": False,
        "max_image_seq_len": 8192,
        "max_shift": math.log(3),  # We use shift=3 in distillation
        "num_train_timesteps": 1000,
        "shift": 1.0,
        "shift_terminal": None,  # set shift_terminal to None
        "stochastic_sampling": False,
        "time_shift_type": "exponential",
        "use_beta_sigmas": False,
        "use_dynamic_shifting": True,
        "use_exponential_sigmas": False,
        "use_karras_sigmas": False,
    }
    scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler_config)

    pipe = QwenImageEditPlusPipeline.from_pretrained(
        args.model_id,
        torch_dtype=torch.bfloat16,
        scheduler=scheduler
    )
    pipe.load_lora_weights("Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors")
    
    # 注意：此时模型还在 CPU 上
    
    if args.quantize:
        try:
            from optimum.quanto import quantize, freeze, qint8
        except ImportError:
            raise RuntimeError(
                "需要安装 optimum-quanto 才能使用 --quantize\n"
                "请运行: pip install 'optimum-quanto'"
            )
        print("Quantizing transformer to int8 with optimum-quanto...")
        quantize(pipe.transformer, weights=qint8)
        freeze(pipe.transformer)
    
    # 选择上 GPU 的方式
    if args.cpu_offload:
        pipe.vae.enable_slicing() # 启用切片 (sliced) VAE 解码，显著减少峰值显存占用，会引入轻微的速度下降。
        # pipe.vae.enable_tiling() # 启用平铺 (tiled) VAE 解码和编码，允许生成超高分辨率（例如 4K 或更大）的单张图像，节省大量内存，速度较慢。
        pipe.enable_model_cpu_offload() # 把模型分块驻留在 CPU / GPU，上一次用到谁就把谁搬上来，显存占用会更低，但推理会变慢
        print("Enabled model CPU offload.")
    else:
        pipe.to(args.device)
        print(f"Pipeline moved to {args.device}.")
    
    pipe.set_progress_bar_config(disable=None)
    
    base_dir = os.path.abspath(args.base_dir)
    out_ref_root = os.path.join(base_dir, args.out_subdir_ref)
    out_raw_root = os.path.join(base_dir, args.out_subdir_raw)
    os.makedirs(out_ref_root, exist_ok=True)
    os.makedirs(out_raw_root, exist_ok=True)

    gen = torch.Generator(device=args.device).manual_seed(random.randint(1, 99999999))

    wb = load_workbook(args.excel)
    ws = wb[args.sheet] if args.sheet else wb.active

    updated_rows = 0

    for excel_row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        if args.max_rows is not None and updated_rows >= args.max_rows:
            break

        need_gen_cell = row[6]  # 第 7 列 G: need_gen
        need_val = str(need_gen_cell.value).strip().lower() if need_gen_cell.value is not None else ""
        if need_val not in ("true", "1", "yes", "y"):
            continue  # 不需要生成

        raw_cell = row[0]      # A: raw_image
        ref_cells = row[1:4]   # B-D: ref_image_1..3
        prompt_cell = row[4]   # E: gen_edit_prompt

        prompt = (prompt_cell.value or "").strip()
        if not prompt:
            print(f"[row {excel_row_idx}] need_gen=TRUE 但 gen_edit_prompt 为空，跳过。")
            continue

        raw_rel = (raw_cell.value or "").strip() if raw_cell.value else ""
        raw_abs = resolve_path(base_dir, raw_rel) if raw_rel else None
        ref_rels = [(c.value or "").strip() for c in ref_cells]
        ref_abss = [resolve_path(base_dir, p) for p in ref_rels if p]

        has_raw = bool(raw_abs)
        has_any_ref = bool(ref_abss)

        # 判定模式
        if has_raw and not has_any_ref:
            mode = "gen_ref"          # 只有样本图 -> 生成参考图
        elif (not has_raw) and has_any_ref:
            mode = "gen_raw"          # 只有参考图 -> 生成样本图
        elif has_raw and has_any_ref:
            # 有样本也有部分参考图：填补第一个空的 ref_image_x
            empty_slots = [i for i, c in enumerate(ref_cells)
                           if not (c.value and str(c.value).strip())]
            if not empty_slots:
                print(f"[row {excel_row_idx}] need_gen=TRUE 但 raw/ref 都齐全，跳过。")
                continue
            mode = "gen_extra_ref"
        else:
            print(f"[row {excel_row_idx}] need_gen=TRUE 但既没有 raw_image 也没有 ref_image，跳过。")
            continue

        if mode in ("gen_ref", "gen_extra_ref"):
            # 用 raw_image 作为输入，生成一张参考图
            try:
                input_img = Image.open(raw_abs).convert("RGB")
            except Exception as e:
                print(f"[row {excel_row_idx}] 打不开 raw_image '{raw_abs}': {e}")
                continue

            input_images = [input_img]

            with torch.inference_mode():
                out = pipe(
                    image=input_images,
                    prompt=prompt,
                    generator=gen,
                    true_cfg_scale=args.true_cfg_scale,
                    negative_prompt=args.negative_prompt,
                    num_inference_steps=args.num_steps,
                    guidance_scale=args.guidance_scale,
                    num_images_per_prompt=1,
                )
            out_img = out.images[0]

            filename = uuid.uuid4().hex + ".png"
            save_path = os.path.join(out_ref_root, filename)
            out_img.save(save_path)

            rel_save = os.path.relpath(save_path, base_dir).replace("\\", "/")

            # 写入第一个空的 ref_image_x
            if mode == "gen_ref":
                target_index = None
                for i, c in enumerate(ref_cells):
                    if not (c.value and str(c.value).strip()):
                        target_index = i
                        break
            else:  # gen_extra_ref
                target_index = [i for i, c in enumerate(ref_cells)
                                if not (c.value and str(c.value).strip())][0]

            ref_cells[target_index].value = rel_save
            print(f"[row {excel_row_idx}] 生成 ref_image_{target_index + 1}: {rel_save}")

        elif mode == "gen_raw":
            # 用已有的参考图（可多张）作为输入，生成样本图 raw_image
            input_images = []
            ok = True
            for p in ref_abss:
                try:
                    img = Image.open(p).convert("RGB")
                    input_images.append(img)
                except Exception as e:
                    print(f"[row {excel_row_idx}] 打不开 ref_image '{p}': {e}")
                    ok = False
                    break
            if not ok or not input_images:
                continue

            with torch.inference_mode():
                out = pipe(
                    image=input_images,
                    prompt=prompt,
                    generator=gen,
                    true_cfg_scale=args.true_cfg_scale,
                    negative_prompt=args.negative_prompt,
                    num_inference_steps=args.num_steps,
                    guidance_scale=args.guidance_scale,
                    num_images_per_prompt=1,
                )
            out_img = out.images[0]

            filename = uuid.uuid4().hex + ".png"
            save_path = os.path.join(out_raw_root, filename)
            out_img.save(save_path)

            rel_save = os.path.relpath(save_path, base_dir).replace("\\", "/")
            raw_cell.value = rel_save
            print(f"[row {excel_row_idx}] 生成 raw_image: {rel_save}")

        # 该行已处理完，need_gen 置为 FALSE
        need_gen_cell.value = "FALSE"
        updated_rows += 1

    wb.save(args.excel)
    print(f"已处理 {updated_rows} 行，Excel 已保存到: {args.excel}")


if __name__ == "__main__":
    main()
```

命令行参数
```
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python run_qwen_image_edit_generation.py \
  --excel data_one.xlsx \
  --base-dir ./data_one \
  --model-id ./Qwen-Image-Edit-2509 \
  --device cuda \
  --num-steps 8 \
  --true-cfg-scale 1.0 \
  --guidance-scale 1.0 \
  --quantize \
  --negative-prompt "扭曲，没有遵守指令，不正常，混乱的画面，画面科幻不够现实，不写实，修改了不希望修改的东西，与参考图一致性差"
```

大致的改动就是需要使用FlowMatchEulerDiscreteScheduler，然后`--true-cfg-scale`与Qwen-Image-Edit-2509模型卡上写的有不同，模型卡上写的4，这里需要1，在generate_with_diffusers.py的这部分可以看出似乎有些“特殊用意”：
```
    if args.steps is None:
        num_inference_steps = 50 if args.lora_path is None else 8
    else:
        num_inference_steps = args.steps
    if args.cfg is None:
        true_cfg_scale = 4.0 if args.lora_path is None else 1.0
```

我将继续生成数据集。
