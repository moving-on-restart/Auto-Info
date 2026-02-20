import json
import math
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

from app3.data_agent_project.core.llm_client import LLMClient


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def _find_values_and_encoding(spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(spec, dict):
        return [], {}

    queue: List[Dict[str, Any]] = [spec]
    while queue:
        node = queue.pop(0)

        data_node = node.get("data")
        values = data_node.get("values") if isinstance(data_node, dict) else None
        if isinstance(values, list) and values and isinstance(values[0], dict):
            encoding = node.get("encoding")
            return values, encoding if isinstance(encoding, dict) else {}

        for key in ("layer", "hconcat", "vconcat", "concat"):
            children = node.get(key)
            if isinstance(children, list):
                queue.extend([item for item in children if isinstance(item, dict)])

        child_spec = node.get("spec")
        if isinstance(child_spec, dict):
            queue.append(child_spec)

    return [], {}


def _extract_numeric_series(chart_source: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    empty = {"value_field": None, "x_field": None, "series": []}
    if not isinstance(chart_source, dict):
        return empty

    rows, encoding = _find_values_and_encoding(chart_source)
    if not rows:
        return empty

    x_field = encoding.get("x", {}).get("field") if isinstance(encoding.get("x"), dict) else None
    value_field = None

    # 优先取显式 quantitative 字段
    for channel in ("y", "x", "size", "theta", "radius"):
        enc = encoding.get(channel)
        if not isinstance(enc, dict):
            continue
        field = enc.get("field")
        enc_type = str(enc.get("type", "")).lower()
        if field and enc_type in ("quantitative", "q"):
            value_field = field
            break

    # 回退：选择数值出现次数最多的字段
    if value_field is None:
        numeric_counts: Dict[str, int] = {}
        for row in rows:
            for key, value in row.items():
                if _safe_float(value) is not None:
                    numeric_counts[key] = numeric_counts.get(key, 0) + 1
        if numeric_counts:
            value_field = max(numeric_counts.items(), key=lambda item: item[1])[0]

    if value_field is None:
        return empty

    series: List[float] = []
    for row in rows:
        value = _safe_float(row.get(value_field))
        if value is not None and math.isfinite(value):
            series.append(value)

    return {"value_field": value_field, "x_field": x_field, "series": series}


def _extract_statistical_features(chart_source: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    extracted = _extract_numeric_series(chart_source)
    series = extracted["series"]

    if len(series) < 2:
        return {
            "value_field": extracted["value_field"],
            "x_field": extracted["x_field"],
            "count": len(series),
            "mean": None,
            "std": None,
            "variance": None,
            "min": None,
            "max": None,
            "trend_direction": "flat",
            "trend_strength": 0.0,
            "volatility_score": 0.0,
            "extreme_ratio": 0.0,
            "scarcity_ratio": 0.0,
            "decay_score": 0.0,
        }

    count = len(series)
    mean = statistics.fmean(series)
    std = statistics.pstdev(series)
    variance = std ** 2
    min_v = min(series)
    max_v = max(series)

    first = series[0]
    last = series[-1]
    trend_rate = (last - first) / (abs(first) + 1e-6)
    trend_strength = _clamp(abs(trend_rate), 0.0, 1.0)
    if trend_rate > 0.08:
        trend_direction = "up"
    elif trend_rate < -0.08:
        trend_direction = "down"
    else:
        trend_direction = "flat"

    volatility_score = _clamp(std / (abs(mean) + 1e-6), 0.0, 1.0)
    extreme_ratio = (
        sum(1 for v in series if abs(v - mean) > 1.5 * std) / count if std > 1e-9 else 0.0
    )
    scarcity_ratio = sum(1 for v in series if abs(v) <= 0.15 * max(abs(min_v), abs(max_v), 1e-6)) / count
    decay_score = _clamp(max(0.0, -trend_rate) * 0.65 + scarcity_ratio * 0.35, 0.0, 1.0)

    return {
        "value_field": extracted["value_field"],
        "x_field": extracted["x_field"],
        "count": count,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "variance": round(variance, 6),
        "min": round(min_v, 6),
        "max": round(max_v, 6),
        "trend_direction": trend_direction,
        "trend_strength": round(trend_strength, 6),
        "volatility_score": round(volatility_score, 6),
        "extreme_ratio": round(extreme_ratio, 6),
        "scarcity_ratio": round(scarcity_ratio, 6),
        "decay_score": round(decay_score, 6),
    }


def _fallback_semantics(description: str, query: str) -> Dict[str, Any]:
    text = f"{description or ''} {query or ''}".lower()

    domain_rules = {
        "heritage": ["museum", "artifact", "dynasty", "故宫", "文物", "陶瓷", "古代", "明代", "清代"],
        "finance": ["finance", "stock", "revenue", "sales", "market", "经济", "营收", "销量", "股价"],
        "technology": ["ai", "model", "chip", "cloud", "software", "科技", "算法", "模型", "芯片"],
        "ecology": ["climate", "carbon", "forest", "water", "生态", "环境", "气候", "污染"],
        "health": ["health", "medical", "hospital", "disease", "医疗", "健康", "疾病"],
    }
    entity_rules = {
        "artifact": ["artifact", "ceramic", "vase", "文物", "瓷器", "器物"],
        "person": ["user", "people", "person", "用户", "人群"],
        "location": ["city", "country", "region", "城市", "地区", "国家"],
        "time": ["year", "month", "daily", "annual", "年代", "时间", "年份"],
        "product": ["product", "item", "category", "产品", "品类"],
    }

    domain_tags = [tag for tag, words in domain_rules.items() if any(word in text for word in words)]
    entity_types = [tag for tag, words in entity_rules.items() if any(word in text for word in words)]

    if re.search(r"(古代|古典|历史|文物|明代|清代|historical|dynasty|antique)", text):
        era = "historical"
    elif re.search(r"(未来|预测|future|forecast)", text):
        era = "future"
    elif re.search(r"(当代|现代|today|current|modern)", text):
        era = "modern"
    else:
        era = "unknown"

    return {
        "domain_tags": domain_tags[:5] or ["general_data"],
        "era_context": era,
        "entity_types": entity_types[:5] or ["main_subject", "background"],
        "source": "heuristic",
    }


def _extract_semantic_features(description: str, query: str) -> Dict[str, Any]:
    fallback = _fallback_semantics(description, query)
    prompt = (
        "你是数据语义提取器。请从 description 与 query 提取语义。\n"
        "只返回 JSON，对象结构：\n"
        "{\"domain_tags\":[...],\"era_context\":\"historical|modern|future|mixed|unknown\",\"entity_types\":[...]}\n\n"
        f"description: {description or ''}\n"
        f"query: {query or ''}"
    )

    messages = [{"role": "user", "content": prompt}]
    parsed = None

    try:
        parsed = _parse_json_object(LLMClient.call_local(messages, temperature=0.2, json_mode=True))
    except Exception:
        parsed = None

    if parsed is None:
        try:
            parsed = _parse_json_object(LLMClient.call_api(messages, temperature=0.2, json_mode=True))
        except Exception:
            parsed = None

    if parsed is None:
        return fallback

    domain_tags = parsed.get("domain_tags")
    era = str(parsed.get("era_context", "")).lower().strip()
    entity_types = parsed.get("entity_types")

    if not isinstance(domain_tags, list) or not domain_tags:
        domain_tags = fallback["domain_tags"]
    else:
        domain_tags = [str(item).strip() for item in domain_tags if str(item).strip()][:5]

    if not isinstance(entity_types, list) or not entity_types:
        entity_types = fallback["entity_types"]
    else:
        entity_types = [str(item).strip() for item in entity_types if str(item).strip()][:5]

    if era not in {"historical", "modern", "future", "mixed", "unknown"}:
        era = fallback["era_context"]

    return {
        "domain_tags": domain_tags or fallback["domain_tags"],
        "era_context": era,
        "entity_types": entity_types or fallback["entity_types"],
        "source": "llm",
    }


def _short_text(text: Optional[str], max_len: int = 28) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."


def _fallback_semantic_anchor(
    description: str,
    query: str,
    analysis_result: Optional[str],
    semantic_features: Dict[str, Any],
) -> Dict[str, Any]:
    domain_to_topic = {
        "heritage": "文博藏品数据",
        "finance": "金融指标数据",
        "technology": "科技发展数据",
        "ecology": "生态环境数据",
        "health": "医疗健康数据",
        "general_data": "综合统计数据",
    }
    entity_to_cn = {
        "artifact": "文物/器物",
        "person": "人群/用户",
        "location": "区域/地点",
        "time": "时间维度",
        "product": "产品/品类",
        "main_subject": "主体对象",
        "background": "背景对象",
    }

    tags = [str(item).lower() for item in semantic_features.get("domain_tags", [])]
    topic_cn = ""
    for tag in tags:
        if tag in domain_to_topic:
            topic_cn = domain_to_topic[tag]
            break
    if not topic_cn:
        topic_cn = _short_text(query, 18) or _short_text(description, 18) or "数据主题"

    query_l = (query or "").lower()
    if re.search(r"(对比|比较|vs|compare)", query_l):
        relation_cn = "类别差异对比"
    elif re.search(r"(趋势|变化|走势|trend|over time)", query_l):
        relation_cn = "时间趋势变化"
    elif re.search(r"(占比|比例|结构|ratio|proportion|share)", query_l):
        relation_cn = "结构占比关系"
    elif re.search(r"(排名|排序|top|rank)", query_l):
        relation_cn = "排序层级关系"
    else:
        relation_cn = "核心指标关系"

    entity_types = semantic_features.get("entity_types", []) or []
    entities_cn = []
    for entity in entity_types:
        ent = str(entity).strip()
        if not ent:
            continue
        entities_cn.append(entity_to_cn.get(ent, ent))
    if not entities_cn:
        entities_cn = ["主体对象", "背景对象"]

    focus = _short_text(query, 20) or _short_text(analysis_result, 20) or "关键关系表达"
    return {
        "topic_cn": topic_cn,
        "relation_cn": relation_cn,
        "key_entities_cn": entities_cn[:3],
        "narrative_focus_cn": focus,
        "source": "heuristic",
    }


def _extract_semantic_anchor(
    description: str,
    query: str,
    analysis_result: Optional[str],
    semantic_features: Dict[str, Any],
) -> Dict[str, Any]:
    fallback = _fallback_semantic_anchor(description, query, analysis_result, semantic_features)
    prompt = (
        "你是数据可视化语义锚点提取器。基于 description/query/analysis_result 提炼与图表直接相关的语义锚点。"
        "只返回 JSON，对象结构："
        "{\"topic_cn\":\"\",\"relation_cn\":\"\",\"key_entities_cn\":[\"\",\"\"],\"narrative_focus_cn\":\"\"}。"
        "topic_cn 要体现数据主题；relation_cn 要体现分析关系（如对比/趋势/占比）；"
        "key_entities_cn 最多3个中文短语。\n\n"
        f"description: {description or ''}\n"
        f"query: {query or ''}\n"
        f"analysis_result: {(analysis_result or '')[:400]}\n"
        f"semantic_features: {json.dumps(semantic_features, ensure_ascii=False)}"
    )
    messages = [{"role": "user", "content": prompt}]

    parsed = None
    try:
        parsed = _parse_json_object(LLMClient.call_local(messages, temperature=0.2, json_mode=True))
    except Exception:
        parsed = None

    if parsed is None:
        try:
            parsed = _parse_json_object(LLMClient.call_api(messages, temperature=0.2, json_mode=True))
        except Exception:
            parsed = None

    if not isinstance(parsed, dict):
        return fallback

    topic_cn = str(parsed.get("topic_cn", "")).strip() or fallback["topic_cn"]
    relation_cn = str(parsed.get("relation_cn", "")).strip() or fallback["relation_cn"]
    narrative_focus_cn = str(parsed.get("narrative_focus_cn", "")).strip() or fallback["narrative_focus_cn"]
    entities = parsed.get("key_entities_cn")
    if not isinstance(entities, list) or not entities:
        entities = fallback["key_entities_cn"]
    else:
        entities = [str(item).strip() for item in entities if str(item).strip()][:3]
        if not entities:
            entities = fallback["key_entities_cn"]

    return {
        "topic_cn": _short_text(topic_cn, 20),
        "relation_cn": _short_text(relation_cn, 20),
        "key_entities_cn": entities,
        "narrative_focus_cn": _short_text(narrative_focus_cn, 24),
        "source": "llm",
    }


def _map_emotion_vector(stats: Dict[str, Any], semantics: Dict[str, Any]) -> Dict[str, Any]:
    # Russell 模型：Valence/Arousal
    valence = 0.5
    arousal = 0.45
    temperature_score = 0.0  # warm(+1) / cool(-1)

    trend = stats.get("trend_direction")
    trend_strength = float(stats.get("trend_strength") or 0.0)
    volatility = float(stats.get("volatility_score") or 0.0)
    extreme_ratio = float(stats.get("extreme_ratio") or 0.0)
    decay_score = float(stats.get("decay_score") or 0.0)

    if trend == "up":
        valence += 0.24 * (0.4 + trend_strength)
        arousal += 0.10
        temperature_score += 0.20
    elif trend == "down":
        valence -= 0.24 * (0.4 + trend_strength)
        arousal += 0.05
        temperature_score -= 0.20

    arousal += 0.35 * volatility + 0.22 * extreme_ratio
    valence -= 0.10 * max(0.0, volatility - 0.5)

    valence -= 0.25 * decay_score
    temperature_score -= 0.14 * decay_score

    era = semantics.get("era_context", "unknown")
    if era == "historical":
        arousal -= 0.16
        temperature_score += 0.10
    elif era == "future":
        arousal += 0.10
        temperature_score -= 0.08

    for tag in semantics.get("domain_tags", []):
        tag_l = str(tag).lower()
        if tag_l == "heritage":
            arousal -= 0.08
            temperature_score += 0.08
        elif tag_l == "technology":
            arousal += 0.10
            temperature_score -= 0.08
        elif tag_l == "finance":
            arousal += 0.06
        elif tag_l == "ecology":
            arousal -= 0.04
            temperature_score -= 0.06

    valence = _clamp(valence, 0.0, 1.0)
    arousal = _clamp(arousal, 0.0, 1.0)
    temperature_score = _clamp(temperature_score, -1.0, 1.0)

    return {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "temperature_score": round(temperature_score, 4),
    }


def _synthesize_color_attributes(emotion: Dict[str, Any], stats: Dict[str, Any], semantics: Dict[str, Any]) -> Dict[str, Any]:
    valence = float(emotion["valence"])
    arousal = float(emotion["arousal"])
    temp_score = float(emotion["temperature_score"])
    extreme_ratio = float(stats.get("extreme_ratio", 0.0))
    era = semantics.get("era_context", "unknown")

    # M2: C_attr = {Hue_range, Saturation_level, Lightness_bias, Contrast_ratio, Temperature}
    hue_center = int(round(_clamp(150 - 110 * temp_score, 0, 360)))
    hue_span = int(round(_clamp(35 + 85 * arousal, 28, 130)))
    hue_range = [(hue_center - hue_span // 2) % 360, (hue_center + hue_span // 2) % 360]

    saturation = int(round(_clamp(22 + 58 * arousal + 12 * (valence - 0.5), 12, 92)))
    lightness = int(round(_clamp(38 + 32 * valence + 8 * (0.5 - arousal), 22, 86)))
    if era == "historical":
        saturation = int(round(_clamp(saturation - 10, 10, 92)))
        lightness = int(round(_clamp(lightness + 6, 22, 88)))

    contrast = round(_clamp(0.24 + 0.54 * arousal + 0.20 * extreme_ratio, 0.2, 0.95), 4)

    if temp_score > 0.15:
        temperature = "warm"
    elif temp_score < -0.15:
        temperature = "cool"
    else:
        temperature = "neutral"

    return {
        "Hue_range": hue_range,
        "Saturation_level": saturation,
        "Lightness_bias": lightness,
        "Contrast_ratio": contrast,
        "Temperature": temperature,
    }


def _build_scene_prompt(
    semantics: Dict[str, Any],
    semantic_anchor: Dict[str, Any],
    emotion: Dict[str, Any],
    c_attr: Dict[str, Any],
    description: str,
    query: str,
) -> str:
    domain_tags = [str(item).lower() for item in semantics.get("domain_tags", [])]
    era = semantics.get("era_context", "unknown")
    valence = emotion.get("valence", 0.5)
    arousal = emotion.get("arousal", 0.5)

    if "heritage" in domain_tags:
        scene = "文博展陈空间，器物与肌理并置"
    elif "finance" in domain_tags:
        scene = "数据编辑室，几何结构与信息层叠"
    elif "technology" in domain_tags:
        scene = "未来分析实验室，材料反射与秩序布局"
    elif "ecology" in domain_tags:
        scene = "自然观测场景，地形纹理与空气透视"
    else:
        scene = "抽象信息叙事场景，层次清晰"

    if era == "historical":
        era_phrase = "时代气质偏古雅"
    elif era == "future":
        era_phrase = "时代气质偏前瞻"
    elif era == "modern":
        era_phrase = "时代气质偏现代"
    else:
        era_phrase = "时代气质中性"

    if arousal >= 0.66:
        composition = "构图动态、节奏紧凑、明暗边界清晰"
    elif arousal <= 0.4:
        composition = "构图稳定、渐变柔和、过渡细腻"
    else:
        composition = "构图均衡、层次明确、光比适中"

    if valence >= 0.66:
        mood = "整体情绪积极且有活力"
    elif valence <= 0.4:
        mood = "整体情绪克制且冷静"
    else:
        mood = "整体情绪理性平衡"

    h0, h1 = c_attr["Hue_range"]
    s = c_attr["Saturation_level"]
    l = c_attr["Lightness_bias"]
    cr = c_attr["Contrast_ratio"]
    t = c_attr["Temperature"]

    topic = semantic_anchor.get("topic_cn", "数据主题")
    relation = semantic_anchor.get("relation_cn", "关键关系")
    entities = semantic_anchor.get("key_entities_cn", [])
    entities_text = "、".join([str(item) for item in entities[:3]]) if entities else "主体对象、背景对象"
    focus = semantic_anchor.get("narrative_focus_cn", "核心信息表达")
    query_hint = _short_text(query, 36)
    desc_hint = _short_text(description, 32)

    return (
        f"语义主题：{topic}；关注关系：{relation}；关键实体：{entities_text}；叙事焦点：{focus}。"
        f"分析问题：{query_hint or '未提供'}；数据描述：{desc_hint or '未提供'}。"
        f"请生成可用于提取调色板的参考场景图：{scene}。{era_phrase}，{composition}，{mood}。"
        "通过光照、材质、空间深度和对比关系编码色彩倾向，不直接写颜色名称。"
        f"目标色彩属性：Hue范围{h0}-{h1}，Saturation约{s}，Lightness约{l}，Contrast约{cr}，Temperature={t}。"
        "画面无文字、无水印、主体明确。"
    )


def _build_palette_image_prompt(
    scene_prompt: str,
    c_attr: Dict[str, Any],
    emotion: Dict[str, Any],
    semantic_anchor: Dict[str, Any],
) -> str:
    h0, h1 = c_attr["Hue_range"]
    s = c_attr["Saturation_level"]
    l = c_attr["Lightness_bias"]
    cr = c_attr["Contrast_ratio"]
    t = c_attr["Temperature"]
    v = emotion["valence"]
    a = emotion["arousal"]

    topic = semantic_anchor.get("topic_cn", "数据主题")
    relation = semantic_anchor.get("relation_cn", "关键关系")
    entities = semantic_anchor.get("key_entities_cn", [])
    entities_text = "、".join([str(item) for item in entities[:3]]) if entities else "主体对象"

    return (
        "生成信息图调色板图：上半部分为抽象场景，下半部分为5色等宽色条。"
        "色条需和谐且区分明确，不写具体颜色名。"
        f"语义锚点：主题={topic}，关系={relation}，实体={entities_text}。"
        f"约束：Hue={h0}-{h1}，Saturation={s}，Lightness={l}，Contrast={cr}，Temperature={t}，Valence={v}，Arousal={a}。"
        f"场景语义：{scene_prompt}"
    )


def _build_region_prompt(semantics: Dict[str, Any]) -> str:
    entities = [str(item).strip() for item in semantics.get("entity_types", []) if str(item).strip()]
    if not entities:
        return "主体, 背景, 高光区域"
    return ", ".join(entities[:3])


def generate_palette_prompt_package(
    description: str,
    query: str,
    analysis_result: Optional[str] = None,
    chart_source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # M1: 统计特征 + 语义特征 + Russell 情感向量
    statistical_features = _extract_statistical_features(chart_source)
    semantic_features = _extract_semantic_features(description or "", query or "")
    semantic_anchor = _extract_semantic_anchor(
        description or "",
        query or "",
        analysis_result,
        semantic_features,
    )
    emotion_vector = _map_emotion_vector(statistical_features, semantic_features)

    # M2: 情感向量 -> HSL色彩属性
    color_attributes = _synthesize_color_attributes(emotion_vector, statistical_features, semantic_features)

    # M3: 场景提示词生成（编码色彩属性）
    scene_prompt = _build_scene_prompt(
        semantic_features,
        semantic_anchor,
        emotion_vector,
        color_attributes,
        description or "",
        query or "",
    )

    # 保持与现有接口兼容：stage4 提供可直接用于前端的引用字段
    palette_image_prompt = _build_palette_image_prompt(
        scene_prompt,
        color_attributes,
        emotion_vector,
        semantic_anchor,
    )
    region_prompt = _build_region_prompt(semantic_features)

    insight_hint = None
    if isinstance(analysis_result, str) and analysis_result.strip():
        insight_hint = analysis_result.strip().splitlines()[0][:160]

    return {
        "stage1": {
            "statistical_features": statistical_features,
            "semantic_features": semantic_features,
            "semantic_anchor": semantic_anchor,
            "emotion_vector": emotion_vector,
        },
        "stage2": {
            "color_attributes": color_attributes,
        },
        "stage3": {
            "scene_prompt": scene_prompt,
        },
        "stage4": {
            "reference_prompt": scene_prompt,
            "palette_image_prompt": palette_image_prompt,
            "region_prompt": region_prompt,
        },
        "insight_hint": insight_hint,
    }
