import json
import shutil
import os
import logging
from pathlib import Path
from utils.image_utils import ImageUtils

class PageNode:
    def __init__(self, page_id: str, image_path: str, skeleton_path: str, trajectory: list):
        self.page_id = page_id
        self.image_path = image_path
        self.skeleton_path = skeleton_path
        self.trajectory = trajectory
        self.visited_elements = set()
        self.scrollable_components =[]

class PageMemory:
    def __init__(self, package_name: str, similarity_threshold=0.85):
        self.pages =[]
        self.similarity_threshold = similarity_threshold
        
        # 创建属于该 App 的专属目录
        self.output_dir = Path("outputs") / package_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.json_file = self.output_dir / "memory_graph.json"

    def load_from_disk(self) -> bool:
        """从 JSON 恢复之前的探索进度"""
        if not self.json_file.exists():
            return False
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.pages =[]
            for item in data:
                node = PageNode(
                    page_id=item['page_id'],
                    image_path=item['image_path'],
                    skeleton_path=item['skeleton_path'],
                    trajectory=item['trajectory']
                )
                node.scrollable_components = item.get('scrollable_components',[])
                # 恢复已点击坐标的记忆集合
                node.visited_elements = set(tuple(x) for x in item.get('visited_elements',[]))
                self.pages.append(node)
            return True
        except Exception as e:
            logging.error(f"加载地图缓存失败: {e}")
            return False

    def is_new_page(self, new_image_path: str):
        if not self.pages:
            return True, None

        for page in self.pages:
            sim = ImageUtils.calculate_skeleton_similarity(page.image_path, new_image_path)
            if sim >= self.similarity_threshold:
                return False, page.page_id
        
        return True, None

    def add_page(self, temp_image_path: str, trajectory: list) -> str:
        """将临时截图正式收录为新的 Page"""
        page_index = len(self.pages)
        page_id = f"page_{page_index}"
        
        # 定义最终的存储路径
        final_img_path = self.output_dir / f"{page_id}.png"
        final_skel_path = self.output_dir / f"{page_id}_skeleton.png"
        final_xml_path = self.output_dir / f"{page_id}.xml"  # 新增
        
        # 移动临时图片到正式目录
        shutil.move(temp_image_path, final_img_path)
        
        # 将临时的 XML 也一并移动过去并重命名
        temp_xml_path = temp_image_path.replace('.png', '.xml')
        if os.path.exists(temp_xml_path):
            shutil.move(temp_xml_path, final_xml_path)
            
        ImageUtils.save_skeleton(str(final_img_path), str(final_skel_path))
        
        # 记录到内存
        new_page = PageNode(
            page_id=page_id,
            image_path=str(final_img_path),
            skeleton_path=str(final_skel_path),
            trajectory=trajectory
        )
        self.pages.append(new_page)
        return page_id

    def get_page(self, page_id: str) -> PageNode:
        for p in self.pages:
            if p.page_id == page_id:
                return p
        return None

    def save_to_disk(self):
        data =[]
        for p in self.pages:
            data.append({
                "page_id": p.page_id,
                "image_path": p.image_path,
                "skeleton_path": p.skeleton_path,
                "trajectory": p.trajectory,
                "scrollable_components": getattr(p, 'scrollable_components',[]),
                "visited_elements": list(p.visited_elements)  # 记录断点
            })
        
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"页面图谱已保存至: {self.json_file}")