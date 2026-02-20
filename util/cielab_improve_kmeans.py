import numpy as np
import cv2
from sklearn.cluster import KMeans
from itertools import combinations
import colorsys
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import os


class MoonSpencerHarmonySelector:
    def __init__(self):
        # Moon-Spencer美学因子 (基于原论文)
        self.identity_factors = {'H': 1.5, 'V': -1.3, 'C': 0.8}
        self.similarity_factors = {'H': 1.1, 'V': 0.7, 'C': 0.1}
        self.contrast_factors = {'H': 1.7, 'V': 3.7, 'C': 0.4}
        self.ambiguity1_factors = {'H': 0, 'V': -1.0, 'C': 0}
        self.ambiguity2_factors = {'H': 0.65, 'V': -0.20, 'C': 0}
        self.area_balance = 1.0
        self.gray_factor = 1.0
    def extract_candidate_colors(self, image, min_clusters=5, max_clusters=10):
        """基于二阶差分的自动肘部检测"""
        from scipy.signal import savgol_filter

        image_lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        pixels_lab = image_lab.reshape(-1, 3)

        # 1. 计算不同k值的惯性（总内部方差）
        inertias = []
        k_values = range(min_clusters, max_clusters + 1)

        for k in k_values:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(pixels_lab)
            inertias.append(kmeans.inertia_)

        inertias = np.array(inertias)

        # 2. 归一化惯性值到[0,1]范围
        inertias_normalized = (inertias - inertias.min()) / (inertias.max() - inertias.min())

        # 3. 平滑处理（使用Savitzky-Golay滤波器）
        if len(inertias_normalized) >= 5:
            inertias_smooth = savgol_filter(inertias_normalized,
                                            window_length=min(5, len(inertias_normalized) if len(
                                                inertias_normalized) % 2 == 1 else len(inertias_normalized) - 1),
                                            polyorder=2)
        else:
            inertias_smooth = inertias_normalized

        # 4. 计算一阶差分（斜率）
        first_derivative = np.diff(inertias_smooth)

        # 5. 计算二阶差分（曲率变化）
        second_derivative = np.diff(first_derivative)

        # 6. 找到二阶差分的最大值（曲率最大点 = 肘部）
        # 二阶差分最大值对应曲线向上弯曲最剧烈的点
        elbow_index = np.argmax(second_derivative) + 1  # +1因为差分降维
        optimal_k = min_clusters + elbow_index

        print(f"肘部法则（二阶差分）最优k值: {optimal_k}")
        print(f"惯性值: {inertias[elbow_index]:.2f}")

        # 7. 最终聚类
        kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        kmeans.fit(pixels_lab)
        centers_lab = kmeans.cluster_centers_

        # 转换回RGB
        centers_rgb = []
        for center_lab in centers_lab:
            center_rgb = cv2.cvtColor(center_lab.reshape(1, 1, 3).astype(np.uint8),
                                      cv2.COLOR_LAB2RGB).reshape(3)
            centers_rgb.append(center_rgb)

        # 可选：可视化肘部曲线

        return np.array(centers_rgb)



    def classify_color_relationship(self, color1, color2):
        """根据Moon-Spencer原论文分类颜色关系"""
        # 转换到HSV空间进行分析
        hsv1 = colorsys.rgb_to_hsv(color1[0] / 255, color1[1] / 255, color1[2] / 255)
        hsv2 = colorsys.rgb_to_hsv(color2[0] / 255, color2[1] / 255, color2[2] / 255)

        # 色相差异 (0-180度，考虑环形特性)
        hue_diff = min(abs(hsv1[0] - hsv2[0]), 1 - abs(hsv1[0] - hsv2[0])) * 360

        # 饱和度差异 (0-100)
        sat_diff = abs(hsv1[1] - hsv2[1]) * 100

        # 明度差异 (0-100)
        val_diff = abs(hsv1[2] - hsv2[2]) * 100

        # 根据论文的分类标准
        relationships = {'H': 'identity', 'V': 'identity', 'C': 'identity'}

        # 色相关系分类
        if hue_diff < 5:
            relationships['H'] = 'identity'
        elif hue_diff < 15:
            relationships['H'] = 'ambiguity1'  # 第一模糊性
        elif hue_diff < 30:
            relationships['H'] = 'similarity'
        elif hue_diff < 45:
            relationships['H'] = 'ambiguity2'  # 第二模糊性
        else:
            relationships['H'] = 'contrast'

        # 明度关系分类
        if val_diff < 10:
            relationships['V'] = 'identity'
        elif val_diff < 20:
            relationships['V'] = 'ambiguity1'
        elif val_diff < 30:
            relationships['V'] = 'similarity'
        elif val_diff < 40:
            relationships['V'] = 'ambiguity2'
        else:
            relationships['V'] = 'contrast'

        # 饱和度关系分类
        if sat_diff < 15:
            relationships['C'] = 'identity'
        elif sat_diff < 25:
            relationships['C'] = 'ambiguity1'
        elif sat_diff < 35:
            relationships['C'] = 'similarity'
        elif sat_diff < 45:
            relationships['C'] = 'ambiguity2'
        else:
            relationships['C'] = 'contrast'

        return relationships

    def calculate_complexity(self, colors):
        """计算复杂度因子C = (颜色数) + (色相差异对数) + (明度差异对数) + (饱和度差异对数)"""
        n_colors = len(colors)
        hue_diff_pairs = 0
        value_diff_pairs = 0
        chroma_diff_pairs = 0

        for i in range(n_colors):
            for j in range(i + 1, n_colors):
                relationships = self.classify_color_relationship(colors[i], colors[j])

                if relationships['H'] != 'identity':
                    hue_diff_pairs += 1
                if relationships['V'] != 'identity':
                    value_diff_pairs += 1
                if relationships['C'] != 'identity':
                    chroma_diff_pairs += 1

        complexity = n_colors + hue_diff_pairs + value_diff_pairs + chroma_diff_pairs
        return max(complexity, 1)  # 避免除零

    def calculate_order(self, colors):
        """计算顺序因子O"""
        n_colors = len(colors)

        # 统计各种关系的数量
        relation_counts = {
            'H': {'identity': 0, 'similarity': 0, 'contrast': 0, 'ambiguity1': 0, 'ambiguity2': 0},
            'V': {'identity': 0, 'similarity': 0, 'contrast': 0, 'ambiguity1': 0, 'ambiguity2': 0},
            'C': {'identity': 0, 'similarity': 0, 'contrast': 0, 'ambiguity1': 0, 'ambiguity2': 0}
        }

        # 统计所有颜色对的关系
        for i in range(n_colors):
            for j in range(i + 1, n_colors):
                relationships = self.classify_color_relationship(colors[i], colors[j])

                for dimension in ['H', 'V', 'C']:
                    relation_type = relationships[dimension]
                    relation_counts[dimension][relation_type] += 1

        # 计算顺序分数
        order_score = 0

        # 色相贡献
        order_score += (relation_counts['H']['identity'] * self.identity_factors['H'] +
                        relation_counts['H']['similarity'] * self.similarity_factors['H'] +
                        relation_counts['H']['contrast'] * self.contrast_factors['H'] +
                        relation_counts['H']['ambiguity1'] * self.ambiguity1_factors['H'] +
                        relation_counts['H']['ambiguity2'] * self.ambiguity2_factors['H'])

        # 明度贡献
        order_score += (relation_counts['V']['identity'] * self.identity_factors['V'] +
                        relation_counts['V']['similarity'] * self.similarity_factors['V'] +
                        relation_counts['V']['contrast'] * self.contrast_factors['V'] +
                        relation_counts['V']['ambiguity1'] * self.ambiguity1_factors['V'] +
                        relation_counts['V']['ambiguity2'] * self.ambiguity2_factors['V'])

        # 饱和度贡献
        order_score += (relation_counts['C']['identity'] * self.identity_factors['C'] +
                        relation_counts['C']['similarity'] * self.similarity_factors['C'] +
                        relation_counts['C']['contrast'] * self.contrast_factors['C'] +
                        relation_counts['C']['ambiguity1'] * self.ambiguity1_factors['C'] +
                        relation_counts['C']['ambiguity2'] * self.ambiguity2_factors['C'])

        # 面积平衡贡献 (假设等面积)
        # 对于n个颜色，有C(n,2)个颜色对，每对贡献area_balance
        num_pairs = n_colors * (n_colors - 1) // 2
        order_score += num_pairs * self.area_balance

        return max(order_score, 0.1)  # 确保为正值

        # 在 MoonSpencerHarmonySelector 类内部添加/修改

    def extract_candidate_colors_from_pixels(self, pixels, min_clusters=5, max_clusters=10):
        """
        修正后的从像素数组提取候选颜色方法
        pixels: (N, 3) 的 RGB numpy数组
        """
        # 0. 数据校验与形状处理
        if len(pixels) < min_clusters:
            # 如果像素太少，直接返回去重后的像素，不足补0
            return np.pad(pixels, ((0, max(0, min_clusters - len(pixels))), (0, 0)))

        # OpenCV的cvtColor需要 (1, N, 3) 或 (H, W, 3) 的形状
        pixels_reshaped = pixels.reshape(1, -1, 3).astype(np.uint8)

        # 转换到LAB颜色空间
        pixels_lab = cv2.cvtColor(pixels_reshaped, cv2.COLOR_RGB2LAB)
        pixels_lab = pixels_lab.reshape(-1, 3)  # 变回 (N, 3) 给 KMeans 用

        # 1. 肘部法则计算 (保持原逻辑，略微优化k range防止报错)
        inertias = []
        # 确保 max_clusters 不超过像素总数
        real_max_clusters = min(max_clusters, len(pixels))
        if real_max_clusters <= min_clusters:
            k_values = [min_clusters]
        else:
            k_values = range(min_clusters, real_max_clusters + 1)

        for k in k_values:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(pixels_lab)
            inertias.append(kmeans.inertia_)

        # 如果只有一个k值或惯性差异太小，直接取中间值
        if len(inertias) < 3:
            optimal_k = k_values[-1]
        else:
            # ... (保留你原本的平滑和二阶差分逻辑) ...
            inertias = np.array(inertias)
            inertias_normalized = (inertias - inertias.min()) / (inertias.max() - inertias.min() + 1e-6)

            # 简化版肘部检测，防止数据量少时报错
            try:
                first_derivative = np.diff(inertias_normalized)
                second_derivative = np.diff(first_derivative)
                elbow_index = np.argmax(second_derivative) + 1
                optimal_k = k_values[0] + elbow_index
            except:
                optimal_k = k_values[len(k_values) // 2]

        print(f"区域聚类 - 最优k值: {optimal_k}")

        # 7. 最终聚类
        kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        kmeans.fit(pixels_lab)
        centers_lab = kmeans.cluster_centers_

        # 转换回RGB
        centers_lab_reshaped = centers_lab.reshape(1, -1, 3).astype(np.uint8)
        centers_rgb = cv2.cvtColor(centers_lab_reshaped, cv2.COLOR_LAB2RGB).reshape(-1, 3)

        return np.array(centers_rgb)

    def extract_harmonious_palette_from_pixels(self, pixels, target_colors=5, method='exhaustive'):
        """
        【新增接口】专为分割区域设计：直接从像素点集生成最佳和谐色板
        """
        # 1. 提取候选颜色 (自动肘部法则)
        candidates = self.extract_candidate_colors_from_pixels(pixels)

        # 2. 如果候选颜色少于目标数量，直接返回
        if len(candidates) <= target_colors:
            selected_palette = candidates
        else:
            # 3. 选择最和谐的组合 (调用你原有的贪心或穷举逻辑)
            if method == 'exhaustive':
                selected_palette = self.select_best_palette_exhaustive(candidates, target_colors)
            else:
                selected_palette = self.select_best_palette_greedy(candidates, target_colors)

        # 4. 计算最终的和谐度分数
        harmony_score = self.calculate_moon_spencer_measure(selected_palette)

        return {
            'palette': selected_palette.tolist(),
            'harmony_score': harmony_score,
            'candidates': candidates.tolist(),
            'method': method
        }

    def calculate_moon_spencer_measure(self, colors):
        """计算Moon-Spencer美学测量值 M = O/C"""
        if len(colors) < 2:
            return 0

        order = self.calculate_order(colors)
        complexity = self.calculate_complexity(colors)

        return order / complexity

    def select_best_palette_greedy(self, candidates, target_num=5):
        """贪心算法：逐步添加能最大化和谐度的颜色"""
        if len(candidates) <= target_num:
            return candidates

        # 从第一个颜色开始
        selected = [candidates[0]]
        remaining = list(range(1, len(candidates)))

        for _ in range(target_num - 1):
            best_idx = None
            best_score = -float('inf')

            for idx in remaining:
                test_palette = np.vstack([selected, [candidates[idx]]])
                score = self.calculate_moon_spencer_measure(test_palette)

                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx is not None:
                selected.append(candidates[best_idx])
                remaining.remove(best_idx)

        return np.array(selected)

    def select_best_palette_exhaustive(self, candidates, target_num=5):
        """穷举法：尝试所有组合，选择和谐度最高的"""
        if len(candidates) <= target_num:
            return candidates

        # 限制组合数量以避免计算爆炸


        best_combination = None
        best_score = -float('inf')

        print(
            f"正在评估 C({len(candidates)}, {target_num}) = {len(list(combinations(range(len(candidates)), target_num)))} 种组合...")

        for indices in combinations(range(len(candidates)), target_num):
            palette = candidates[list(indices)]
            score = self.calculate_moon_spencer_measure(palette)

            if score > best_score:
                best_score = score
                best_combination = indices

        return candidates[list(best_combination)] if best_combination else candidates[:target_num]

    def extract_harmonious_palette_from_image(self, image, target_colors=5, method='exhaustive'):
        """
        从图像数组直接提取和谐调色板 - 与app.py接口一致

        参数:
        image: numpy数组，形状为 (height, width, 3) 的RGB图像数据
        target_colors: 目标颜色数量
        method: 选择方法 ('exhaustive' 或 'greedy')

        返回:
        字典，包含提取的调色板和和谐度分数
        """
        # 提取候选颜色
        candidates = self.extract_candidate_colors(image)

        # 选择最和谐的组合
        if method == 'exhaustive':
            selected_palette = self.select_best_palette_exhaustive(candidates, target_colors)
        else:
            selected_palette = self.select_best_palette_greedy(candidates, target_colors)

        # 计算最终的和谐度分数
        harmony_score = self.calculate_moon_spencer_measure(selected_palette)

        return {
            'palette': selected_palette.tolist(),
            'harmony_score': harmony_score,
            'candidates': candidates.tolist(),
            'method': method
        }

    def extract_harmonious_palette(self, image_path, target_colors=5, method='exhaustive'):
        image = get_image(image_path)

        """主要接口：从图像中提取最和谐的色板"""
        candidates = self.extract_candidate_colors(image)

        # 2. 选择最和谐的组合
        if method == 'exhaustive':
            selected_palette = self.select_best_palette_exhaustive(candidates, target_colors)
        else:
            selected_palette = self.select_best_palette_greedy(candidates, target_colors)

        # 3. 计算最终的和谐度分数
        harmony_score = self.calculate_moon_spencer_measure(selected_palette)

        return {
            'palette': selected_palette.tolist(),
            'harmony_score': harmony_score,
            'candidates': candidates.tolist(),
            'method': method
        }


def display_image_with_palette(image_path, result, save_path=None):
    """显示图片和提取的色板"""
    # 加载图片
    image = Image.open(image_path)
    image_rgb = np.array(image)

    # 创建图形
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 显示原始图片
    ax1.imshow(image_rgb)
    ax1.set_title(f'Original Image\n{os.path.basename(image_path)}', fontsize=12, fontweight='bold')
    ax1.axis('off')

    # 显示色板
    palette = np.array(result['palette'])
    n_colors = len(palette)

    # 创建色板矩形
    rect_width = 1.0 / n_colors
    for i, color in enumerate(palette):
        # 归一化颜色值到0-1范围
        normalized_color = color / 255.0
        rect = patches.Rectangle((i * rect_width, 0), rect_width, 1,
                                 facecolor=normalized_color, edgecolor='white', linewidth=2)
        ax2.add_patch(rect)

        # 添加RGB值标签
        rgb_text = f'RGB\n({int(color[0])}, {int(color[1])}, {int(color[2])})'
        text_color = 'white' if np.mean(color) < 128 else 'black'
        ax2.text(i * rect_width + rect_width / 2, 0.5, rgb_text,
                 ha='center', va='center', fontsize=8, color=text_color, fontweight='bold')

    # 设置色板子图属性
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.set_title(f'Extracted Color Palette\nHarmony Score: {result["harmony_score"]:.3f} | Method: {result["method"]}',
                  fontsize=12, fontweight='bold')
    ax2.axis('off')

    plt.tight_layout()

    # 保存图片（可选）
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"结果已保存到: {save_path}")

    plt.show()

    # 打印详细信息
    print("=" * 50)
    print(f"图片路径: {image_path}")
    print(f"提取方法: {result['method']}")
    print(f"和谐度分数: {result['harmony_score']:.3f}")
    print(f"色板颜色:")
    for i, color in enumerate(result['palette']):
        print(f"  颜色 {i + 1}: RGB({int(color[0])}, {int(color[1])}, {int(color[2])})")
    print("=" * 50)


