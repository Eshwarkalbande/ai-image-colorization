from threading import RLock

import numpy as np
from PIL import Image


class ColorizeEngine:
    def __init__(self):
        self._models = {}
        self._lock = RLock()

    def colorize(self, image, model_name="siggraph17"):
        model_key = model_name.lower()
        if model_key not in ("eccv16", "siggraph17"):
            raise ValueError(f"Unsupported colorization model: {model_name}")

        import torch
        from colorizers import eccv16, postprocess_tens, preprocess_img, siggraph17

        with self._lock:
            model = self._models.get(model_key)
            if model is None:
                model_factory = eccv16 if model_key == "eccv16" else siggraph17
                model = model_factory(pretrained=True).eval()
                self._models[model_key] = model

        image_rgb = image.convert("RGB")
        tensor_l_orig, tensor_l_resized = preprocess_img(np.asarray(image_rgb), HW=(256, 256))
        with torch.inference_mode():
            output_ab = model(tensor_l_resized)

        output_rgb = postprocess_tens(tensor_l_orig, output_ab)
        output_pixels = np.clip(output_rgb * 255.0, 0, 255).astype(np.uint8)
        return Image.fromarray(output_pixels, mode="RGB")
