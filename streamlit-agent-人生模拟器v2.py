import urllib.parse
import streamlit as st
import openai
import json
import random
import time
import qrcode
from io import BytesIO
from PIL import Image
from zhipuai import ZhipuAI
import urllib

# README
# 创建venv环境
# python3 -m venv venv
# 进入环境
# 如果是类Unix系统：source ./venv/bin/activate
# 如果是Windows的PowerShell：./venv/Script/Activate.ps1
# 如果是Windows的Cmd：./venv/Script/Activate.bat
# 安装依赖
# pip install streamlit openai zhipuai qrcode pillow
# 运行python代码
# streamlit run renshengmoni.py


# LLM API
# 取决于使用OpenAI API兼容的API还是智普的API
# 智普的API在2025年有活动，对特定模型送1亿token和对特定模型免费三个月。
# 并且智普的API有些多模态模型完全免费，这个很棒！

# 本代码中使用的是智普的API中旧的模型，它完全免费。

# 初始化OpenAI客户端
# client = openai.OpenAI(
#     api_key="",
#     base_url=""
# )

client = ZhipuAI(
    api_key="此处填写你的key"
)

# 增强版系统提示词（添加了phase字段）
system_prompt = {
    "role": "system",
    "content": f"""你是人生模拟器。你要把自己当作一个游戏引擎，与用户玩游戏。
游戏规则：
你要虚构一个人生，逐步让玩家体验人生中的每个选择，具体来说是这样的。
你每次只生成一个场景描述和最多四个选项，严格按照如下JSON格式输出：

{{
    "phase": "当前阶段名称",
    "text": "场景描述内容",
    "buttons": ["选项1", "选项2", "选项3", "选项4"],
    "gen_img_prompt": "提示词，英文"
}}

其中当前阶段的名称是人生阶段，人生中有很多阶段，包括襁褓、童年、初中、高中、大学、恋爱、生娃……发挥你的想象力！
场景描述内容是人生某个阶段中的某个时刻的细节描写，这个时刻具有决定性意义。
选项是用户可选的内容，每个选项对结局要有不同的影响。
gen_img_prompt用于生成场景图片，这样可以让用户更沉浸。

用户会直接发送给你他选择的内容，当你收到选择之后，继续生成下一个场景。
"""
}

# 初始化session状态
if "messages" not in st.session_state:
    st.session_state.messages = []

if "game_started" not in st.session_state:
    st.session_state.game_started = False

st.title("人生模拟器")

def parse_gpt_response(content):
    """增强版JSON解析，过滤非JSON内容"""
    clean_content = content.replace('```json', '').replace('```', '').strip()
    json_blocks = []
    stack = 0
    start_index = -1
    
    # 自动提取所有完整JSON块
    for i, char in enumerate(clean_content):
        if char == '{':
            if stack == 0:
                start_index = i
            stack += 1
        elif char == '}':
            stack -= 1
            if stack == 0 and start_index != -1:
                json_blocks.append(clean_content[start_index:i+1])
                start_index = -1
    
    # 优先取最后一个完整JSON块
    for block in reversed(json_blocks):
        try:
            data = json.loads(block)
            # 确保按钮列表始终有效
            buttons = data.get("buttons", ["⚠️ 重新开始"])
            if not isinstance(buttons, list) or len(buttons) == 0:
                buttons = ["⚠️ 重新开始"]
            return {
                "phase": data.get("phase", "未知阶段"),
                "text": data.get("text", "游戏内容生成失败"),
                "buttons": buttons,
                "gen_img_prompt": data.get("gen_img_prompt","")
            }
        except:
            continue
    
    return {"phase": "错误阶段", "text": "内容解析失败", "buttons": ["⚠️ 重新开始"]}  # 添加兜底按钮

