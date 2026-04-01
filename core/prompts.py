prompt_slidable_regions = """你是一个智能的 GUI 自动化测试助手。请仔细分析这张移动应用UI界面截图，找出屏幕上**所有**隐含的或大面积的“可滑动区域”（例如：信息流、图片瀑布流、横向滑动的卡片组、可展开的抽屉面板等）。

对于你找到的每个可滑动区域，请提供：
1. category: 必须固定输出 "region"
2. type: 区域的类型（如：feed流、短视频区、轮播图、侧边导航栏等）
3. direction: 该区域支持的滑动方向，选择 "vertical"（上下滑动） 或 "horizontal"（左右滑动）
4. bbox: 边界框坐标[x1, y1, x2, y2]，x和y的范围是0到1000的归一化坐标。请务必框选出整个可滑动的有效大区域。
5. command: 针对该区域的一句具体、清晰的自然语言动作指令，必须是【祈使句】，明确指出动作和意图（例如："向上滑动主信息流以查看更多动态"，"向左滑动轮播图以浏览下一张海报"）。

请务必严格以 JSON 数组格式输出，每个元素是一个对象。只输出 JSON，不要有任何额外的文字说明或 Markdown 标记。"""

# 
prompt_generate_intension = """你是一个智能的 GUI 自动化测试助手。这是一张移动应用的UI截图。
我已经通过底层代码为你锁定了一个【可滑动组件】。
它的归一化边界框 (bbox) 是：{}。
它支持的滑动方向是："{}"。
该组件内部包含的文本信息是："{}"。

请你结合截图的视觉上下文和上述信息，推测如果在这个组件上执行滑动，用户的意图是什么？
请仅返回一句具体、清晰的自然语言动作指令，必须是【祈使句】（例如："向下滚动设置列表以查找更多选项" 或 "向右拖动进度条以调整音量"）。
只输出这句指令的纯文本，不要有多余的话。"""

# core/prompts.py

# ==========================================
# 1. 纯视觉寻找大滑动区域 (Region)
# ==========================================
# 【英文实际使用版】
REGION_TASK_PROMPT_EN = """You are an intelligent GUI automation testing expert. This is a screenshot of a mobile application UI.
Your task is to identify **ALL** implicit or large "slidable regions" on the screen (e.g., content feeds, image waterfalls, horizontally scrollable card carousels, expandable side drawers, etc.).

Please first think privately within the <think> and </think> tags. Your thinking process should include:
1. Observe the overall layout and determine the type of the application.
2. Analyze whether the main content exceeds the screen boundaries (e.g., truncated text/images) to determine where it can be scrolled.
3. Confirm the effective bounding box (bbox) of the slidable region.

After thinking, strictly output a JSON array. 
JSON format requirements:
1. category: Must be exactly "region".
2. type: The type of the region (e.g., "feed", "carousel", "sidebar").
3. direction: The supported swipe direction ("vertical" or "horizontal").
4. bbox: Bounding box coordinates[x1, y1, x2, y2], normalized to the range of 0 to 1000.
5. command: A specific, clear natural language action instruction for this region. It MUST be an **imperative sentence** (e.g., "Swipe up on the main feed to view more posts").

STRICT REQUIREMENT: After </think>, you must output ONLY a valid JSON array. Do not include markdown tags like ```json.
"""

REGION_EXAMPLE_ASSISTANT_EN = """<think>
This is a screenshot of a social media app's home page.
I see a large content area in the middle, and the text at the bottom is truncated, indicating this is a vertical dynamic feed.
There is a navigation bar at the top and a tab bar at the bottom, so the main area from y=150 to y=920 is a vertically slidable region.
</think>[
  {
    "category": "region",
    "type": "feed",
    "direction": "vertical",
    "bbox":[0, 150, 1000, 920],
    "command": "Swipe up on the main feed to view more posts"
  }
]"""

# ==========================================
# 2. 为 XML 组件生成意图指令 (Component)
# ==========================================
# 【英文实际使用版】
COMPONENT_TASK_PROMPT_EN = """You are an intelligent GUI automation testing expert. This is a screenshot of a mobile application UI.
I have located a [Scrollable Component] for you via underlying code.
Its normalized bounding box (bbox) is: {}.
Its supported swipe direction is: "{}".
The text information contained within this component is: "{}".

Please first think privately within the <think> and </think> tags:
1. Locate the component in the screenshot using the provided bbox and text.
2. Observe the context of the component to infer its specific function.
3. Formulate an action instruction that matches human habits.

After thinking, return ONLY ONE specific, clear natural language action instruction. It MUST be an **imperative sentence**.
Note: After </think>, output only the plain text of this instruction, with no extra words.
"""

COMPONENT_EXAMPLE_PROMPT_EN = COMPONENT_TASK_PROMPT_EN.format("[0, 100, 1000, 900]", "vertical", "Settings | Network | Bluetooth | Display")

COMPONENT_EXAMPLE_ASSISTANT_EN = """<think>
Located the component at bbox[0, 100, 1000, 900]. The internal text shows "Settings | Network | Bluetooth | Display".
This is a typical system settings list. The direction is "vertical".
If a user swipes on this component, the intent is obviously to scroll down to see other hidden setting items.
Therefore, the instruction should clearly state "Scroll down the settings list".
</think>
Scroll down the settings list to find more system options"""

# -------------------------------------------------------------------------
# [附] 中文对照版 (仅供参考，代码中实际发送的是英文版)
# REGION_TASK_PROMPT_ZH = "你是一个智能的 GUI 自动化测试专家。这是一张移动应用UI界面截图..."
# COMPONENT_TASK_PROMPT_ZH = "我已经通过底层代码为你锁定了一个【可滑动组件】..."
# -------------------------------------------------------------------------