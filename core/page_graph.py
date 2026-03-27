import json
import shutil
from pathlib import Path
from utils.image_utils import ImageUtils

class PageNode:
    def __init__(self, page_id: str, image_path: str, skeleton_path: str, trajectory: list):
        self.page_id = page_id
        self.image_path = image_path
        self.skeleton_path = skeleton_path
        self.trajectory = trajectory
        self.visited_elements = set()

class PageMemory:
    def __init__(self, package_name: str, similarity_threshold=0.85):
        self.pages =[]
        self.similarity_threshold = similarity_threshold
        
        # 创建属于该 App 的专属目录
        self.output_dir = Path("outputs") / package_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        
        # 将临时图移动/重命名为正式图
        shutil.move(temp_image_path, final_img_path)
        
        # 生成并保存骨架图
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
                "trajectory": p.trajectory
            })
        
        json_file = self.output_dir / "memory_graph.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"页面图谱已保存至: {json_file}")