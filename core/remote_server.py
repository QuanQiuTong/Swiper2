import base64
import io
import torch
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForImageTextToText, AutoProcessor
import json
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "inference_log.jsonl"

MODEL_PATH = "" # 请确认你的模型路径
MAX_NEW_TOKENS = 2048 # 加大 Token 数量以容纳 <think>

print("Loading model...")
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_PATH,
    dtype=torch.float16,  # 修复了警告
    device_map="auto",
    trust_remote_code=True
)
processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model.eval()
print("Model loaded.")

app = FastAPI(title="Remote VLM Inference Server")

class InferRequest(BaseModel):
    target_image_base64: str
    target_user_prompt: str
    # One-Shot 示例参数 (可选)
    example_image_base64: str = None
    example_user_prompt: str = ""
    example_assistant_reply: str = ""

@app.post("/infer")
def infer(req: InferRequest):
    print("Received inference request.")
    try:
        # 1. 解析目标图片
        tg_bytes = base64.b64decode(req.target_image_base64)
        tg_image = Image.open(io.BytesIO(tg_bytes)).convert("RGB")
        
        messages =[]
        
        # 2. 如果提供了 One-Shot 示例，先构造两轮对话
        if req.example_image_base64:
            ex_bytes = base64.b64decode(req.example_image_base64)
            ex_image = Image.open(io.BytesIO(ex_bytes)).convert("RGB")
            
            # Turn 1: 示例问题
            messages.append({
                "role": "user",
                "content":[
                    {"type": "image", "image": ex_image},
                    {"type": "text", "text": req.example_user_prompt}
                ]
            })
            # Turn 2: 示例回答
            messages.append({
                "role": "assistant",
                "content": req.example_assistant_reply
            })
            
        # 3. 构造实际的目标问题
        target_text = req.target_user_prompt
        if req.example_image_base64:
            target_text = f"Now please analyze the current screenshot based on the standards above.\n\n{req.target_user_prompt}"

        messages.append({
            "role": "user",
            "content":[
                {"type": "image", "image": tg_image},
                {"type": "text", "text": target_text}
            ]
        })

        # 4. 模型推理
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        # 提取传入的所有图片
        images = [img["image"] for msg in messages for img in msg["content"] if img["type"] == "image"]

        inputs = processor(text=[text], images=images, return_tensors="pt", padding=True).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)

        gen_ids = output_ids[:, inputs.input_ids.shape[1]:]
        result_text = processor.batch_decode(gen_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

        return {"text": result_text}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 补上启动服务器的代码
# ==========================================
if __name__ == "__main__":
    import uvicorn
    print("Starting Uvicorn server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)