from __future__ import annotations

import os

import streamlit as st


def get_app_key() -> str:
    try:
        secret_value = st.secrets.get("APP_KEY", "") or st.secrets.get("app_key", "")
    except Exception:  # noqa: BLE001
        secret_value = ""
    return str(secret_value or os.getenv("APP_KEY", "") or os.getenv("app_key", "")).strip()


def get_access_code() -> str:
    try:
        secret_value = st.secrets.get("ACCESS_CODE", "") or st.secrets.get("access_code", "")
    except Exception:  # noqa: BLE001
        secret_value = ""
    return str(secret_value or os.getenv("ACCESS_CODE", "") or os.getenv("access_code", "")).strip()
