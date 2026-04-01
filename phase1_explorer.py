import time
import os
import logging
from pathlib import Path
from core.device_controller import UIAutomatorController
from core.page_graph import PageMemory

class Phase1Explorer:
    def __init__(self, package_name: str, max_depth=3):
        self.package = package_name
        self.max_depth = max_depth
        self.controller = UIAutomatorController()
        self.memory = PageMemory(package_name=self.package, similarity_threshold=0.85)
        
        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def run_exploration(self):
        """核心的 BFS 探索主循环"""
        logging.info(f"=== 启动 Phase 1 纯自动化探索 (App: {self.package}) ===")
        
        queue =[]
        
        # 【断点续传】加载已有进度
        if self.memory.load_from_disk():
            logging.info(f"  -> 📦 发现已有探索进度，成功恢复 {len(self.memory.pages)} 个页面地图！")
            # 扫描所有未满深度的页面重新加入探索队列
            for p in self.memory.pages:
                if len(p.trajectory) < self.max_depth:
                    queue.append(p.page_id)
        else:
            self.controller.reset_app(self.package)
            time.sleep(4) # 权宜之计
            # 疑似没必要 # self.controller.wait_for_loading_to_finish()
            
            temp_home = str(self.temp_dir / "temp_home.png")
            self.controller.take_screenshot(temp_home)
            # 【修改点】首页没有父节点，传入 parent_page_id=None
            home_page_id = self.memory.add_page(temp_home, trajectory=[], parent_page_id=None)
            logging.info(f"记录首页: {home_page_id}")
            queue.append(home_page_id)

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)
            
            if len(current_page.trajectory) >= self.max_depth:
                continue

            logging.info(f"\n--- 正在探索页面: {current_page_id} (深度: {len(current_page.trajectory)}) ---")
            
            # 回放处理（如果断点恢复时刚好在查 page_0，则必须主动回到首页）
            if len(current_page.trajectory) == 0:
                logging.info(f"  -> [重置] 正在启动回到首页...")
                self.controller.reset_app(self.package)
                time.sleep(3) 
            else:
                if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                    logging.error(f"  -> ❌ 无法稳定回放至 {current_page_id}，放弃该页面探索。")
                    continue
            time.sleep(5) # 权宜之计
            
            elements = self.controller.get_clickable_elements_xml()
                
            logging.info(f"检测到 {len(elements)} 个可点击元素。")

            for elem in elements:

                time.sleep(3) # 权宜之计
                success = self._explore_single_element(elem, current_page, queue)
                if not success:
                    # 如果返回 False，说明发生了致命错误（如无法回退到基础页面或 ADB 断开），中断当前页面的后续探索
                    break

        self.memory.save_to_disk()
        logging.info(f"\n=== Phase 1 探索完成。共发现 {len(self.memory.pages)} 个独立结构页面 ===")

    def _explore_single_element(self, elem: dict, current_page, queue: list) -> bool:
        """
        处理【单个可点击元素】的探索逻辑（点击、防抖、截图、对比、回放）。
        :return: True 表示继续遍历下一个元素，False 表示遇到严重错误需终止当前页面遍历。
        """
        cx, cy = elem['center']
        
         # 去重
        if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
            return True
        
        # 标记并保存进度
        current_page.visited_elements.add((cx, cy))
        self.memory.save_to_disk() 
        
        btn_name = elem.get('text') or elem.get('desc') or '未知组件'
        logging.info(f"[{current_page.page_id}] 点击: ({cx}, {cy}) [{btn_name}]")
        
        # 把 bbox 直接存下来，供 Phase 2 生成意图使用
        action = {
            'x': cx, 
            'y': cy, 
            'bbox': elem['bounds'], 
            'desc': btn_name, 
            'expected_image_path': ''
        }
        new_trajectory = current_page.trajectory + [action]

        self.controller.click(cx, cy, delay=2.5)

        # 智能防抖：等待加载动画结束
        self.controller.wait_for_loading_to_finish()

        # 防逃逸检查
        current_pkg = self.controller.get_current_package()
        if current_pkg != self.package:
            logging.warning(f"  -> ⚠️ 意外跳出目标应用 (当前位于: {current_pkg})。放弃该分支。")
            if not self.controller.replay_trajectory(self.package, current_page.trajectory):
                logging.error("  -> ❌ 严重错误：无法恢复到基础页面，终止该页面的后续元素探索。")
                return False # 致命错误
            return True # 成功恢复，继续下一个元素 (相当于原循环的 continue)
        
        # 截取新状态并比对
        temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
        self.controller.take_screenshot(temp_img)
        is_new, matched_id = self.memory.is_new_page(temp_img)

        if is_new:
            # 【修改点】传入当前页面 ID 作为新页面的 parent_page_id
            new_page_id = self.memory.add_page(temp_img, new_trajectory, parent_page_id=current_page.page_id)
            logging.info(f"  -> ⭐ 发现新页面骨架! 记录为 {new_page_id}")

            new_page_node = self.memory.get_page(new_page_id)
            new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
            logging.info(f"     已提取并保存 {len(new_page_node.scrollable_components)} 个 XML 可滑动组件。")
            
            action['expected_image_path'] = new_page_node.image_path
            queue.append(new_page_id)
        else:
            logging.info(f"  -> 页面未产生结构性变化 (骨架匹配到 {matched_id})")
            matched_page_node = self.memory.get_page(matched_id)
            action['expected_image_path'] = matched_page_node.image_path
            
            if os.path.exists(temp_img):
                os.remove(temp_img)
            temp_xml = temp_img.replace('.png', '.xml')
            if os.path.exists(temp_xml):
                os.remove(temp_xml)

        self.memory.save_to_disk()

        # 探索完当前分支，恢复到当前页面的初始状态，以便点击下一个元素
        if not self.controller.replay_trajectory(self.package, current_page.trajectory):
            logging.error("  -> ❌ 严重错误：无法恢复到基础页面，终止该页面的后续元素探索。")
            return False

        return True # 一切顺利，告诉 for 循环继续