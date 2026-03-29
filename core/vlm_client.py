# core/vlm_client.py
import requests
import base64
import json
import logging
from pathlib import Path
from core.prompts import prompt_slidable_regions, prompt_generate_intension

class VLMClient:
    def __init__(self, server_url="http://127.0.0.1:8000"):
        self.server_url = server_url.rstrip("/")

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def analyze_slidable_regions(self, image_path: str) -> list:
        """发送截图给远程 VLM，获取可滑动大区域列表"""
        payload = {
            "prompt": prompt_slidable_regions,
            "image_base64": self._encode_image(image_path)
        }

        try:
            logging.info(f"  [VLM Client] 正在远程分析纯视觉区域: {Path(image_path).name} ...")
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=120)
            resp.raise_for_status()
            response_text = resp.json()["text"]
            
            return self._parse_json_response(response_text)
        except Exception as e:
            logging.error(f"  [VLM Client] 区域推理请求失败: {e}")
            return[]

    def generate_intent_for_xml_component(self, image_path: str, bbox: list, direction: str, context_text: str) -> str:
        """为 XML 中提取的明确可滑动组件，远程请求一句自然语言意图"""
        # 注意：这里我们默认屏幕为 1080x2400 进行归一化以辅助大模型定位。
        # 你可以根据你实际连接的手机（如小米12S Ultra）的分辨率进行调整。
        w, h = 1080, 2400 
        norm_bbox = [
            int(bbox[0]/w*1000), int(bbox[1]/h*1000), 
            int(bbox[2]/w*1000), int(bbox[3]/h*1000)
        ]
        
        # 将参数格式化填入 prompt
        prompt = prompt_generate_intension.format(norm_bbox, direction, context_text)
        
        payload = {
            "prompt": prompt,
            "image_base64": self._encode_image(image_path)
        }

        try:
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=60)
            resp.raise_for_status()
            
            # 返回的是一句纯文本指令，清理两端的空白符即可
            response_text = resp.json()["text"].strip()
            return response_text
        except Exception as e:
            logging.error(f"[VLM Client] 生成意图请求失败: {e}")
            return f"沿 {direction} 方向滑动该组件"

    def _parse_json_response(self, text: str) -> list:
        """从大模型的文本回复中安全提取 JSON 数组"""
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
            logging.error(f"[VLM Client] JSON 解析失败: {e}")
            logging.info(f"  [解析用字符串]: {json_str}")
            return []