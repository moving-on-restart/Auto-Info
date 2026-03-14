# -*- coding: utf-8 -*-
"""
som_module/som_trainer.py
=========================
核心 SOM 训练模块。

本文件是整个子模块中最适合修改算法的地方，包含：
  1. 多模态嵌入构建（NLP + 共现 + 类别 + 层级 + 图结构）
  2. MiniSom 训练
  3. 元素到网格节点的最优分配（匈牙利算法）

修改建议：
  - 调整各模态的权重：直接修改 config.py 中的 WEIGHT_* 常量
  - 替换文本模型：修改 config.TEXT_MODEL_NAME
  - 尝试不同的 SOM 参数：修改 config.SOM_* 常量
  - 替换嵌入方式：修改 _build_embeddings() 函数
  - 替换分配算法：修改 _assign_elements_to_nodes() 函数
"""

import math
import threading

from . import config

# 全局文本模型缓存（避免重复加载）
_TEXT_MODEL = None
_TEXT_MODEL_LOCK = threading.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────────────────────

def _get_text_model():
    """懒加载文本编码模型（线程安全）。"""
    global _TEXT_MODEL
    if _TEXT_MODEL is not None:
        return _TEXT_MODEL
    with _TEXT_MODEL_LOCK:
        if _TEXT_MODEL is not None:
            return _TEXT_MODEL
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers 未安装，请执行: pip install sentence-transformers"
            ) from exc
        if config.VERBOSE:
            print(f"[SOM] 正在加载文本模型: {config.TEXT_MODEL_NAME} ...")
        _TEXT_MODEL = SentenceTransformer(config.TEXT_MODEL_NAME)
        if config.VERBOSE:
            print("[SOM] 文本模型加载完成。")
        return _TEXT_MODEL


def _l2_normalize_rows(matrix):
    """对矩阵的每一行做 L2 归一化。"""
    import numpy as np
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)


