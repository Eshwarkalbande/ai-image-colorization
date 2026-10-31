import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "colorization-master"))

import numpy as np
import torch
import streamlit as st
from PIL import Image
from colorizers import eccv16, siggraph17, preprocess_img, postprocess_tens

st.set_page_config(page_title="AI Image Colorization", page_icon="🎨")
st.title("🎨 AI Image Colorization")
st.write("Upload a black & white photo and get a colorized version.")

@st.cache_resource(max_entries=1)
def load_model(name):
    m = siggraph17(pretrained=True) if name == "SIGGRAPH17" else eccv16(pretrained=True)
    return m.eval()

name = st.radio("Model", ["SIGGRAPH17", "ECCV16"], horizontal=True)
file = st.file_uploader("Upload image", type=["jpg", "jpeg", "png"])

if file:
    img = Image.open(file).convert("RGB")
    img.thumbnail((800, 800))
    arr = np.array(img)
    with st.spinner("Colorizing..."):
        model = load_model(name)
        tens_l_orig, tens_l_rs = preprocess_img(arr, HW=(256, 256))
        with torch.no_grad():
            out_ab = model(tens_l_rs).cpu()
        out = postprocess_tens(tens_l_orig, out_ab)
    c1, c2 = st.columns(2)
    c1.image(img, caption="Original", use_container_width=True)
    c2.image(out, caption="Colorized", use_container_width=True)