# 使用示例
def example_usage():
    selector = MoonSpencerHarmonySelector()

    # 示例：从图像中提取色板
    # image = cv2.imread('your_image.jpg')
    # image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # 创建示例图像
    image = np.random.randint(0, 255, (400, 400, 3), dtype=np.uint8)

    # 使用贪心算法
    result_greedy = selector.extract_harmonious_palette(
        image, target_colors=5, method='greedy'
    )

    print("=== 贪心算法结果 ===")
    print(f"选择的色板: {result_greedy['palette']}")
    print(f"和谐度分数: {result_greedy['harmony_score']:.3f}")
    print(f"候选颜色数量: {len(result_greedy['candidates'])}")

    # 使用穷举算法 (候选数量较少时)
    result_exhaustive = selector.extract_harmonious_palette(
        image, target_colors=5, method='exhaustive'
    )

    print("\n=== 穷举算法结果 ===")
    print(f"选择的色板: {result_exhaustive['palette']}")
    print(f"和谐度分数: {result_exhaustive['harmony_score']:.3f}")
    print(f"使用方法: {result_exhaustive['method']}")

    return result_greedy, result_exhaustive


def test_moon_spencer_calculation():
    """测试Moon-Spencer计算的具体案例"""
    selector = MoonSpencerHarmonySelector()

    # 测试论文中的例子：R 6/8, R 5/8 (色相相同，明度相近，饱和度相同)
    test_colors = np.array([
        [200, 100, 100],  # 红色调1
        [180, 90, 100],  # 红色调2 (稍暗一点)
    ])

    print("=== 测试Moon-Spencer计算 ===")
    print(f"测试颜色: {test_colors.tolist()}")

    complexity = selector.calculate_complexity(test_colors)
    order = selector.calculate_order(test_colors)
    measure = selector.calculate_moon_spencer_measure(test_colors)

    print(f"复杂度 C: {complexity}")
    print(f"顺序 O: {order:.3f}")
    print(f"美学测量 M: {measure:.3f}")

    # 测试更多颜色的情况
    test_colors_5 = np.array([
        [200, 100, 100],  # 红色
        [100, 200, 100],  # 绿色
        [100, 100, 200],  # 蓝色
        [200, 200, 100],  # 黄色
        [200, 100, 200],  # 品红
    ])

    print(f"\n5色测试:")
    print(f"测试颜色: {test_colors_5.tolist()}")
    measure_5 = selector.calculate_moon_spencer_measure(test_colors_5)
    print(f"美学测量 M: {measure_5:.3f}")


