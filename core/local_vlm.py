import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from PIL import Image
import json
from pathlib import Path

class LocalVLMClient:
    def __init__(self, model_path=r"D:\Games\Qwen3-VL-4B-Instruct"):
        """初始化并加载本地的 Qwen3-VL 模型"""
        print(f"  [LocalVLM] 正在加载本地模型: {model_path} ...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 加载模型 (默认使用 fp16 精度以节省显存，Qwen3-VL-4B 大约需要 8-10GB 显存)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            trust_remote_code=True
        )
        
        # 加载处理器
        self.processor = AutoProcessor.from_pretrained(
            model_path,
            trust_remote_code=True
        )
        self.model.eval()
        print(f"[LocalVLM] 模型加载完成！当前使用设备: {self.device}")

    def analyze_slidable_regions(self, image_path: str) -> list:
        """读取本地图片，本地跑前向推理，返回可滑动区域列表"""
        prompt = """请仔细分析这张移动应用UI界面截图，找出所有可滑动的区域（如列表、轮播图、页面整体等）。
只输出最多前4个可滑动区域的详细信息。
对于每个区域，请提供：
1. category: "slidable"
2. type: 具体类型描述（如：列表、轮播图、大区块）
3. direction: 滑动方向（"vertical" 或 "horizontal"）
4. bbox: 边界框坐标[x1, y1, x2, y2]，x和y的范围是0到1000的归一化坐标
5. description: 对该区域上滑动操作意图的描述

请务必严格以JSON数组格式输出，每个元素是一个对象。只输出JSON，不要有其他文字说明。
"""
        try:
            print(f"  [LocalVLM] 正在分析图片: {Path(image_path).name} ...")
            image = Image.open(image_path).convert("RGB")
            
            # 构造 Qwen3-VL 需要的 message 格式
            messages = [
                {
                    "role": "user",
                    "content":[
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            
            # 模板套用
            text = self.processor.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True
            )
            
            # 数据预处理
            inputs = self.processor(
                text=[text],
                images=[image],
                padding=True,
                return_tensors="pt"
            ).to(self.device)
            
            # 模型生成
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=False  # 关闭随机采样，保证输出更确定的 JSON 结构
                )
            
            # 截取新生成的 tokens（去掉 prompt 部分）
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            # 解码结果
            response_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]
            
            print(f"  [LocalVLM] 模型原始输出 -> \n{response_text}\n")
            return self._parse_json_response(response_text)
            
        except Exception as e:
            print(f"  [LocalVLM] 推理发生错误: {e}")
            return[]

    def _parse_json_response(self, text: str) -> list:
        """从大模型的文本中剥离并解析 JSON 数组"""
        start = text.find('[')
        end = text.rfind(']') + 1
        if start == -1 or end == 0:
            return []
        
        json_str = text[start:end]
        try:
            regions = json.loads(json_str)
            valid_regions =[]
            for r in regions:
                if 'bbox' in r and len(r['bbox']) == 4:
                    valid_regions.append(r)
            return valid_regions
        except Exception as e:
            print(f"  [LocalVLM] JSON 解析失败: {e}\n  [解析用字符串]: {json_str}")
            return[]