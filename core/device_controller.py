# core/device_controller.py
import uiautomator2 as u2
import time
import os
import cv2
import xml.etree.ElementTree as ET
from pathlib import Path
from utils.image_utils import ImageUtils

class UIAutomatorController:
    def __init__(self, device_serial=None):
        self.d = u2.connect(device_serial)
        print(f"已连接设备: {self.d.info}")
        self.window_size = self.d.window_size()

    def _extract_all_text_from_node(self, node):
        """
        递归提取当前节点及其所有子孙节点中的文本和描述。
        返回一个包含所有有效文字的集合（去重）。
        """
        texts = set()
        
        # 提取当前节点的 text 和 content-desc
        text = node.attrib.get('text', '').strip()
        desc = node.attrib.get('content-desc', '').strip()
        if text: texts.add(text)
        if desc: texts.add(desc)
        
        # 递归遍历所有子孙节点
        for child in node:
            texts.update(self._extract_all_text_from_node(child))
            
        return texts

    def get_clickable_elements_xml(self):
        """
        获取所有可点击组件，并智能聚合其内部的文本。
        """
        elements =[]
        try:
            # 使用原生 XML 导出，速度极快且兼容 Android 15 / API 36
            xml_dump = self.d.dump_hierarchy()
            root = ET.fromstring(xml_dump)
            
            # 遍历所有节点
            for node in root.iter('node'):
                # 寻找 clickable 为 true 的节点
                if node.attrib.get('clickable') == 'true':
                    bounds_str = node.attrib.get('bounds')
                    if not bounds_str: continue
                        
                    # 解析 "[x1,y1][x2,y2]"
                    bounds_str = bounds_str.replace('][', ',').replace('[', '').replace(']', '')
                    x1, y1, x2, y2 = map(int, bounds_str.split(','))
                    
                    # 过滤无效坐标或超出屏幕的坐标
                    if x2 <= x1 or y2 <= y1: continue
                    if x1 < 0 or y1 < 0 or x2 > self.window_size[0] or y2 > self.window_size[1]: continue

                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    
                    # 【核心改进】调用递归函数，把容器肚子里的字全部榨取出来
                    aggregated_texts = self._extract_all_text_from_node(node)
                    
                    # 拼接成一个具有描述性的字符串
                    final_text = " | ".join(aggregated_texts) if aggregated_texts else ""
                    
                    elements.append({
                        'bounds':[x1, y1, x2, y2],
                        'center': (cx, cy),
                        'text': final_text,
                        'resourceId': node.attrib.get('resource-id', '')
                    })
        except Exception as e:
            print(f"解析 XML 获取可点击节点时失败: {e}")
            
        return elements

    def take_anonymized_screenshot(self, output_path: str):
        """
        截图并打码：使用原生 dump_hierarchy，完美绕过 XPath 限制。
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.d.screenshot(output_path)
        
        sensitive_keywords =['avatar', 'profile', 'username', 'email', 'phone', 'account', 'password', 'sign in', 'log in']
        boxes_to_mask =[]
        
        try:
            xml_dump = self.d.dump_hierarchy()
            root = ET.fromstring(xml_dump)
            
            for node in root.iter('node'):
                text = (node.attrib.get('text') or '').lower()
                desc = (node.attrib.get('content-desc') or '').lower()
                res_id = (node.attrib.get('resource-id') or '').lower()
                
                if any(kw in text for kw in sensitive_keywords) or \
                   any(kw in desc for kw in sensitive_keywords) or \
                   any(kw in res_id for kw in sensitive_keywords):
                    
                    bounds_str = node.attrib.get('bounds')
                    if bounds_str:
                        bounds_str = bounds_str.replace('][', ',').replace('[', '').replace(']', '')
                        coords = list(map(int, bounds_str.split(',')))
                        if len(coords) == 4:
                            boxes_to_mask.append(coords)
        except Exception as e:
            print(f"  [Anonymize] XML解析异常: {e}")
            
        if boxes_to_mask:
            img = cv2.imread(output_path)
            for box in boxes_to_mask:
                x1, y1, x2, y2 = box
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
            # 原图移动到_original.png，打码图覆盖原图
            # os.rename(output_path, output_path.replace(".png", "_original.png"))
            cv2.imwrite(output_path, img)
            print(f"  [Anonymize] 成功为 {len(boxes_to_mask)} 处敏感区域打码。")
            
        return output_path

    def take_screenshot(self, output_path: str):
        return self.take_anonymized_screenshot(output_path)

    def get_current_package(self):
        """获取当前正在前台运行的 App 包名"""
        try:
            return self.d.app_current()['package']
        except Exception:
            return ""

    def click(self, x, y, delay=1.5):
        """
        执行点击并等待。
        增加 delay 参数，以便区分“探索”和“回放”时的不同等待需求。
        """
        self.d.click(x, y)
        time.sleep(delay)

    def reset_app(self, package_name):
        self.d.app_stop(package_name)
        time.sleep(1)
        self.d.app_start(package_name)
        print(f"  [Device Controller] 已重置应用 {package_name}，等待完全启动")
        time.sleep(9)

    def replay_trajectory(self, package_name, trajectory):
        """
        重置 App，并带有步进状态校验的轨迹回放。
        每执行一步，都会动态校验是否到达了预期的中间页面状态。
        """
        self.reset_app(package_name)
        
        # 确保用于步进校验的临时目录存在
        temp_dir = Path("outputs") / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        for step_idx, action in enumerate(trajectory):
            # 点击当前步
            self.click(action['x'], action['y'], delay=1.0)
            
            expected_path = action.get('expected_image_path')
            if not expected_path or not os.path.exists(expected_path):
                # 兼容老数据：如果没有预期截图路径，退化为硬等待
                time.sleep(2.0)
                continue
                
            # --- 动态轮询校验当前步的页面状态 ---
            max_retries = 3
            wait_time = 2.0
            step_success = False
            
            for attempt in range(max_retries):
                verify_img = str(temp_dir / f"verify_step_{step_idx}_{int(time.time())}.png")
                self.take_screenshot(verify_img) # 同样会触发打码，保证比对的一致性
                
                # 计算当前屏幕与预期画面的骨架相似度
                sim = ImageUtils.calculate_skeleton_similarity(verify_img, expected_path)
                
                if os.path.exists(verify_img):
                    os.remove(verify_img) # 清理临时文件
                    
                if sim >= 0.85: # 相似度阈值
                    if attempt > 0:
                        print(f"      -> 步进 {step_idx+1}/{len(trajectory)} 加载成功 (耗时 ~{attempt * wait_time}s)")
                    step_success = True
                    break
                    
                print(f"      -> ⏳ 步进 {step_idx+1}/{len(trajectory)} 校验未通过 (相似度 {sim:.2f})，等待 {wait_time}s 重试 ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
                
            if not step_success:
                print(f"    -> ❌ 轨迹回放失败于第 {step_idx+1} 步: {action.get('desc', '未知操作')}")
                return False
                
        return True
    
    def swipe_by_normalized_bbox(self, bbox: list, direction: str, duration=0.3):
        """
        根据 VLM 给出的归一化 bbox [0-1000] 和方向，计算真实的物理坐标并执行滑动。
        为了符合直觉：
        - vertical (向下浏览内容)：手指从下往上滑 (y从大到小)
        - horizontal (向右浏览内容)：手指从右往左滑 (x从大到小)
        """
        w, h = self.window_size
        # 转换为物理像素坐标
        x1, y1 = bbox[0] * w / 1000, bbox[1] * h / 1000
        x2, y2 = bbox[2] * w / 1000, bbox[3] * h / 1000
        
        # 计算区域的中心
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        
        # 计算滑动的起止点 (留出 20% 的边距防止滑出边界)
        box_w = x2 - x1
        box_h = y2 - y1
        
        if direction.lower() == "vertical":
            start_x = end_x = cx
            start_y = y1 + box_h * 0.8
            end_y = y1 + box_h * 0.2
        else: # horizontal
            start_y = end_y = cy
            start_x = x1 + box_w * 0.8
            end_x = x1 + box_w * 0.2

        print(f"    [Action] 执行滑动: ({int(start_x)}, {int(start_y)}) -> ({int(end_x)}, {int(end_y)})")
        self.d.swipe(start_x, start_y, end_x, end_y, duration=duration)
        time.sleep(2) # 等待滑动动画和内容加载完成

        # 返回执行的真实参数，用于保存数据集
        return {
            "start":[int(start_x), int(start_y)],
            "end": [int(end_x), int(end_y)],
            "duration": duration
        }

    def get_scrollable_elements_xml(self):
        """
        利用 XML 提取明确的可滑动组件 (Scrollable Components)。
        依据：scrollable="true" 或者是拖动条 (SeekBar)。
        """
        elements =[]
        try:
            xml_dump = self.d.dump_hierarchy()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_dump)
            
            for node in root.iter('node'):
                is_scrollable = node.attrib.get('scrollable') == 'true'
                is_seekbar = 'SeekBar' in node.attrib.get('class', '')
                
                if is_scrollable or is_seekbar:
                    bounds_str = node.attrib.get('bounds')
                    if not bounds_str: continue
                        
                    bounds_str = bounds_str.replace('][', ',').replace('[', '').replace(']', '')
                    x1, y1, x2, y2 = map(int, bounds_str.split(','))
                    
                    if x2 <= x1 or y2 <= y1: continue
                    
                    # 确定滑动的优势方向 (Dominant Axis)
                    width = x2 - x1
                    height = y2 - y1
                    # 如果高度大于宽度，通常是上下滑动；反之则是左右滑动
                    direction = "vertical" if height > width else "horizontal"
                    
                    # 提取组件内可能包含的文字（借鉴之前的聚合思想）
                    aggregated_texts = self._extract_all_text_from_node(node)
                    final_text = " | ".join(aggregated_texts) if aggregated_texts else "无文本内容"
                    
                    elements.append({
                        'category': 'component', # 标记为明确的组件
                        'bounds': [x1, y1, x2, y2],
                        'direction': direction,
                        'text': final_text,
                        'resourceId': node.attrib.get('resource-id', '')
                    })
        except Exception as e:
            print(f"解析 XML 获取滑动节点失败: {e}")
            
        return elements