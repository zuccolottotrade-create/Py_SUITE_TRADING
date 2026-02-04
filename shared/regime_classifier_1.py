from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Literal


import json
import os
print("[DEBUG] regime_classifier_1 loaded from:", __file__)


RegimeFilterL1 = Literal["OFF", "L1"]

# ==========================================================
# Contract / Requirements for this regime classifier
# ==========================================================

REQUIRED_BASE_COLS = [
    "symbol", "isin", "date", "time", "open", "high", "low", "close", "volume", "datetime"
]

REQUIRED_KPI_COLS = [
    "KPI_ATR_14",
    "KPI_ATR_PCT_14",
    "KPI_ADX_14",
    "KPI_EMA_21",
    "KPI_EMA_50",
]

def validate_input_L1(df):
    validate_input_L1(df)
    missing = [c for c in REQUIRED_KPI_COLS_L1 if c not in df.columns]
    if missing:
        raise ValueError(
            "[regime_classifier_1:L1] KPI mancanti: " + ", ".join(missing)
        )

def validate_input(df):
    """
    Validate that df contains the minimum columns required by this classifier.
    Raise ValueError with a clear message if requirements are not met.
    """
    missing_base = [c for c in REQUIRED_BASE_COLS if c not in df.columns]
    missing_kpi = [c for c in REQUIRED_KPI_COLS if c not in df.columns]

    if missing_base or missing_kpi:
        parts = []
        if missing_base:
            parts.append("BASE=" + ", ".join(missing_base))
        if missing_kpi:
            parts.append("KPI=" + ", ".join(missing_kpi))
        raise ValueError("[regime_classifier_1] Missing required columns: " + " | ".join(parts))






# =============================================================================
# REGIME_L1 baseline (FROZEN) - v1.0
# =============================================================================
REGIME_L1_VERSION = "1.0"

# Baseline congelata (non toccare senza bump di versione)
REGIME_L1_BASELINE = dict(
    adx_trend_enter=20.0,
    adx_trend_exit=18.0,
    adx_range_enter=15.0,
    adx_range_exit=17.0,
    atr_volatile_enter=2.0,
    atr_volatile_exit=1.7,
    confirm_bars_trend=2,
    confirm_bars_range=2,
    confirm_bars_volatile=2,
    lateral_label="LATERAL",
)

# Profili (preset) per fine tuning: aggiungi qui nuovi preset
# Nota: NON modificare REGIME_L1_BASELINE; crea un profilo nuovo.
REGIME_L1_PROFILES = {
    "BASELINE": REGIME_L1_BASELINE,
    # esempi (commentati): duplicali e cambia solo ciò che vuoi
    # "TUNE_SOFT_RANGE": {**REGIME_L1_BASELINE, "adx_range_enter": 16.0, "adx_range_exit": 18.0},
    # "TUNE_MORE_VOL":   {**REGIME_L1_BASELINE, "atr_volatile_enter": 1.5, "atr_volatile_exit": 1.3},
}

