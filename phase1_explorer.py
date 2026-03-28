import time
import os
from pathlib import Path
from core.device_controller import UIAutomatorController
from core.page_graph import PageMemory
from utils.image_utils import ImageUtils  # 引入图像处理工具用于比对

class Phase1Explorer:
    def __init__(self, package_name: str, max_depth=3):
        self.package = package_name
        self.max_depth = max_depth
        self.controller = UIAutomatorController()
        self.memory = PageMemory(package_name=self.package, similarity_threshold=0.85)
        
        # 专门存放点完之后的临时截图，判断完后如果是旧图就删掉，新图就挪走
        self.temp_dir = Path("outputs") / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _replay_and_verify(self, target_page, max_retries=4, wait_time=2.0):
        """
        回放轨迹，并通过骨架图相似度动态验证是否真正到达了目标页面。
        """
        # 执行回放操作
        self.controller.replay_trajectory(self.package, target_page.trajectory)
        
        # 轮询验证当前屏幕状态
        for attempt in range(max_retries):
            verify_img = str(self.temp_dir / f"verify_{int(time.time())}.png")
            self.controller.take_screenshot(verify_img) # 同样会调用打码截图
            
            # 计算当前屏幕与目标页面原存档图的骨架相似度
            sim = ImageUtils.calculate_skeleton_similarity(verify_img, target_page.image_path)
            os.remove(verify_img) # 清理临时文件
            
            if sim >= self.memory.similarity_threshold:
                # 如果是第一把就成功，说明页面很快，0秒额外等待；否则说明是等了一段时间才加载出来
                if attempt > 0:
                    print(f"    -> ✅ 页面加载成功 (耗时 ~{attempt * wait_time}s)")
                return True
                
            print(f"    -> ⏳ 页面未加载完或状态异常 (相似度 {sim:.2f} < 阈值)，等待 {wait_time}s 重试 ({attempt+1}/{max_retries})...")
            time.sleep(wait_time)
            
        return False
        
    def run_exploration(self):
        print(f"=== 启动 Phase 1 纯自动化探索 (App: {self.package}) ===")
        
        # 1. 启动并处理首页
        self.controller.reset_app(self.package)
        temp_home = str(self.temp_dir / "temp_home.png")
        self.controller.take_screenshot(temp_home)
        home_page_id = self.memory.add_page(temp_home, trajectory=[])
        print(f"记录首页: {home_page_id}")

        queue =[home_page_id]

        while queue:
            current_page_id = queue.pop(0)
            current_page = self.memory.get_page(current_page_id)
            
            if len(current_page.trajectory) >= self.max_depth:
                continue

            print(f"\n--- 正在探索页面: {current_page_id} (深度: {len(current_page.trajectory)}) ---")
            
            # 【改进点1】首次进入该页面前的回放与动态验证
            if len(current_page.trajectory) > 0:
                if not self._replay_and_verify(current_page):
                    print(f"  -> ❌ 无法稳定回放至 {current_page_id}，可能遇到无法关闭的弹窗或网络错误。放弃该页面探索。")
                    continue
            
            elements = self.controller.get_clickable_elements_xml()
            print(f"检测到 {len(elements)} 个可点击元素。")

            for elem in elements:
                cx, cy = elem['center']
                
                # 去重逻辑
                if any(abs(cx - vx) < 20 and abs(cy - vy) < 20 for vx, vy in current_page.visited_elements):
                    continue
                
                current_page.visited_elements.add((cx, cy))
                
                btn_name = elem.get('text') or elem.get('desc') or '未知组件'
                print(f"[{current_page_id}] 点击: ({cx}, {cy}) [{btn_name}]")
                
                action = {'x': cx, 'y': cy, 'desc': btn_name}
                new_trajectory = current_page.trajectory + [action]

                # 探索点击时，依然保持一个较短的固定等待，给新页面的转场留一点点时间
                self.controller.click(cx, cy, delay=1.5)
                
                # 防逃逸检查
                current_pkg = self.controller.get_current_package()
                if current_pkg != self.package:
                    print(f"  -> ⚠️ 意外跳出目标应用 (当前位于: {current_pkg})。放弃该分支。")
                    # 发生逃逸，必须将画面拉回 current_page 以便点击下一个按钮
                    if not self._replay_and_verify(current_page):
                        print("  -> ❌ 严重错误：无法恢复到基础页面，终止该页面的后续元素探索。")
                        break
                    continue
                
                # 截取新页面临时图
                temp_img = str(self.temp_dir / f"temp_{int(time.time())}.png")
                self.controller.take_screenshot(temp_img)
                
                is_new, matched_id = self.memory.is_new_page(temp_img)

                if is_new:
                    new_page_id = self.memory.add_page(temp_img, new_trajectory)
                    print(f"  -> ⭐ 发现新页面骨架! 记录为 {new_page_id}")

                    new_page_node = self.memory.get_page(new_page_id)
                    new_page_node.scrollable_components = self.controller.get_scrollable_elements_xml()
                    print(f"     已提取并保存 {len(new_page_node.scrollable_components)} 个 XML 可滑动组件。")
                    
                    queue.append(new_page_id)
                else:
                    print(f"  -> 页面未产生结构性变化 (骨架匹配到 {matched_id})")
                    os.remove(temp_img)

                # 【改进点2】点完一个按钮后，恢复状态以点击下一个按钮。加入动态验证
                if not self._replay_and_verify(current_page):
                    print("  -> ❌ 严重错误：无法恢复到基础页面，终止该页面的后续元素探索。")
                    break

        self.memory.save_to_disk()
        print(f"\n=== Phase 1 探索完成。共发现 {len(self.memory.pages)} 个独立结构页面 ===")

if __name__ == "__main__":
    target_app = "com.deepseek.chat"
    explorer = Phase1Explorer(package_name=target_app, max_depth=2)
    explorer.run_exploration()