def _build_embeddings(element_list: list, run_ids: list, pagerank: dict, degree_cent: dict):
    """
    构建多模态组合嵌入向量。

    各模态及权重（均可在 config.py 中调整）：
      - NLP 文本向量       weight = config.WEIGHT_NLP          (默认 0.35)
      - 共现向量           weight = config.WEIGHT_CO_OCCURRENCE (默认 0.25)
      - 类别 one-hot       weight = config.WEIGHT_CATEGORY      (默认 0.20)
      - 层级 one-hot       weight = config.WEIGHT_LAYER         (默认 0.10)
      - 图结构（PR+度）     weight = config.WEIGHT_GRAPH         (默认 0.10)

    Parameters
    ----------
    element_list : list
        元素对象列表（来自 extract_elements_and_rules 返回的 elements.values()）。
    run_ids : list
        所有 run 的 ID 列表。
    pagerank : dict
        {element_id: float}
    degree_cent : dict
        {element_id: float}

    Returns
    -------
    numpy.ndarray
        shape = (n_elements, combined_dim)，已加权组合的嵌入矩阵。
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy 未安装，请执行: pip install numpy") from exc

    # ── 1. NLP 文本嵌入 ──
    model = _get_text_model()
    texts = [
        f"{e.get('category', '')} {e.get('label', '')} {e.get('desc', '')}".strip()
        for e in element_list
    ]
    nlp_vectors = np.array(model.encode(texts))
    nlp_vectors = _l2_normalize_rows(nlp_vectors)

    # ── 2. 共现向量（元素在哪些 run 中出现） ──
    run_sets = [set(e.get("runs", [])) for e in element_list]
    co_vectors = np.array(
        [[1.0 if run_id in run_set else 0.0 for run_id in run_ids] for run_set in run_sets],
        dtype=float,
    )
    co_vectors = _l2_normalize_rows(co_vectors)

    # ── 3. 层级 one-hot ──
    layers = sorted(
        {str(e.get("layer") or "top_layer") for e in element_list},
        key=lambda x: (config.LAYER_PRIORITY.get(x, 99), x),
    )
    layer_vectors = np.array(
        [[1.0 if e.get("layer") == layer else 0.0 for layer in layers] for e in element_list],
        dtype=float,
    )

    # ── 4. 类别 one-hot ──
    categories = sorted({str(e.get("category") or "unknown") for e in element_list})
    category_vectors = np.array(
        [
            [1.0 if e.get("category") == cat else 0.0 for cat in categories]
            for e in element_list
        ],
        dtype=float,
    )

    # ── 5. 图结构（PageRank + 度中心性） ──
    pr_vec = np.array(
        [float(pagerank.get(e.get("id"), 0.0)) for e in element_list]
    ).reshape(-1, 1)
    deg_vec = np.array(
        [float(degree_cent.get(e.get("id"), 0.0)) for e in element_list]
    ).reshape(-1, 1)
    graph_vectors = np.hstack([pr_vec, deg_vec])
    graph_vectors = graph_vectors / (
        np.linalg.norm(graph_vectors, axis=0, keepdims=True) + 1e-9
    )

    # ── 组合（加权拼接） ──
    combined = np.hstack([
        config.WEIGHT_NLP          * nlp_vectors,
        config.WEIGHT_CO_OCCURRENCE * co_vectors,
        config.WEIGHT_CATEGORY     * category_vectors,
        config.WEIGHT_LAYER        * layer_vectors,
        config.WEIGHT_GRAPH        * graph_vectors,
    ])

    return combined


def _assign_elements_greedy(som, combined_vectors, element_list: list, grid_size: int):
    """
    使用贪心 BMU（最佳匹配单元）算法将元素分配到 SOM 网格节点。

    与匈牙利算法不同，此方法直接将每个元素映射到其最近的网格节点，
    不保证一对一分配——多个元素可能映射到同一节点，部分节点可能为空。

    Parameters
    ----------
    som : MiniSom
        已训练完毕的 MiniSom 实例。
    combined_vectors : numpy.ndarray
        shape = (n_elements, dim)
    element_list : list
        与 combined_vectors 行顺序一致的元素列表。
    grid_size : int
        SOM 网格边长。

    Returns
    -------
    list
        som_nodes 列表，每个节点格式为：
        {"x": int, "y": int, "u_value": float, "elements": list}
        注意：单个节点可能包含多个元素（碰撞）。
    """
    u_matrix = som.distance_map()

    som_nodes = [
        {"x": x, "y": y, "u_value": float(u_matrix[x][y]), "elements": []}
        for x in range(grid_size)
        for y in range(grid_size)
    ]

    for elem_idx, vec in enumerate(combined_vectors):
        wx, wy = som.winner(vec)
        grid_idx = wx * grid_size + wy
        som_nodes[grid_idx]["elements"].append(element_list[elem_idx])

    return som_nodes


def _assign_elements_to_nodes(som, combined_vectors, element_list: list, grid_size: int):
    """
    使用匈牙利算法（线性和分配）将元素最优分配到 SOM 网格节点。

    Parameters
    ----------
    som : MiniSom
        已训练完毕的 MiniSom 实例。
    combined_vectors : numpy.ndarray
        shape = (n_elements, dim)
    element_list : list
        与 combined_vectors 行顺序一致的元素列表。
    grid_size : int
        SOM 网格边长。

    Returns
    -------
    list
        som_nodes 列表，每个节点格式为：
        {"x": int, "y": int, "u_value": float, "elements": list}
    """
    try:
        import numpy as np
        from scipy.spatial.distance import cdist
        from scipy.optimize import linear_sum_assignment
    except ImportError as exc:
        raise RuntimeError(
            "scipy 未安装，请执行: pip install scipy"
        ) from exc

    num_grids = grid_size * grid_size
    u_matrix = som.distance_map()

    som_nodes = [
        {"x": x, "y": y, "u_value": float(u_matrix[x][y]), "elements": []}
        for x in range(grid_size)
        for y in range(grid_size)
    ]

    grid_weights = som.get_weights().reshape(num_grids, -1)
    distances = cdist(combined_vectors, grid_weights, metric="cosine")
    row_ind, col_ind = linear_sum_assignment(distances)

    for elem_idx, grid_idx in zip(row_ind, col_ind):
        som_nodes[int(grid_idx)]["elements"].append(element_list[int(elem_idx)])

    return som_nodes


def _assign_elements_bmu(som, combined_vectors, element_list: list, grid_size: int):
    """
    使用标准最佳匹配单元（BMU / winner）将元素分配到 SOM 网格节点。

    与匈牙利算法不同，此方法允许多个元素映射到同一节点（多对一）。
    可通过 config.ASSIGN_METHOD = "bmu" 启用。

    Returns
    -------
    list
        som_nodes 列表，格式与 _assign_elements_to_nodes 完全相同。
        多元素节点的 elements 列表按出现频次降序排列。
    """
    import numpy as np

    u_matrix = som.distance_map()
    som_nodes = [
        {"x": x, "y": y, "u_value": float(u_matrix[x][y]), "elements": []}
        for x in range(grid_size)
        for y in range(grid_size)
    ]

    for i, vec in enumerate(combined_vectors):
        wx, wy = som.winner(vec)
        grid_idx = wx * grid_size + wy
        som_nodes[grid_idx]["elements"].append(element_list[i])

    # 多元素节点内按频次降序排列，确保最重要的元素在 elements[0]
    for node in som_nodes:
        if len(node["elements"]) > 1:
            node["elements"].sort(key=lambda e: -float(e.get("count", 1) or 1))

    return som_nodes


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def train_som(elements: dict, run_ids: list, pagerank: dict, degree_cent: dict,
              use_hungarian: bool = True) -> list:
    """
    对提取出的设计元素执行 SOM 训练，返回带有元素分配的网格节点列表。

    完整流程：
      1. 构建多模态组合嵌入（_build_embeddings）
      2. 初始化 MiniSom（网格尺寸自动计算）
      3. PCA 或随机权重初始化
      4. 批量训练 N 次迭代
      5. 匈牙利算法最优分配

    Parameters
    ----------
    elements : dict
        来自 element_extractor.extract_elements_and_rules 的 elements 字典。
    run_ids : list
        所有 run 的 ID 列表。
    pagerank : dict
        PageRank 得分字典。
    degree_cent : dict
        度中心性字典。
    use_hungarian : bool
        True（默认）：使用匈牙利算法进行最优一对一分配；
        False：使用贪心 BMU 分配（可能产生碰撞，用于对比演示）。

    Returns
    -------
    list
        som_nodes 列表，格式为：
        [{"x": int, "y": int, "u_value": float, "elements": [...]}, ...]
        空列表表示输入为空。

    Raises
    ------
    RuntimeError
        minisom / scipy / numpy 未安装时抛出。
    """
    try:
        from minisom import MiniSom
    except ImportError as exc:
        raise RuntimeError(
            "minisom 未安装，请执行: pip install minisom"
        ) from exc

    element_list = list(elements.values())
    if not element_list:
        return []

    # ── 1. 构建嵌入 ──
    if config.VERBOSE:
        print(f"[SOM] 构建 {len(element_list)} 个元素的多模态嵌入 ...")
    combined_vectors = _build_embeddings(element_list, run_ids, pagerank, degree_cent)

    # ── 2. 确定网格尺寸 ──
    num_elements = len(element_list)
    grid_size = int(math.ceil(math.sqrt(num_elements))) + config.GRID_SIZE_PADDING

    if config.VERBOSE:
        print(
            f"[SOM] 网格尺寸: {grid_size}×{grid_size}，"
            f"向量维度: {combined_vectors.shape[1]}，"
            f"拓扑: {config.SOM_TOPOLOGY}"
        )

    # ── 3. 初始化 MiniSom ──
    som = MiniSom(
        grid_size,
        grid_size,
        combined_vectors.shape[1],
        sigma=config.SOM_SIGMA,
        learning_rate=config.SOM_LEARNING_RATE,
        topology=config.SOM_TOPOLOGY,
        random_seed=config.SOM_RANDOM_SEED,
    )

    # ── 4. 权重初始化 ──
    if config.SOM_INIT_METHOD == "pca":
        try:
            som.pca_weights_init(combined_vectors)
            if config.VERBOSE:
                print("[SOM] 使用 PCA 初始化权重。")
        except Exception:
            som.random_weights_init(combined_vectors)
            if config.VERBOSE:
                print("[SOM] PCA 初始化失败，回退到随机初始化。")
    else:
        som.random_weights_init(combined_vectors)
        if config.VERBOSE:
            print("[SOM] 使用随机初始化权重。")

    # ── 5. 训练 ──
    if config.VERBOSE:
        print(f"[SOM] 开始训练，迭代次数: {config.SOM_TRAINING_ITERATIONS} ...")
    som.train_batch(combined_vectors, config.SOM_TRAINING_ITERATIONS)
    if config.VERBOSE:
        print("[SOM] 训练完成。")

    # ── 6. 分配元素到节点 ──
    if config.ASSIGN_METHOD == "bmu":
        if config.VERBOSE:
            print("[SOM] 使用 BMU（最佳匹配单元）分配元素。")
        som_nodes = _assign_elements_bmu(som, combined_vectors, element_list, grid_size)
    else:
        if config.VERBOSE:
            print("[SOM] 使用匈牙利算法（线性和分配）分配元素。")
        som_nodes = _assign_elements_to_nodes(som, combined_vectors, element_list, grid_size)

    return som_nodes