def resolve_regime_l1_params(
    profile: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """
    Resolve parametri L1:
    - profile: nome preset (default: ENV REGIME_L1_PROFILE, altrimenti BASELINE)
    - overrides: dict runtime (sovrascrive il profilo)
    - ENV overrides: REGIME_L1_OVERRIDES_JSON (JSON string) opzionale
    """
    p = (profile or os.getenv("REGIME_L1_PROFILE") or "BASELINE").strip().upper()
    if p not in REGIME_L1_PROFILES:
        raise ValueError(f"[REGIME_L1] Unknown profile: {p}. Available={list(REGIME_L1_PROFILES.keys())}")

    params = dict(REGIME_L1_PROFILES[p])

    # 1) override da ENV JSON (se presente)
    env_json = os.getenv("REGIME_L1_OVERRIDES_JSON", "").strip()
    if env_json:
        try:
            env_over = json.loads(env_json)
            if not isinstance(env_over, dict):
                raise ValueError("REGIME_L1_OVERRIDES_JSON must be a JSON object")
            params.update(env_over)
        except Exception as e:
            raise ValueError(f"[REGIME_L1] Bad REGIME_L1_OVERRIDES_JSON: {e}")

    # 2) override da argomento python (massima priorità)
    if overrides:
        params.update(overrides)

    return params

def update_regime_state_Livello1(
    df: pd.DataFrame,
    *,
    # --- soglie (enter/exit = hysteresis) ---
    adx_trend_enter: float = 20.0,
    adx_trend_exit: float = 18.0,
    adx_range_enter: float = 15.0,
    adx_range_exit: float = 17.0,
    atr_volatile_enter: float = 2.0,
    atr_volatile_exit: float = 1.7,
    # --- debounce (barre consecutive richieste) ---
    confirm_bars_trend: int = 2,
    confirm_bars_volatile: int = 2,
    confirm_bars_range: int = 2,
    # --- output columns ---
    col_raw: str = "REGIME_L1_RAW",
    col_out: str = "REGIME_L1",
    col_code: str = "REGIME_L1_CODE",
    col_switch: str = "REGIME_L1_SWITCH",
    col_reason: str = "REGIME_L1_REASON",
) -> pd.DataFrame:
    """
    REGIME – Livello 1 (contesto primario) - versione robusta

    Regimi granulari:
      - TREND_UP
      - TREND_DOWN
      - VOLATILE
      - LATERAL = mercato non direzionale, ADX medio, nessun trend strutturato,
          volatilità normale (zona di transizione / congestione ampia)


    Output:
      - REGIME_L1_RAW    : classificazione istantanea (debug/QC)
      - REGIME_L1        : stato stabilizzato (debounce + hysteresis)
      - REGIME_L1_CODE   : codice numerico stabile
      - REGIME_L1_SWITCH : 1 quando cambia stato (su barra), altrimenti 0
      - REGIME_L1_REASON : driver dominante dello stato RAW (TREND_UP/TREND_DOWN/VOLATILE/RANGE)

    Priorità RAW (come tua versione):
      1) Trend
      2) Volatile
      3) Lateral
    """

    required_cols = [
        "close",
        "KPI_EMA_21",
        "KPI_EMA_50",
        "KPI_EMA_200",
        "KPI_ADX_14",
        "KPI_ATR_PCT_14",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"[REGIME_L1] Colonne mancanti: {missing}")

    # --- segnali base -----------------------------------------------------
    ema_up = (df["KPI_EMA_21"] > df["KPI_EMA_50"]) & (df["KPI_EMA_50"] > df["KPI_EMA_200"])
    ema_dn = (df["KPI_EMA_21"] < df["KPI_EMA_50"]) & (df["KPI_EMA_50"] < df["KPI_EMA_200"])

    adx = df["KPI_ADX_14"]
    atrp = df["KPI_ATR_PCT_14"]

    # condizioni di ingresso/uscita (hysteresis)
    trend_up_enter = ema_up & (adx >= adx_trend_enter)
    trend_dn_enter = ema_dn & (adx >= adx_trend_enter)
    trend_ok_exit = (adx >= adx_trend_exit)  # “trend ancora valido” lato ADX

    volatile_enter = atrp >= atr_volatile_enter
    volatile_ok_exit = atrp >= atr_volatile_exit

    range_enter = adx < adx_range_enter
    range_ok_exit = adx < adx_range_exit

    # --- RAW: classificazione istantanea (priorità) -----------------------
    # Trend domina (se presente). Nota: up e down sono mutuamente esclusivi se EMA ordinate.
    raw = np.select(
        [trend_up_enter, trend_dn_enter, volatile_enter, range_enter],
        ["TREND_UP", "TREND_DOWN", "VOLATILE", "RANGE"],
        default="LATERAL",
    )
    df[col_raw] = raw
    df[col_reason] = df[col_raw]  # per ora reason = raw driver

    # --- Debounce helper: N barre consecutive True ------------------------
    def _confirm(sig: pd.Series, n: int) -> pd.Series:
        if n <= 1:
            return sig.fillna(False)
        return sig.fillna(False).rolling(n, min_periods=n).sum().ge(n)

    trend_up_c = _confirm(trend_up_enter, confirm_bars_trend)
    trend_dn_c = _confirm(trend_dn_enter, confirm_bars_trend)
    volatile_c = _confirm(volatile_enter, confirm_bars_volatile)
    range_c = _confirm(range_enter, confirm_bars_range)

    # --- State machine (sequenziale, deterministica) ----------------------
    # Stato iniziale: RAW della prima riga
    states = []
    prev = None

    for i in range(len(df)):
        if prev is None:
            prev = df.iloc[i][col_raw]
            states.append(prev)
            continue

        # Stato corrente e segnali “confermati”
        su = bool(trend_up_c.iat[i])
        sd = bool(trend_dn_c.iat[i])
        sv = bool(volatile_c.iat[i])
        sr = bool(range_c.iat[i])

        # Mantieni stato se ancora “valido” (hysteresis exit)
        if prev in ("TREND_UP", "TREND_DOWN"):
            still_trend = bool(trend_ok_exit.iat[i]) and (bool(ema_up.iat[i]) if prev == "TREND_UP" else bool(ema_dn.iat[i]))
            if still_trend:
                states.append(prev)
                continue

        if prev == "VOLATILE":
            if bool(volatile_ok_exit.iat[i]):
                states.append(prev)
                continue

        if prev == "RANGE":
            if bool(range_ok_exit.iat[i]):
                states.append(prev)
                continue

        # Se non lo mantieni, prova transizioni in ordine di priorità
        if su:
            prev = "TREND_UP"
        elif sd:
            prev = "TREND_DOWN"
        elif sv:
            prev = "VOLATILE"
        elif sr:
            prev = "RANGE"
        else:
            # fallback: RAW (ma senza jitter eccessivo grazie ai confirm sopra)
            prev = df.iloc[i][col_raw]

        states.append(prev)

    df[col_out] = pd.Series(states, index=df.index)

    # --- SWITCH flag ------------------------------------------------------
    df[col_switch] = (df[col_out] != df[col_out].shift(1)).fillna(False).astype(int)

    # --- CODE mapping (stabile) ------------------------------------------
    code_map = {
        "LATERAL": 0,
        "RANGE": 1,
        "VOLATILE": 2,
        "TREND_UP": 3,
        "TREND_DOWN": 4,
    }
    df[col_code] = df[col_out].map(code_map).fillna(0).astype(int)

    return df


def apply_regime_L1(
    df: pd.DataFrame,
    regime_filter: RegimeFilterL1 | None = None,
    *,
    cfg: dict | None = None,
    profile: str | None = None,
    overrides: dict | None = None,
) -> pd.DataFrame:
    """
    Entry-point Livello 1 per PyKPI / Strategy Creator.

    Compatibilità:
    - supporta chiamata legacy/bridge: apply_regime_L1(df, cfg=cfg)
    - supporta chiamata esplicita: apply_regime_L1(df, regime_filter="L1", profile=..., overrides=...)
    """
    # --- Backward/bridge compatibility: cfg può contenere regime_filter/profile/overrides
    if cfg:
        # accetta varie chiavi possibili senza essere fragile
        if regime_filter is None:
            regime_filter = (
                cfg.get("regime_filter")
                or cfg.get("regime_filter_L1")
                or cfg.get("filter")
                or cfg.get("mode")
            )
        if profile is None:
            profile = cfg.get("profile")
        if overrides is None:
            overrides = cfg.get("overrides")

    rf = (regime_filter or "OFF")
    rf = rf.strip().upper()

    if rf == "OFF":
        return df

    if rf == "L1":
        params = resolve_regime_l1_params(profile=profile, overrides=overrides)

        # update_regime_state_Livello1 NON accetta lateral_label: rimuovilo se presente
        params.pop("lateral_label", None)

        return update_regime_state_Livello1(df, **params)

    raise ValueError(f"Unknown regime_filter_L1: {regime_filter}")


def apply_regime(df, cfg=None):
    """
    Bridge per PyKPI_calcolo: per default applica L1.
    Se cfg specifica esplicitamente un filtro (OFF/L1) lo rispetta.
    """
    # Default coerente col commento: L1
    default_filter = "L1"

    # Se cfg contiene una scelta esplicita, usala; altrimenti resta L1
    if cfg and isinstance(cfg, dict):
        explicit = (
            cfg.get("regime_filter")
            or cfg.get("regime_filter_L1")
            or cfg.get("filter")
            or cfg.get("mode")
        )
        if explicit is not None:
            default_filter = explicit

    return apply_regime_L1(df, regime_filter=default_filter, cfg=cfg)



def _regime_l1_preflight_qc() -> None:
    expected = (20.0, 18.0, 15.0, 17.0, 2.0, 1.7, 2, 2, 2, "LATERAL")
    b = REGIME_L1_BASELINE
    sig = (
        b["adx_trend_enter"], b["adx_trend_exit"],
        b["adx_range_enter"], b["adx_range_exit"],
        b["atr_volatile_enter"], b["atr_volatile_exit"],
        b["confirm_bars_trend"], b["confirm_bars_range"], b["confirm_bars_volatile"],
        b["lateral_label"],
    )
    if sig != expected:
        raise RuntimeError(
            f"[REGIME_L1] Baseline changed without bump. version={REGIME_L1_VERSION} sig={sig}"
        )

_regime_l1_preflight_qc()