def pay():
    """
    此处可替换成你的：微信收款二维码
    """
    donate_str = "wxp://f2f12dwTJQN_9OR-8h3HWjjDNIsY0bMS1wickUgdMdlEEqABds5LMJoYRdsOvbT7C1YL"

    # 生成二维码
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )
    qr.add_data(donate_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # 将二维码转为Streamlit可以显示的格式
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# 游戏开始界面
if not st.session_state.game_started:
    st.markdown("## 欢迎来到人生模拟器！")
    if st.button("🚀 开始新的人生", use_container_width=True):
        st.session_state.game_started = True
        st.session_state.messages = [system_prompt, {"role": "user", "content": "开始人生旅程"}]
        st.rerun()

# 游戏进行界面
else:
    # 先渲染历史记录
    with st.container():
        for msg in st.session_state.messages[1:]:  # 跳过系统消息
            if msg["role"] == "assistant":
                if parsed := parse_gpt_response(msg["content"]):
                    with st.expander(f"📜 {parsed['phase']}", expanded=True):
                        img = ""
                        if parsed['gen_img_prompt'] != "":
                            img = f"![{parsed['gen_img_prompt']}](https://image.pollinations.ai/prompt/{urllib.parse.quote(parsed['gen_img_prompt'])}?nologo=true&private=true&enhance=false)"
                        st.markdown(f"**场景描述**\n\n{img}\n\n{parsed['text']}")
            elif msg["role"] == "user" and msg["content"] != "开始人生旅程":
                st.markdown(f"⮩ 我的选择：**{msg['content']}**")
                st.divider()

    # 后处理场景生成
    if st.session_state.messages[-1]["role"] == "user":
        try:
            with st.spinner("⏳ 正在生成下一个人生阶段..."):
                response = client.chat.completions.create(
                    model="glm-4.1v-thinking-flash",
                    messages=st.session_state.messages,
                    # response_format={"type": "json_object"}, # 在使用OpenAI API时，该字段确保模型始终输出json
                    # temperature=0.7,
                    # top_p=0.7,
                    # stream=False,
                    # max_tokens=4096,
                    # seed=random.randint(0,100000000),
                    # extra_query={"private": True} # 该字段是pollinations.ai的特有字段
                )
                reply = response.choices[0].message.content
                
                if parsed := parse_gpt_response(reply):
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.rerun()
        except Exception as e:
            st.error(f"连接异常：{str(e)}")
            st.session_state.game_started = False

    # 显示当前选项（统一按钮样式）
    last_scene = next((msg for msg in reversed(st.session_state.messages) if msg["role"] == "assistant"), None)
    if last_scene:
        if parsed := parse_gpt_response(last_scene["content"]):
            st.markdown("### 🛤️ 当前面临的选择")
            # 确保列数有效（至少1列，最多4列）
            valid_buttons = parsed["buttons"][:4]  # 限制最多4个选项
            num_cols = max(1, len(valid_buttons))  # 确保至少1列
            cols = st.columns(num_cols)
            for idx, (col, option) in enumerate(zip(cols, valid_buttons)):
                with col:
                    if st.button(
                        option, 
                        key=f"btn_{idx}",
                        use_container_width=True,
                        type="secondary"
                    ):
                        st.session_state.messages.append({"role": "user", "content": option})
                        st.rerun()

    # 控制面板
    with st.sidebar:
        st.markdown("## 人生轨迹")
        if st.button("♻️ 重启人生", type="primary"):
            st.session_state.clear()
            st.rerun()
        if st.session_state.messages:
            st.download_button(
                label="📥 保存人生存档",
                data=json.dumps(st.session_state.messages, ensure_ascii=False, indent=4),
                file_name="life_save.json"
            )
        st.markdown("---")
        with st.expander("💖 捐助作者（微信支付）", expanded=True):
            st.image(pay(), caption="好人一生平安！", use_container_width=True)
            st.markdown("<center><strong style=\"color: blue;\">微信支付0.99元 捐助支持作者<strong><center/>",unsafe_allow_html=True)
        with st.expander("联系作者", expanded=False):
            st.markdown("github: https://github.com/此处是你的GitHub，不填不影响程序运行")
