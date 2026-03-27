import requests
import base64
import json
from pathlib import Path

class VLMClient:
    def __init__(self, server_url="http://127.0.0.1:8000"):
        self.server_url = server_url.rstrip("/")

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def analyze_slidable_regions(self, image_path: str) -> list:
        """
        发送截图给 VLM，获取可滑动区域列表
        """
        prompt = """请仔细分析这张移动应用UI界面截图，找出所有可滑动的区域（如列表、轮播图、页面整体等）。
只输出最多前4个可滑动区域的详细信息。
对于每个区域，请提供：
1. category: "slidable"
2. type: 具体类型描述（如：列表、轮播图、大区块）
3. direction: 滑动方向（"vertical" 或 "horizontal"）
4. bbox: 边界框坐标 [x1, y1, x2, y2]，x和y的范围是0到1000的归一化坐标
5. description: 对该区域上滑动操作意图的描述

请务必严格以JSON数组格式输出，每个元素是一个对象。只输出JSON，不要有其他文字说明。
"""
        payload = {
            "prompt": prompt,
            "image_base64": self._encode_image(image_path)
        }

        try:
            print(f"  [VLM] 正在分析图片: {Path(image_path).name} ...")
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=120)
            resp.raise_for_status()
            response_text = resp.json()["text"]
            
            return self._parse_json_response(response_text)
        except Exception as e:
            print(f"  [VLM] 推理请求失败: {e}")
            return[]

    def _parse_json_response(self, text: str) -> list:
        """从大模型的回复中提取 JSON"""
        # 寻找大括号或中括号包裹的区域
        start = text.find('[')
        end = text.rfind(']') + 1
        if start == -1 or end == 0:
            return[]
        
        json_str = text[start:end]
        try:
            regions = json.loads(json_str)
            valid_regions = []
            for r in regions:
                if 'bbox' in r and len(r['bbox']) == 4:
                    valid_regions.append(r)
            return valid_regions
        except Exception as e:
            print(f"  [VLM] JSON 解析失败: {e}")
            return[]