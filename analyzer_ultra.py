import streamlit as st
import pandas as pd
import yfinance as yf
from openai import OpenAI
import numpy as np
from streamlit_autorefresh import st_autorefresh
import ta

# ============================================================
# ULTRA ENGINE v12 — FULL AI PIPELINE + CHAT
# ============================================================

st.set_page_config(layout="wide", page_title="TERMINAL v12", page_icon="⚔️")

# --- STYL / NEONY ---
st.markdown("""
<style>
.stApp {
    background-color: #030305;
    color: #e0e0e0;
}
.neon-button {
    background: linear-gradient(90deg, #ff00cc, #3333ff);
    padding: 12px 24px;
    border-radius: 8px;
    color: white !important;
    font-weight: bold;
    font-size: 18px;
    border: 2px solid #ff00cc;
    box-shadow: 0 0 15px #ff00cc;
    transition: 0.2s;
}
.neon-button:hover {
    box-shadow: 0 0 25px #ff00cc, 0 0 25px #3333ff;
    transform: scale(1.03);
}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: REFRESH + MODEL + LISTY ---
st.sidebar.header("⚙️ USTAWIENIA SYSTEMU")
refresh_val = st.sidebar.slider("Auto-odświeżanie (minuty)", 1, 15, 10)
st_autorefresh(interval=refresh_val * 60 * 1000, key="datarefresh")

st.sidebar.header("🤖 MODEL AI")
model_choice = st.sidebar.selectbox(
    "Model",
    ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    index=0
)

OPENAI_KEY =
