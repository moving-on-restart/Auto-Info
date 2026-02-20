import numpy as np
import cv2

def mask_to_polygon(binary_mask):
    """将二进制 mask 转换为多边形点集"""
    try:
        if binary_mask is None: return []
        if hasattr(binary_mask, 'cpu'): binary_mask = binary_mask.cpu().detach().numpy()
        binary_mask = np.array(binary_mask)
        if binary_mask.ndim > 2: binary_mask = np.squeeze(binary_mask)

        mask_uint8 = (binary_mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 30: continue
            epsilon = 0.002 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            points = approx.reshape(-1, 2).tolist()
            if len(points) > 2: polygons.append(points)
        return polygons
    except Exception:
        return []