import concurrent.futures
import random
import time

from app3.controller import infographic_logic

DEFAULT_RANDOM_COUNT = 3
MIN_RANDOM_COUNT = 1
MAX_RANDOM_COUNT = 12
MAX_CONCURRENT_WORKERS = 6


def _parse_target_count(raw_count):
    if raw_count is None:
        return DEFAULT_RANDOM_COUNT
    try:
        parsed = int(raw_count)
    except (TypeError, ValueError):
        return None
    if parsed < MIN_RANDOM_COUNT or parsed > MAX_RANDOM_COUNT:
        return None
    return parsed


def _generate_single_worker(sel, chart_json, description, query, analysis_result):
    try:
        # Avoid API bursts when multiple workers start together.
        time.sleep(random.uniform(0, 1.0))

        final_url = infographic_logic.generate_final_composite(
            user_selections=sel,
            chart_json=chart_json,
            description=description,
            query=query,
            analysis_result=analysis_result,
        )
        if final_url:
            return {"image_url": final_url, "selections": sel}
        return None
    except Exception as e:
        print(f"Worker Error: {e}")
        return None


def generate_random_logic(data):
    plan = data.get("plan")
    if not plan or "element_pool" not in plan:
        return None, "Missing or invalid plan data"

    target_count = _parse_target_count(data.get("count"))
    if target_count is None:
        return None, f"Invalid count. Please use an integer between {MIN_RANDOM_COUNT} and {MAX_RANDOM_COUNT}."

    combinations = []
    attempts = 0
    max_attempts = max(50, target_count * 25)

    while len(combinations) < target_count and attempts < max_attempts:
        attempts += 1
        current_sel = {"bottom_layer": {}, "middle_layer": {}, "top_layer": {}}

        for layer_key in ["bottom_layer", "middle_layer", "top_layer"]:
            layer_pool = plan["element_pool"].get(layer_key, [])
            for group in layer_pool:
                group_id = group.get("id")
                options = group.get("options") or []
                if not group_id or not options:
                    continue

                choice = random.choice(options)
                if group_id == "visual_assets":
                    current_sel[layer_key][group_id] = choice
                    continue

                if isinstance(choice, dict):
                    label = choice.get("label") or choice.get("name") or choice
                else:
                    label = choice
                current_sel[layer_key][group_id] = label

        if current_sel not in combinations:
            combinations.append(current_sel)

    if not combinations:
        return None, "Could not build random selections from the current plan."

    results = []
    worker_count = min(len(combinations), MAX_CONCURRENT_WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _generate_single_worker,
                sel,
                data.get("chart_source"),
                data.get("description", "No description"),
                data.get("query", "No query"),
                data.get("analysis_result", "No insights"),
            )
            for sel in combinations
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    if not results:
        return None, f"All {len(combinations)} generations failed. API might be overloaded."

    return results, None


def generate_random_three_logic(data):
    # Backward-compatible wrapper.
    safe_data = dict(data or {})
    safe_data["count"] = DEFAULT_RANDOM_COUNT
    return generate_random_logic(safe_data)
