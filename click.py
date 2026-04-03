import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from core.vlm_client import VLMClient
# 假设你的 image_utils 里有 convert 函数，如果没有可以直接用后面的归一化逻辑
# from utils.image_utils import convert 

class OfflineClickSynthesis:
    def __init__(self, package_name: str):
        self.package = package_name
        self.vlm = VLMClient(server_url="http://127.0.0.1:8000")
        
        self.input_dir = Path("outputs") / self.package
        self.memory_file = self.input_dir / "memory_graph.json"
        
        self.output_dir = Path("click") / f"{self.package}_dataset"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.dataset_file = self.output_dir / "click_dataset.json"
        self.click_data =[]
        
        if self.dataset_file.exists():
            with open(self.dataset_file, 'r', encoding='utf-8') as f:
                self.click_data = json.load(f)
            print(f"📦 已恢复 {len(self.click_data)} 条离线点击数据。")

    def _get_parent_page(self, pages, child_trajectory):
        """寻找当前页面的上一级页面"""
        if not child_trajectory:
            return None
        parent_traj = child_trajectory[:-1]
        for p in pages:
            if len(p['trajectory']) != len(parent_traj):
                continue
            match = True
            for a, b in zip(p['trajectory'], parent_traj):
                if a['x'] != b['x'] or a['y'] != b['y']:
                    match = False
                    break
            if match:
                return p
        return None

    def _find_bbox_from_xml(self, xml_path: str, cx: int, cy: int) -> list:
        """
        解析 XML 文件，通过中心点 (cx, cy) 反向推导出元素的原始 bbox。
        """
        if not os.path.exists(xml_path):
            return None
            
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for node in root.iter('node'):
                if node.attrib.get('clickable') == 'true':
                    bounds_str = node.attrib.get('bounds')
                    if bounds_str:
                        bounds_str = bounds_str.replace('][', ',').replace('[', '').replace(']', '')
                        x1, y1, x2, y2 = map(int, bounds_str.split(','))
                        
                        # Phase 1 里的计算公式：cx = (x1 + x2) // 2
                        node_cx, node_cy = (x1 + x2) // 2, (y1 + y2) // 2
                        
                        # 允许 2 像素的取整误差
                        if abs(node_cx - cx) <= 2 and abs(node_cy - cy) <= 2:
                            return[x1, y1, x2, y2]
        except Exception as e:
            print(f"  ⚠️ 解析 XML {xml_path} 失败: {e}")
            
        return None

    def run_synthesis(self):
        if not self.memory_file.exists():
            print(f"❌ 找不到 {self.memory_file}")
            return
            
        with open(self.memory_file, 'r', encoding='utf-8') as f:
            pages = json.load(f)
            
        print(f"=== 启动纯离线 Click 数据合成 (App: {self.package}) ===")
        print(f"共加载 {len(pages)} 个探索节点。")

        processed_targets = {item.get('target_page') for item in self.click_data}

        for page in pages:
            if not page['trajectory']:
                continue
                
            page_id = page['page_id']
            if page_id in processed_targets:
                print(f"  ⏭️ {page_id} 的点击数据已生成，跳过。")
                continue
                
            parent_page = self._get_parent_page(pages, page['trajectory'])
            if not parent_page:
                print(f"  ⚠️ 找不到 {page_id} 的父页面，跳过。")
                continue
                
            action = page['trajectory'][-1]
            cx, cy = action['x'], action['y']
            desc = action.get('desc', '未知组件')
            
            before_img = parent_page['image_path']
            after_img = page['image_path']
            
            # 获取对应的 XML 文件路径
            before_xml = before_img.replace('.png', '.xml')
            
            print(f"\n--- 分析动作: 从 {parent_page['page_id']} 点击 ({cx}, {cy}) [{desc}] -> 到达 {page_id} ---")
            
            if not os.path.exists(before_img):
                print(f"  ❌ 找不到原始截图 {before_img}，跳过。")
                continue

            # 【核心逻辑】从 XML 中逆推 bbox
            physical_bbox = self._find_bbox_from_xml(before_xml, cx, cy)
            
            if not physical_bbox:
                print(f"  ⚠️ 在 XML 中未找到匹配的边界框，将使用中心点生成一个 40x40 的虚拟 bbox。")
                physical_bbox =[max(0, cx-20), max(0, cy-20), cx+20, cy+20]

            # 调用 VLM 生成指令 (此时传入的是真实 bbox)
            instruction = self.vlm.generate_intent_for_click(before_img, physical_bbox, desc)
            print(f"  💡 意图生成: {instruction}")
            
            # 归一化坐标供最终 JSON 使用
            w, h = 1080, 2400
            norm_bbox = [
                int(physical_bbox[0]/w*1000), int(physical_bbox[1]/h*1000),
                int(physical_bbox[2]/w*1000), int(physical_bbox[3]/h*1000)
            ]
            norm_x, norm_y = int(cx/w*1000), int(cy/h*1000)
            
            # 组装与 swipe 格式对齐的 action_data
            data_entry = {
                "img_filename": before_img,  
                "target_page": page_id,      
                "after_image": after_img,    
                "action_data": {
                    "action": "click",
                    "bbox": norm_bbox,       # 完美补上了 bbox！
                    "start": [norm_x, norm_y],
                    "end": [norm_x, norm_y], 
                    "instruction": instruction,
                    "description": desc
                }
            }
            
            self.click_data.append(data_entry)
            
            # 实时去重并存盘
            unique_clicks = {s['target_page']: s for s in self.click_data}
            self.click_data = list(unique_clicks.values())
            
            with open(self.dataset_file, 'w', encoding='utf-8') as f:
                json.dump(self.click_data, f, ensure_ascii=False, indent=2)

        print(f"\n=== 离线生成完成！共获得 {len(self.click_data)} 条高质量点击数据。 ===")


from utils.packages import PACKAGE_ANDROID_WORLD, PACKAGE_NEW, PACKAGE_HOT_GLOBAL, PACKAGE_HOT_CN, PACKAGE_INSTALLED

if __name__ == "__main__":
    for target_app in PACKAGE_INSTALLED.values():
        OfflineClickSynthesis(package_name=target_app).run_synthesis()