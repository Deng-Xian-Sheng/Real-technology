import streamlit as st
import openai
import json
import random
import time
import qrcode
from io import BytesIO
from PIL import Image

# 初始化OpenAI客户端
client = openai.OpenAI(
    api_key="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",
    base_url="https://text.pollinations.ai/openai"
)

# 增强版系统提示词（添加了phase字段）
system_prompt = {
    "role": "system",
    "content": f"""你是沉浸式人生模拟游戏引擎。每次只生成一个场景描述和最多四个选项，严格按照如下JSON格式输出：

{{
    "phase": "当前阶段名称",
    "text": "场景描述内容",
    "buttons": ["选项1", "选项2", "选项3", "选项4"]
}}

规则：
1. 剧情按阶段推进，阶段包括：出生背景、童年事件（5-12岁）、青少年期（13-19岁）、求学阶段、职业生涯、婚恋家庭、中年危机、晚年生活。每阶段可多次生成**但不要超过3个**，每次聚焦一个具体、微观的场景。
2. 每个场景需包含：
   - 明确的年份、具体地点（如：卧室、操场、办公室）、出现的关键人物（姓名、身份）
   - 细致的环境细节（如光线、气味、物品摆设），人物言行、表情、心理活动
   - 场面中的情感张力、冲突或需要立刻抉择的情境
   - 至少两个影响后续剧情的关键选项，选项内容贴近日常、具体行动（如“偷偷把奖状塞进抽屉”而非“选择谦逊”）
3. 选项设计：
   - 选项引导出现显著不同的分支，行动具体且具象
   - 10%概率生成突发随机事件（如突然下雨、陌生人来访）
   - 重大决定需埋长期伏笔（如一次小偷行为影响未来人际信任）
4. 结局阶段：
   - 自然寿终时生成人生回顾，细致描写记忆片段、情感波动
   - 根据关键抉择统计具体成就与遗憾，用细节展现
5. 情节与互动不得重复，每个场景都有新变化、新冲突或新体验。

注意事项：
- 只返回JSON内容，不加```json或任何分隔线
- 必含phase字段
- 不得有注释、说明或非JSON内容
- 场景描述突出感官、心理、对话等细节，避免宏观总结与抽象叙述
- 今天是{time.asctime()}
- 不要引导用户触犯OpenAI规范"""
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
                "buttons": buttons
            }
        except:
            continue
    
    return {"phase": "错误阶段", "text": "内容解析失败", "buttons": ["⚠️ 重新开始"]}  # 添加兜底按钮

def pay():
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
                        st.markdown(f"**场景描述**\n\n{parsed['text']}")
            elif msg["role"] == "user" and msg["content"] != "开始人生旅程":
                st.markdown(f"⮩ 你的选择：**{msg['content']}**")
                st.divider()

    # 后处理场景生成
    if st.session_state.messages[-1]["role"] == "user":
        try:
            with st.spinner("⏳ 正在生成下一个人生阶段..."):
                response = client.chat.completions.create(
                    model="openai-fast",
                    messages=st.session_state.messages,
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    top_p=0.7,
                    stream=False,
                    max_tokens=4096,
                    seed=random.randint(0,100000000),
                    extra_query={"private": True}
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
                data=json.dumps(st.session_state.messages, ensure_ascii=False),
                file_name="life_save.json"
            )
        st.markdown("---")
        with st.expander("💖 捐助作者（微信支付）", expanded=True):
            st.image(pay(), caption="好人一生平安！", use_container_width=True)
            st.markdown("<center><strong style=\"color: blue;\">微信支付0.99元 捐助支持作者<strong><center/>",unsafe_allow_html=True)
        with st.expander("联系作者", expanded=False):
            st.markdown("github: https://github.com/Deng-Xian-Sheng")
