import os
import random
import torch
import gradio as gr

from PIL import Image
from diffusers import QwenImage21Pipeline

# =========================================================
# Config
# =========================================================

MODEL_ID = os.environ.get(
    "QWEN_IMAGE_MODEL",
    "Qwen/Qwen-Image-2.1"
)

MAX_SEED = 2**31 - 1

SIZE_PRESETS = {
    "1024x1024": (1024, 1024),
    "1344x768": (1344, 768),
    "768x1344": (768, 1344),
    "1184x864": (1184, 864),
    "864x1184": (864, 1184),

    "2048x2048": (2048, 2048),
    "2688x1536": (2688, 1536),
    "1536x2688": (1536, 2688),
    "2368x1728": (2368, 1728),
    "1728x2368": (1728, 2368),

    "2400x1792": (2400, 1792),
    "1792x2400": (1792, 2400),
    "2528x1696": (2528, 1696),
    "1696x2528": (1696, 2528),
    "2752x1536": (2752, 1536),
    "1536x2752": (1536, 2752),
}


# =========================================================
# Load model once
# =========================================================

print(f"Loading model: {MODEL_ID}")

pipe = QwenImage21Pipeline.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
)

pipe.to("cuda")
# pipe.enable_model_cpu_offload()

# 推理模式
pipe.set_progress_bar_config(disable=False)

print("Model loaded.")


# =========================================================
# Helpers
# =========================================================

def get_size(size_name):
    if size_name not in SIZE_PRESETS:
        raise gr.Error(f"Invalid size: {size_name}")

    return SIZE_PRESETS[size_name]


def get_generator(seed):
    if seed is None or int(seed) < 0:
        seed = random.randint(0, MAX_SEED)

    seed = int(seed)

    generator = torch.Generator(
        device="cuda"
    ).manual_seed(seed)

    return generator, seed

def validate_edit_images(images):
    if images and len(images) > 10:
        raise gr.Error(
            "Qwen-Image 2.1 supports at most 10 reference images."
        )
    
# =========================================================
# T2I
# =========================================================

@torch.inference_mode()
def text_to_image(
    prompt,
    negative_prompt="",
    size="1024x1024",
    steps=40,
    enable_cfg=False,
    cfg_scale=4.0,
    seed=-1,
    progress=gr.Progress(),
):
    if not prompt or not prompt.strip():
        raise gr.Error("Prompt cannot be empty.")

    width, height = get_size(size)
    generator, seed = get_generator(seed)

    steps = int(steps)

    print(
        f"[T2I] "
        f"{width}x{height}, "
        f"steps={steps}, "
        f"cfg={cfg_scale if enable_cfg else 'default'}, "
        f"seed={seed}"
    )

    progress(0, desc="Starting...")

    def step_callback(pipe, step, timestep, callback_kwargs):
        progress(
            (step + 1) / steps,
            desc=f"Generating {step + 1}/{steps}"
        )
        return callback_kwargs

    # 只放我们确定需要传入的参数
    pipe_kwargs = {
        "prompt": prompt.strip(),
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "generator": generator,
        "callback_on_step_end": step_callback,
    }

    # Negative prompt 未填写时也不传
    if negative_prompt and negative_prompt.strip():
        pipe_kwargs["negative_prompt"] = negative_prompt.strip()

    # CFG 未开启时完全不传 true_cfg_scale
    if enable_cfg:
        pipe_kwargs["true_cfg_scale"] = float(cfg_scale)

    try:
        result = pipe(**pipe_kwargs)

    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        raise gr.Error(
            "GPU out of memory. Please use a smaller resolution."
        )

    progress(1.0, desc="Done")

    return result.images[0], seed


# =========================================================
# Edit
# =========================================================

@torch.inference_mode()
def edit_image(
    images,
    instruction,
    negative_prompt="",
    steps=40,
    enable_cfg=False,
    cfg_scale=4.0,
    seed=-1,
    progress=gr.Progress(),
):
    # -----------------------------------------------------
    # Validate images
    # -----------------------------------------------------

    if not images:
        raise gr.Error("At least one reference image is required.")

    if len(images) > 10:
        raise gr.Error("Qwen-Image 2.1 supports at most 10 reference images.")

    # Gallery type="pil" 正常情况下已经返回 PIL.Image list，
    # 这里仍然做兼容处理。
    pil_images = []

    for item in images:
        # 某些 Gradio 版本 / Gallery 数据格式可能是
        # (image, caption)
        if isinstance(item, tuple):
            item = item[0]

        if isinstance(item, Image.Image):
            img = item
        elif isinstance(item, str):
            img = Image.open(item)
        else:
            raise gr.Error(
                f"Unsupported image type: {type(item).__name__}"
            )

        pil_images.append(img.convert("RGB"))

    if not instruction or not instruction.strip():
        raise gr.Error("Instruction cannot be empty.")

    # -----------------------------------------------------
    # Generator
    # -----------------------------------------------------

    generator, seed = get_generator(seed)
    steps = int(steps)

    sizes = ", ".join(
        f"{img.width}x{img.height}"
        for img in pil_images
    )

    print(
        f"[EDIT] "
        f"images={len(pil_images)}, "
        f"sizes=[{sizes}], "
        f"steps={steps}, "
        f"cfg={cfg_scale if enable_cfg else 'default'}, "
        f"seed={seed}"
    )

    # -----------------------------------------------------
    # Progress
    # -----------------------------------------------------

    progress(0, desc="Starting...")

    def step_callback(pipe, step, timestep, callback_kwargs):
        progress(
            (step + 1) / steps,
            desc=f"Editing {step + 1}/{steps}"
        )
        return callback_kwargs

    # -----------------------------------------------------
    # Pipeline arguments
    # -----------------------------------------------------

    pipe_kwargs = {
        "prompt": instruction.strip(),

        # 关键：直接传 PIL.Image 列表
        "image": pil_images,

        "num_inference_steps": steps,
        "generator": generator,
        "callback_on_step_end": step_callback,
    }

    if negative_prompt and negative_prompt.strip():
        pipe_kwargs["negative_prompt"] = negative_prompt.strip()

    if enable_cfg:
        pipe_kwargs["true_cfg_scale"] = float(cfg_scale)

    # -----------------------------------------------------
    # Inference
    # -----------------------------------------------------

    try:
        result = pipe(**pipe_kwargs)

    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()

        raise gr.Error(
            "GPU out of memory. "
            "Try fewer/smaller reference images."
        )

    progress(1.0, desc="Done")

    return result.images[0], seed


