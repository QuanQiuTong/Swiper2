import cv2
import numpy as np

class ImageUtils:
    @staticmethod
    def get_skeleton_image(image_path: str) -> np.ndarray:
        """提取图像的骨架图"""
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        
        # 1. 缩小分辨率，抹平过细的细节
        scale_percent = 300 / img.shape[1]
        width = int(img.shape[1] * scale_percent)
        height = int(img.shape[0] * scale_percent)
        resized = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
        
        # 2. 高斯模糊，进一步去除内容纹理
        blurred = cv2.GaussianBlur(resized, (5, 5), 0)
        
        # 3. 边缘检测，提取UI组件的边界骨架
        edges = cv2.Canny(blurred, 50, 150)
        
        # 4. 膨胀操作，让组件的边框更加粗壮连贯
        kernel = np.ones((3, 3), np.uint8)
        skeleton = cv2.dilate(edges, kernel, iterations=1)
        
        return skeleton

    @staticmethod
    def save_skeleton(image_path: str, output_path: str):
        """生成并保存骨架图用于直观展示"""
        skeleton = ImageUtils.get_skeleton_image(image_path)
        cv2.imwrite(output_path, skeleton)

    @staticmethod
    def calculate_skeleton_similarity(img_path1: str, img_path2: str) -> float:
        """计算两张截图的骨架相似度"""
        skel1 = ImageUtils.get_skeleton_image(img_path1)
        skel2 = ImageUtils.get_skeleton_image(img_path2)
        
        if skel1.shape != skel2.shape:
            skel2 = cv2.resize(skel2, (skel1.shape[1], skel1.shape[0]))
            
        intersection = np.logical_and(skel1 > 0, skel2 > 0)
        union = np.logical_or(skel1 > 0, skel2 > 0)
        
        union_sum = np.sum(union)
        if union_sum == 0:
            return 1.0
            
        return np.sum(intersection) / union_sum
    
def calculate_image_diff(img_path1: str, img_path2: str, threshold=0.01) -> bool:
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
    
H, W = 1080, 2400  # 适配 Android 15 / API 36 的默认屏幕分辨率
def convert(*coords):
    """将坐标转换为适配 Android 15 / API 36 的格式"""
    if len(coords) != 2:
        raise ValueError("坐标必须是 (x, y) 格式")
    x, y = coords
    return [round(x*1000/W, 1), round(y*1000/H, 1)]