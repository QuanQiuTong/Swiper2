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
    print(f"[Verify] UI change ratio: {change_ratio:.4f} (Threshold: {threshold})")
    
    return change_ratio > threshold
    

def mask(img, box, reason):
    """绘制美化的打码框，增强可解释性"""
    x1, y1, x2, y2 = box
    box_w, box_h = x2 - x1, y2 - y1
    
    # A. 绘制黑色填充背景框 (厚度参数 -1 表示实心填充)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
    
    # B. 绘制灰色外边框 (厚度为 2)
    cv2.rectangle(img, (x1, y1), (x2, y2), (128, 128, 128), 2)
    
    # C. 绘制打码原因文字 (白字)
    if box_w > 20 and box_h > 12: # 过滤掉极小的点（比如只是个10x10的像素点，写不下字）
        text_str = f"[{reason}]"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        
        # 获取该字体在当前设置下的像素宽和高
        (text_w, text_h), _ = cv2.getTextSize(text_str, font, font_scale, thickness)
        
        # 【核心】动态自适应字体大小，防止文字比黑框还要长导致溢出
        if text_w > box_w - 4:
            font_scale = font_scale * ((box_w - 4) / text_w)
            # 重新计算缩放后的尺寸
            (text_w, text_h), _ = cv2.getTextSize(text_str, font, font_scale, thickness)
        
        # 只有缩放后还能勉强看清（比例 > 0.15）的才画上去
        if font_scale > 0.15:
            # 计算文字居中的起始坐标
            text_x = int(x1 + (box_w - text_w) / 2)
            text_y = int(y1 + (box_h + text_h) / 2)
            # 写上白色文字，并使用 cv2.LINE_AA 开启抗锯齿让字体平滑
            cv2.putText(img, text_str, (text_x, text_y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    return img


W, H = 1080, 2400  # 适配 Android 15 / API 36 的默认屏幕分辨率
def convert(coords):
    """将坐标转换为适配 Android 15 / API 36 的格式"""
    if len(coords) != 2:
        raise ValueError("坐标必须是 (x, y) 格式")
    x, y = coords
    return [round(x*1000/W, 1), round(y*1000/H, 1)]