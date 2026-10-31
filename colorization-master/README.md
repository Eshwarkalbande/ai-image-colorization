# AI Photo Restoration Studio

A Windows-friendly desktop app for colorizing photographs and enlarging them with an optional Real-ESRGAN ncnn-vulkan executable. The app runs the colorization models on the CPU and does not require an NVIDIA GPU or CUDA.

## Features

- Colorize with Richard Zhang's ECCV 2016 or SIGGRAPH 2017 model.
- Compare the original and processed image with a draggable before/after divider.
- Upscale to Original, 2x, 4x, 1080p, 4K, or 8K.
- Use Real-ESRGAN ncnn-vulkan when installed, or a Lanczos-plus-sharpening fallback.
- Process all supported images in a folder, with progress, cancellation, and per-file error logs.
- Save as PNG or JPG with adjustable JPG quality.
- Remember the selected model, output size, and colorization setting in `settings.json`.
- Optionally drag an image onto the input panel when `tkinterdnd2` is available.

## Tech stack

- Python 3.14
- customtkinter and tkinter
- PyTorch (CPU), NumPy, scikit-image, Pillow, Matplotlib, and IPython (imported by the original colorizer utilities)
- Optional Real-ESRGAN ncnn-vulkan for AI super-resolution

## Install

From the directory containing `app.py`, create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, run the interpreter and pip directly with `.\venv\Scripts\python.exe`.

The colorization model weights are downloaded by the original model code the first time each model is selected. An internet connection is needed for that first run. CPU-only operation is supported; CUDA is not used.

## Real-ESRGAN setup (optional)

1. Download a Windows **ncnn-vulkan** release from [Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases).
2. Extract `realesrgan-ncnn-vulkan.exe` and its accompanying `models` folder into:

   ```text
   tools/realesrgan-ncnn-vulkan/
   ```

3. Select an output size other than **Original** in the app.

If the executable is missing, the app explains where to install it and uses Lanczos resizing with sharpening instead. Real-ESRGAN ncnn-vulkan may use Vulkan-capable hardware when available; it does not require CUDA or `basicsr`.

## Usage

Start the desktop app:

```powershell
python app.py
```

1. Click **IMPORT IMAGE** or drop a PNG, JPG/JPEG, BMP, or WEBP image onto the input panel when drag-and-drop is available.
2. Choose a colorizer, output size, and save format. Turn **COLORIZE** off to upscale without colorization.
3. Click **PROCESS**. Drag the divider in the output preview to compare input (left) and output (right).
4. Click **SAVE TO GALLERY** to save the full-resolution result under `Neural_Chroma_Storage/`. **OPEN OUTPUT FOLDER** opens that location.
5. For multiple images, click **BATCH FOLDER**, select a folder, and use **CANCEL** to stop after the current image. Results go to a timestamped `batch_<timestamp>` subfolder. Failed files are skipped and recorded in `batch_errors.log`.

PNG is lossless. JPG quality can be adjusted with the quality slider; the displayed file size is updated for the current output and format.

## Before / After

Add comparison images here:

| Before | After |
| --- | --- |
| Before image placeholder | After image placeholder |

## Limitations

- Colorization is an AI prediction; it may choose plausible colors that differ from the original scene.
- AI upscaling generates plausible detail; it does not recover real detail that was absent from the source image.
- The included colorizers are inference models, not tools for training or photo restoration of every kind.
- Real-ESRGAN requires its Windows ncnn-vulkan executable and model files to be installed separately. Without them, enlargement uses a conventional resize-and-sharpen fallback.

## Credits

### Original work by Richard Zhang et al. (ECCV 2016, SIGGRAPH 2017)

The original colorization models and implementation are by Richard Zhang, Phillip Isola, Alexei A. Efros, and collaborators:

- Richard Zhang, Phillip Isola, and Alexei A. Efros, “Colorful Image Colorization,” ECCV 2016.
- Richard Zhang et al., “Real-Time User-Guided Image Colorization with Learned Deep Priors,” SIGGRAPH 2017.
- Original project: [richzhang/colorization](https://github.com/richzhang/colorization)

### My additions

- Desktop GUI
- Super-resolution pipeline
- Batch mode
- Comparison slider

The optional super-resolution executable is provided by the [Real-ESRGAN project](https://github.com/xinntao/Real-ESRGAN).

## Duplicate “- Copy” files

The following duplicate-named files are not used by the app. Review and delete them manually if you no longer need them; keep the corresponding non-copy files:

- `app - Copy.py`
- `demo_release - Copy.py`
- `LICENSE - Copy`
- `README - Copy.md`
- `requirements - Copy.txt`
- `saved_eccv16 - Copy.png`
- `saved_siggraph17 - Copy.png`
- `colorizers/base_color - Copy.py`
- `colorizers/eccv16 - Copy.py`
- `colorizers/siggraph17 - Copy.py`
- `colorizers/util - Copy.py`
- `colorizers/__init__ - Copy.py`
- `imgs/ansel_adams2 - Copy.jpg`
- `imgs/ansel_adams3 - Copy.jpg`
- `imgs/ILSVRC2012_val_00041580 - Copy.JPEG`
- `imgs/ILSVRC2012_val_00046524 - Copy.JPEG`
- `imgs/ILSVRC2012_val_00046834 - Copy.JPEG`
