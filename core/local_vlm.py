import torch
import json
import os
from PIL import Image
from pathlib import Path
from transformers import AutoModelForImageTextToText, AutoProcessor

from core.prompts import (
    REGION_TASK_PROMPT_EN, REGION_EXAMPLE_ASSISTANT_EN,
    COMPONENT_TASK_PROMPT_EN, COMPONENT_EXAMPLE_PROMPT_EN, COMPONENT_EXAMPLE_ASSISTANT_EN,
    CLICK_TASK_PROMPT_EN, CLICK_EXAMPLE_PROMPT_EN, CLICK_EXAMPLE_ASSISTANT_EN
)

class LocalVLMClient:
    def __init__(self, model_path=r""):
        """初始化并加载本地的 VL 模型"""
        print(f"  [LocalVLM] 正在加载本地模型: {model_path} ...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 加载模型
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self.model.eval()
        
        # 预加载 One-Shot 示例图 (如果文件不存在，退化为 zero-shot)
        self.ex_region_img = None
        self.ex_comp_img = None
        
        ex_region_path = "examples/example_region.png"
        ex_comp_path = "examples/example_component.png"
        
        if os.path.exists(ex_region_path):
            self.ex_region_img = Image.open(ex_region_path).convert("RGB")
        if os.path.exists(ex_comp_path):
            self.ex_comp_img = Image.open(ex_comp_path).convert("RGB")
            
        print(f"  [LocalVLM] 模型加载完成！")

    def _generate_text(self, target_image: Image.Image, target_prompt: str, 
                       ex_image: Image.Image = None, ex_user_prompt: str = "", 
                       ex_assistant_reply: str = "", max_tokens: int = 2048) -> str:
        """核心推理引擎：组装多轮对话并执行本地推理"""
        messages =[]
        
        # 1. 构造 One-Shot 历史对话
        if ex_image is not None:
            messages.append({
                "role": "user",
                "content":[
                    {"type": "image", "image": ex_image},
                    {"type": "text", "text": ex_user_prompt}
                ]
            })
            messages.append({
                "role": "assistant",
                "content": ex_assistant_reply
            })
            
        # 2. 构造当前目标的提问
        final_target_prompt = target_prompt
        if ex_image is not None:
            final_target_prompt = f"Now please analyze the current screenshot based on the standards above.\n\n{target_prompt}"

        messages.append({
            "role": "user",
            "content":[
                {"type": "image", "image": target_image},
                {"type": "text", "text": final_target_prompt}
            ]
        })
        
        # 3. 模板渲染与张量化
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images = [img["image"] for msg in messages for img in msg["content"] if img["type"] == "image"]
        inputs = self.processor(text=[text], images=images, return_tensors="pt", padding=True).to(self.device)
        
        # 4. 执行推理
        with torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
            
        gen_ids = output_ids[:, inputs.input_ids.shape[1]:]
        result_text = self.processor.batch_decode(gen_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        
        return result_text

    def analyze_slidable_regions(self, image_path: str) -> list:
        """视觉分析：专门找出大面积可滑动区域"""
        try:
            print(f"  [LocalVLM] 正在本地分析纯视觉区域 (One-Shot): {Path(image_path).name} ...")
            target_image = Image.open(image_path).convert("RGB")
            
            response_text = self._generate_text(
                target_image=target_image,
                target_prompt=REGION_TASK_PROMPT_EN,
                ex_image=self.ex_region_img,
                ex_user_prompt=REGION_TASK_PROMPT_EN,
                ex_assistant_reply=REGION_EXAMPLE_ASSISTANT_EN,
                max_tokens=2048
            )
            return self._parse_json_response(response_text)
        except Exception as e:
            print(f"  [LocalVLM] 区域推理发生错误: {e}")
            return[]

    def generate_intent_for_xml_component(self, image_path: str, bbox: list, direction: str, context_text: str) -> str:
        """为 XML 中提取的可滑动组件生成意图"""
        try:
            w, h = 1080, 2400
            norm_bbox = [
                int(bbox[0]/w*1000), int(bbox[1]/h*1000),
                int(bbox[2]/w*1000), int(bbox[3]/h*1000)
            ]
            
            target_prompt = COMPONENT_TASK_PROMPT_EN.format(norm_bbox, direction, context_text)
            target_image = Image.open(image_path).convert("RGB")
            
            response_text = self._generate_text(
                target_image=target_image,
                target_prompt=target_prompt,
                ex_image=self.ex_comp_img,
                ex_user_prompt=COMPONENT_EXAMPLE_PROMPT_EN,
                ex_assistant_reply=COMPONENT_EXAMPLE_ASSISTANT_EN,
                max_tokens=512
            )
            
            response_text = response_text.strip()
            if "</think>" in response_text:
                return response_text.split("</think>")[-1].strip()
            return response_text
        except Exception as e:
            print(f"  [LocalVLM] 生成意图失败: {e}")
            return f"Swipe {direction} on this component"

    def generate_intent_for_click(self, image_path: str, bbox: list, context_text: str) -> str:
        """为点击操作生成意图"""
        try:
            w, h = 1080, 2400
            norm_bbox = [
                int(bbox[0]/w*1000), int(bbox[1]/h*1000),
                int(bbox[2]/w*1000), int(bbox[3]/h*1000)
            ]
            
            target_prompt = CLICK_TASK_PROMPT_EN.format(norm_bbox, context_text)
            target_image = Image.open(image_path).convert("RGB")
            
            # 点击意图同样复用 Component 的示例图（因为它也能表现出理解 Bbox 的能力）
            response_text = self._generate_text(
                target_image=target_image,
                target_prompt=target_prompt,
                ex_image=self.ex_comp_img,
                ex_user_prompt=CLICK_EXAMPLE_PROMPT_EN,
                ex_assistant_reply=CLICK_EXAMPLE_ASSISTANT_EN,
                max_tokens=512
            )
            
            response_text = response_text.strip()
            if "</think>" in response_text:
                return response_text.split("</think>")[-1].strip()
            return response_text
        except Exception as e:
            print(f"  [LocalVLM] 生成点击意图失败: {e}")
            return f"Tap on the component '{context_text}'"

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
            print(f"[LocalVLM] JSON 解析失败: {e}")
            return