# core/vlm_client.py
import requests
import base64
import json
import os
from pathlib import Path
from core.prompts import (
    REGION_TASK_PROMPT_EN, REGION_EXAMPLE_ASSISTANT_EN,
    COMPONENT_TASK_PROMPT_EN, COMPONENT_EXAMPLE_PROMPT_EN, COMPONENT_EXAMPLE_ASSISTANT_EN
)

class VLMClient:
    def __init__(self, server_url="http://localhost:8000"):
        self.server_url = server_url.rstrip("/")
        
        # 预加载 One-Shot 示例图 (如果文件不存在，也不报错，退化为 zero-shot)
        self.ex_region_b64 = None
        self.ex_comp_b64 = None
        
        ex_region_path = "examples/example_region.png"
        ex_comp_path = "examples/example_component.png"
        
        if os.path.exists(ex_region_path):
            self.ex_region_b64 = self._encode_image(ex_region_path)
        if os.path.exists(ex_comp_path):
            self.ex_comp_b64 = self._encode_image(ex_comp_path)

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def analyze_slidable_regions(self, image_path: str) -> list:
        """发送截图给远程 VLM，获取可滑动大区域列表"""
        payload = {
            "target_image_base64": self._encode_image(image_path),
            "target_user_prompt": REGION_TASK_PROMPT_EN
        }
        
        if self.ex_region_b64:
            payload["example_image_base64"] = self.ex_region_b64
            payload["example_user_prompt"] = REGION_TASK_PROMPT_EN
            payload["example_assistant_reply"] = REGION_EXAMPLE_ASSISTANT_EN

        try:
            print(f"  [VLM Client] Analyzing visual regions (One-Shot): {Path(image_path).name} ...")
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=120)
            resp.raise_for_status()
            response_text = resp.json()["text"]
            
            # 你可以在这里 print(response_text) 来观察它的 <think> 过程
            return self._parse_json_response(response_text)
        except Exception as e:
            print(f"  [VLM Client] Region inference request failed: {e}")
            return[]

    def generate_intent_for_xml_component(self, image_path: str, bbox: list, direction: str, context_text: str) -> str:
        """为 XML 中提取的可滑动组件生成意图"""
        w, h = 1080, 2400 # 按照你的设备调整
        norm_bbox = [
            int(bbox[0]/w*1000), int(bbox[1]/h*1000), 
            int(bbox[2]/w*1000), int(bbox[3]/h*1000)
        ]
        
        target_prompt = COMPONENT_TASK_PROMPT_EN.format(norm_bbox, direction, context_text)
        
        payload = {
            "target_image_base64": self._encode_image(image_path),
            "target_user_prompt": target_prompt
        }
        
        if self.ex_comp_b64:
            payload["example_image_base64"] = self.ex_comp_b64
            payload["example_user_prompt"] = COMPONENT_EXAMPLE_PROMPT_EN
            payload["example_assistant_reply"] = COMPONENT_EXAMPLE_ASSISTANT_EN

        try:
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=60)
            resp.raise_for_status()
            
            response_text = resp.json()["text"].strip()
            
            # 剥离 <think> 标签，只保留最后生成的纯净指令
            if "</think>" in response_text:
                return response_text.split("</think>")[-1].strip()
            return response_text
        except Exception as e:
            print(f"[VLM Client] Failed to generate intent: {e}")
            return f"Swipe {direction} on this component"

    def _parse_json_response(self, text: str) -> list:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start == -1 or end == 0:
            return[]
        
        json_str = text[start:end]
        try:
            regions = json.loads(json_str)
            valid_regions =[]
            for r in regions:
                if 'bbox' in r and len(r['bbox']) == 4:
                    valid_regions.append(r)
            return valid_regions
        except Exception as e:
            print(f"[VLM Client] JSON parsing failed: {e}")
            return
        

    def generate_intent_for_click(self, image_path: str, bbox: list, context_text: str) -> str:
        """为离线保存的点击操作，远程请求一句自然语言意图"""
        w, h = 1080, 2400 # 按照你的设备分辨率调整
        norm_bbox = [
            int(bbox[0] / w * 1000), int(bbox[1] / h * 1000),
            int(bbox[2] / w * 1000), int(bbox[3] / h * 1000)
        ]
        
        from core.prompts import CLICK_TASK_PROMPT_EN, CLICK_EXAMPLE_PROMPT_EN, CLICK_EXAMPLE_ASSISTANT_EN
        target_prompt = CLICK_TASK_PROMPT_EN.format(norm_bbox, context_text)
        
        payload = {
            "target_image_base64": self._encode_image(image_path),
            "target_user_prompt": target_prompt
        }
        
        # 复用 component 的 example 图像作为点击的 one-shot 示例图
        if self.ex_comp_b64:
            payload["example_image_base64"] = self.ex_comp_b64
            payload["example_user_prompt"] = CLICK_EXAMPLE_PROMPT_EN
            payload["example_assistant_reply"] = CLICK_EXAMPLE_ASSISTANT_EN

        try:
            resp = requests.post(f"{self.server_url}/infer", json=payload, timeout=60)
            resp.raise_for_status()
            response_text = resp.json()["text"].strip()
            
            if "</think>" in response_text:
                return response_text.split("</think>")[-1].strip()
            return response_text
        except Exception as e:
            print(f"[VLM Client] Failed to generate intent: {e}")
            return f"Tap on the component '{context_text}'"