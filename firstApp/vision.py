from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

from django.conf import settings


VIOLATION_LABELS = {
    "looking_left": "looking_left",
    "turn_left": "looking_left",
    "left": "looking_left",
    "looking_right": "looking_right",
    "turn_right": "looking_right",
    "right": "looking_right",
    "looking_down": "looking_down",
    "head_down": "looking_down",
    "down": "looking_down",
}
NEUTRAL_LABELS = {"normal", "forward", "looking_forward", "center", "attentive"}


def proctoring_available():
    return Path(settings.PROCTORING_MODEL_PATH).is_file() and find_spec("ultralytics") is not None


@lru_cache(maxsize=1)
def _load_model(model_path):
    from ultralytics import YOLO

    return YOLO(model_path)


def _class_name(names, class_id):
    if isinstance(names, dict):
        return str(names.get(class_id, names.get(str(class_id), "")))
    if isinstance(names, (list, tuple)) and class_id < len(names):
        return str(names[class_id])
    return ""


def classify_frame(frame_file):
    model_path = Path(settings.PROCTORING_MODEL_PATH)
    if not model_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy YOLO checkpoint: {model_path}")
    if find_spec("ultralytics") is None:
        raise ModuleNotFoundError("Chưa cài package ultralytics trong môi trường Django.")

    from PIL import Image

    image = Image.open(frame_file).convert("RGB")
    result = _load_model(str(model_path))(image, verbose=False, conf=settings.PROCTORING_CONFIDENCE)[0]
    names = result.names

    if result.probs is not None:
        class_id = int(result.probs.top1)
        confidence = float(result.probs.top1conf.item())
        label = _class_name(names, class_id)
    elif result.boxes is not None and len(result.boxes) > 0:
        confidences = result.boxes.conf.tolist()
        best_index = max(range(len(confidences)), key=confidences.__getitem__)
        class_id = int(result.boxes.cls[best_index].item())
        confidence = float(confidences[best_index])
        label = _class_name(names, class_id)
    else:
        return None, 0.0

    normalized_label = label.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized_label in VIOLATION_LABELS:
        return VIOLATION_LABELS[normalized_label], confidence
    if normalized_label in NEUTRAL_LABELS:
        return "normal", confidence
    return None, confidence