def get_image(image_path, height=400):
    """
    【已重写】读取并调整图片尺寸，能够正确处理包含中文等非 ASCII 字符的路径。
    """
    # 步骤 1: 使用 Python 内置功能以二进制模式读取文件
    # np.fromfile 可以正确处理 unicode 路径，并读入为 numpy 数组
    try:
        image_data = np.fromfile(image_path, dtype=np.uint8)
    except FileNotFoundError:
        print(f"错误：找不到文件 '{image_path}'。请检查路径是否正确。")
        return None

    # 步骤 2: 使用 cv2.imdecode 从内存中的数据解码图像
    # cv2.IMREAD_COLOR 表示总是将图像读取为3通道的 BGR 彩色图像
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

    # 检查图像是否成功解码
    if image is None:
        print(f"错误：文件 '{image_path}' 不是有效的图片格式或文件已损坏。")
        return None

    # cv2.imdecode 解码后的图像是 BGR 格式，需要转换为 RGB
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # 按比例调整图片尺寸
    ratio = height / image.shape[0]
    width = int(image.shape[1] * ratio)
    resized_image = cv2.resize(image, (width, height))

    return resized_image

def show(image_path,candidate_colors):

        # 获取调整尺寸后的图片
        image = get_image(image_path)

        if image is not None:
            # 提取图片中的候选颜色
            # candidate_colors = color_extractor.extract_candidate_colors(image, max_distance=50, min_clusters=3,
            #                                                             max_clusters=15)            # 输出颜色结果
            print("提取的候选颜色：")
            for i, color in enumerate(candidate_colors):
                print(f"颜色 {i + 1}: {color}")

            # 创建一张图，将图片和颜色结合展示
            fig, ax = plt.subplots(figsize=(10, 6))

            # 显示原图
            ax.imshow(image)
            ax.axis('off')  # 关闭坐标轴

            # 在图片下方展示提取的颜色块
            color_bar_height = 100  # 颜色条的高度
            color_bar = np.zeros((color_bar_height, image.shape[1], 3), dtype=np.uint8)

            # 将提取的颜色填充到颜色条中
            for i, color in enumerate(candidate_colors):
                color_bar[:,
                i * (image.shape[1] // len(candidate_colors)):(i + 1) * (
                            image.shape[1] // len(candidate_colors))] = color

            # 显示颜色条
            ax_color = fig.add_axes([0.0, 0.0, 1.0, 0.1])  # 设置颜色条的位置
            ax_color.imshow(color_bar)
            ax_color.axis('off')  # 关闭坐标轴

            plt.show()

if __name__ == "__main__":
    # 创建选择器实例
    selector = MoonSpencerHarmonySelector()

    # 输入图片路径（请替换为您的图片路径）
    image_path = "E:\研究生\myproject\getpicture\emotion_picture_1_batch\peaceful\peaceful_gcOe9JA4_90.jpg"

    # 检查文件是否存在
    if not os.path.exists(image_path):
        print(f"错误：文件 '{image_path}' 不存在！")
        exit(1)

    try:
        # 使用改进的图片加载函数，支持中文路径
        if image_path is None:
            exit(1)

        # 设置参数
        target_colors = 5  # 目标色板颜色数量
        method = 'exhaustive'  # 使用贪心算法（更快）

        print(f"正在从图片中提取 {target_colors} 种和谐颜色...")

        # 提取色板
        result = selector.extract_harmonious_palette(
            image_path,
            target_colors=target_colors,
            method=method
        )
        palette = np.array(result['palette'])
        show(image_path,palette)
    #     display_image_with_palette(image_path, result)
    #
    #     # 可选：保存结果
    #     save_option = input("\n是否保存结果图片？(y/n): ").strip().lower()
    #     if save_option == 'y':
    #         base_name = os.path.splitext(os.path.basename(image_path))[0]
    #         save_path = f"{base_name}_palette_result.png"
    #         display_image_with_palette(image_path, result, save_path)

    except Exception as e:
        print(f"处理图片时发生错误: {e}")
        print("请确保图片文件格式正确且路径可访问。")