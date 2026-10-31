import os
import subprocess
import tempfile

from PIL import Image, ImageFilter


OUTPUT_PRESETS = ("Original", "2x", "4x", "1080p", "4K", "8K")
REAL_ESRGAN_SCALE = {
    "2x": 2,
    "4x": 4,
    "1080p": 4,
    "4K": 4,
    "8K": 4,
}
TARGET_DIMENSIONS = {
    "1080p": (1920, 1080),
    "4K": (3840, 2160),
    "8K": (7680, 4320),
}


class Upscaler:
    def __init__(self, executable_path):
        self.executable_path = executable_path

    @property
    def available(self):
        return os.path.isfile(self.executable_path)

    def upscale(self, image, preset):
        if preset not in OUTPUT_PRESETS:
            raise ValueError(f"Unsupported output size: {preset}")
        if preset == "Original":
            return image.convert("RGB").copy()

        image = image.convert("RGB")
        target_size = self._target_size(image.size, preset)
        if self.available:
            upscaled = self._run_realesrgan(image, preset)
            return upscaled.resize(target_size, Image.Resampling.LANCZOS)

        return self._resize_fallback(image, target_size)

    def _target_size(self, source_size, preset):
        if preset == "2x":
            return source_size[0] * 2, source_size[1] * 2
        if preset == "4x":
            return source_size[0] * 4, source_size[1] * 4

        target_width, target_height = TARGET_DIMENSIONS[preset]
        ratio = min(target_width / source_size[0], target_height / source_size[1])
        return max(1, round(source_size[0] * ratio)), max(1, round(source_size[1] * ratio))

    def _run_realesrgan(self, image, preset):
        with tempfile.TemporaryDirectory(prefix="neural_chroma_") as work_dir:
            input_path = os.path.join(work_dir, "input.png")
            output_path = os.path.join(work_dir, "output.png")
            image.save(input_path, format="PNG")
            completed = subprocess.run(
                [
                    self.executable_path,
                    "-i", input_path,
                    "-o", output_path,
                    "-n", "realesrgan-x4plus",
                    "-s", str(REAL_ESRGAN_SCALE[preset]),
                    "-f", "png",
                ],
                cwd=os.path.dirname(self.executable_path),
                capture_output=True,
                text=True,
                check=False,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            if completed.returncode != 0 or not os.path.isfile(output_path):
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(
                    "Real-ESRGAN failed. Confirm its model files are beside the executable."
                    + (f"\n\n{detail}" if detail else "")
                )
            with Image.open(output_path) as result:
                return result.convert("RGB")

    @staticmethod
    def _resize_fallback(image, target_size):
        resized = image.resize(target_size, Image.Resampling.LANCZOS)
        short_edge = min(target_size)
        radius = max(1, round(short_edge / 300))
        return resized.filter(ImageFilter.UnsharpMask(radius=radius, percent=120, threshold=3))