# =========================================================
# UI
# =========================================================

with gr.Blocks(title="Qwen Image 2.1") as demo:

    gr.Markdown(
        """
# Qwen Image 2.1

Local Qwen-Image-2.1 inference server.
"""
    )

    # -------------------------
    # Text to Image
    # -------------------------

    with gr.Tab("Text to Image"):

        t2i_prompt = gr.Textbox(
            label="Prompt",
            lines=6,
            placeholder="Describe the image..."
        )
        t2i_negative_prompt = gr.Textbox(
            label="Negative Prompt",
            lines=3,
            value="",
            placeholder="Optional negative prompt..."
        )

        with gr.Row():

            t2i_size = gr.Dropdown(
                choices=list(SIZE_PRESETS.keys()),
                value="1024x1024",
                label="Resolution",
            )

            t2i_steps = gr.Slider(
                minimum=1,
                maximum=50,
                value=40,
                step=1,
                label="Steps",
            )

            t2i_seed = gr.Number(
                value=-1,
                precision=0,
                label="Seed (-1 = random)",
            )
            
            t2i_enable_cfg = gr.Checkbox(
                label="Enable CFG",
                value=False,
            )
        
            t2i_cfg = gr.Slider(
                minimum=1.0,
                maximum=10.0,
                value=4.0,
                step=0.1,
                label="True CFG Scale",
                interactive=False,
            )

            t2i_enable_cfg.change(
                fn=lambda enabled: gr.update(interactive=enabled),
                inputs=t2i_enable_cfg,
                outputs=t2i_cfg,
                queue=False,
            )

        t2i_button = gr.Button(
            "Generate",
            variant="primary",
        )

        t2i_output = gr.Image(
            label="Generated Image",
            type="pil",
            format="png",
        )

        t2i_used_seed = gr.Number(
            label="Used Seed",
            precision=0,
        )

        t2i_button.click(
            fn=text_to_image,
            inputs=[
                t2i_prompt,
                t2i_negative_prompt,
                t2i_size,
                t2i_steps,
                t2i_enable_cfg,
                t2i_cfg,
                t2i_seed,
            ],
            outputs=[
                t2i_output,
                t2i_used_seed,
            ],
            # 关键：
            # 所有 GPU 操作共享同一个队列
            concurrency_id="gpu_queue",
            concurrency_limit=1,
            api_name="text_to_image",
        )

    # -------------------------
    # Image Edit
    # -------------------------

    with gr.Tab("Image Edit"):

        edit_input = gr.Gallery(
            label="Reference Images (1-10)",
            type="pil",
            interactive=True,
            columns=5,
            rows=2,
            height="auto",
        )

        edit_input.change(
            fn=validate_edit_images,
            inputs=edit_input,
            outputs=[],
            queue=False,
        )

        edit_prompt = gr.Textbox(
            label="Instruction",
            lines=5,
            placeholder=(
                "Describe how to edit/combine the reference images. "
                "Refer to them as image 1, image 2, image 3..."
            )
        )

        edit_negative_prompt = gr.Textbox(
            label="Negative Prompt",
            lines=3,
            value="",
            placeholder="Optional negative prompt..."
        )

        with gr.Row():

            edit_steps = gr.Slider(
                minimum=1,
                maximum=50,
                value=40,
                step=1,
                label="Steps",
            )

            edit_seed = gr.Number(
                value=-1,
                precision=0,
                label="Seed (-1 = random)",
            )

            edit_enable_cfg = gr.Checkbox(
                label="Enable CFG",
                value=False,
            )
        
            edit_cfg = gr.Slider(
                minimum=1.0,
                maximum=10.0,
                value=4.0,
                step=0.1,
                label="True CFG Scale",
                interactive=False,
            )

            edit_enable_cfg.change(
                fn=lambda enabled: gr.update(interactive=enabled),
                inputs=edit_enable_cfg,
                outputs=edit_cfg,
                queue=False,
            )

        edit_button = gr.Button(
            "Edit",
            variant="primary",
        )

        edit_output = gr.Image(
            label="Edited Image",
            type="pil",
            format="png",
        )

        edit_used_seed = gr.Number(
            label="Used Seed",
            precision=0,
        )

        edit_button.click(
            fn=edit_image,
            inputs=[
                edit_input,
                edit_prompt,
                edit_negative_prompt,
                edit_steps,
                edit_enable_cfg,
                edit_cfg,
                edit_seed,
            ],
            outputs=[
                edit_output,
                edit_used_seed,
            ],

            # 和 T2I 使用同一个 GPU 队列
            concurrency_id="gpu_queue",
            concurrency_limit=1,
            api_name="edit_image",
        )


# =========================================================
# Queue
# =========================================================

demo.queue(
    default_concurrency_limit=1,

    # 最多允许多少请求在队列中等待
    max_size=100,
)


# =========================================================
# Launch
# =========================================================

if __name__ == "__main__":

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
    )
