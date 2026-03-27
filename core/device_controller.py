# core/device_controller.py
import uiautomator2 as u2
import time
import os
import cv2
import xml.etree.ElementTree as ET
from pathlib import Path

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

    def click(self, x, y):
        self.d.click(x, y)
        time.sleep(0.5) # 1.5

    def reset_app(self, package_name):
        self.d.app_stop(package_name)
        time.sleep(1)
        self.d.app_start(package_name)
        time.sleep(3)

    def replay_trajectory(self, package_name, trajectory):
        self.reset_app(package_name)
        for action in trajectory:
            self.click(action['x'], action['y'])
            time.sleep(1)
    
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

    def calculate_image_diff(self, img_path1: str, img_path2: str, threshold=0.01) -> bool:
        """
        计算两张截图的像素级差异。
        用于判断滑动操作是否引发了界面的实质性改变。
        """
        import cv2
        import numpy as np
        
        img1 = cv2.imread(img_path1, cv2.IMREAD_GRAYSCALE)
        img2 = cv2.imread(img_path2, cv2.IMREAD_GRAYSCALE)
        
        if img1 is None or img2 is None:
            return False
            
        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            
        # 计算绝对差值
        diff = cv2.absdiff(img1, img2)
        # 二值化，过滤掉微小的渲染噪点（像素差大于10认为是变化）
        _, diff_thresh = cv2.threshold(diff, 10, 255, cv2.THRESH_BINARY)
        
        # 计算变化像素占总像素的比例
        change_ratio = np.count_nonzero(diff_thresh) / diff_thresh.size
        print(f"[Verify] 界面变化比例: {change_ratio:.4f} (阈值: {threshold})")
        
        return change_ratio > threshold
