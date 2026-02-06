from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Literal


import json
import os
from pathlib import Path

print("[DEBUG] regime_classifier_1 loaded from:", __file__)


# =============================================================================
# Config filtro (CSV) - default per fine tuning
# Standard: _data/config_filtro_regime/config_filtro_<nome_modulo>.csv
# Esempio qui: config_filtro_regime_classifier_1.csv
# NOTE:
# - separatore: ;
# - decimali: VIRGOLA (es: 20,0)  -> il punto (20.0) è considerato ERRORE
# - colonne attese: param ; value ; note
# =============================================================================

def _suite_root_from_shared() -> Path:
    """
    __file__ è in <SUITE_ROOT>/shared/regime_classifier_1.py
    quindi parents[1] = <SUITE_ROOT>.
    """
    return Path(__file__).resolve().parents[1]

def _config_dir_regime() -> Path:
    return (_suite_root_from_shared() / "_data" / "config_filtro_regime").resolve()

def _config_path_this_filter() -> Path:
    # nome file standard: config_filtro_<nome_modulo>.csv
    return (_config_dir_regime() / "config_filtro_regime_classifier_1.csv").resolve()

def _parse_decimal_comma(value: str, *, param: str) -> float:
    """
    Regola: accetta solo virgola decimale.
    - "20,0" OK
    - "20.0" ERRORE (standard richiesto)
    - "2" OK
    """
    s = (value or "").strip()
    if s == "":
        raise ValueError(f"[REGIME_L1][CFG] value vuoto per param='{param}'")

    # vieto esplicitamente il punto come decimale
    if "." in s:
        raise ValueError(
            f"[REGIME_L1][CFG] formato non valido per param='{param}': '{s}'. "
            f"Usa la virgola decimale (es: 20,0) e NON il punto (20.0)."
        )

    # converto virgola -> punto per float()
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception as e:
        raise ValueError(f"[REGIME_L1][CFG] numero non valido per param='{param}': '{value}' ({e})")

REGIME_L1_REQUIRED_PARAMS = [
    "adx_trend_enter",
    "adx_trend_exit",
    "adx_range_enter",
    "adx_range_exit",
    "atr_volatile_enter",
    "atr_volatile_exit",
    "confirm_bars_trend",
    "confirm_bars_range",
    "confirm_bars_volatile",
]





def _load_filter_defaults_from_csv() -> dict:
    """
    Carica override parametri da:
      _data/config_filtro_regime/config_filtro_regime_classifier_1.csv

    Ritorna dict con chiavi dei parametri L1.
    Se il file non esiste -> {} (nessun override).
    """
    path = _config_path_this_filter()

    if not path.exists():
        print("\n❌❌❌  ALERT CONFIG FILTRO REGIME  ❌❌❌")
        print("[REGIME_L1][CFG] File di configurazione OBBLIGATORIO NON trovato:")
        print(f"  {path}\n")
        print("Policy: niente fallback. Esecuzione interrotta.\n")
        raise SystemExit(1)

    # leggiamo come stringhe per controllare il formato numerico (virgola)
    df_cfg = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)

    # --- schema richiesto per il CSV config ---
    required_cols = {"param", "value"}
    optional_cols = {"note"}

    missing = required_cols - set(df_cfg.columns)
    if missing:
        raise ValueError(f"[REGIME_L1][CFG] colonne mancanti in {path.name}: {sorted(missing)}")

    # colonna opzionale: se manca, la creiamo vuota per stabilità downstream
    if "note" not in df_cfg.columns:
        df_cfg["note"] = ""

    out: dict = {}
    for _, r in df_cfg.iterrows():
        param = (r["param"] or "").strip()
        value = (r["value"] or "").strip()

        if not param:
            continue

        # Qui vogliamo SOLO parametri numerici.
        # Se in futuro serve un label stringa, lo gestiamo separatamente.
        num = _parse_decimal_comma(value, param=param)

        # cast int per i confirm_bars_*
        if param.startswith("confirm_bars_"):
            out[param] = int(num)
        else:
            out[param] = float(num)

    # --- REQUIRED params check (policy: niente fallback) ---
    missing_required = [k for k in REGIME_L1_REQUIRED_PARAMS if k not in out]
    if missing_required:
        print("\n❌❌❌  ALERT CONFIG FILTRO REGIME  ❌❌❌")
        print(f"[REGIME_L1][CFG] File presente ma INCOMPLETO: {path.name}")
        print("Parametri mancanti:")
        for m in missing_required:
            print(f"  - {m}")
        print("\nPolicy: niente fallback. Esecuzione interrotta.\n")
        raise SystemExit(1)


    if out:
        print(
            "[DEBUG][REGIME_L1][CFG] override da CSV applicati:",
            ", ".join(f"{k}={v}" for k, v in sorted(out.items()))
        )
    else:
        print("[DEBUG][REGIME_L1][CFG] CSV presente ma nessun override valido trovato")

    return out



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
    """
    Alias esplicito: L1 usa lo stesso validate_input() (contract base + KPI).
    """
    validate_input(df)


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








def resolve_regime_l1_params(
    profile: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """
    Resolve parametri L1 (ordine priorità crescente):
      0) profilo (BASELINE o preset)
      1) override da CSV config_filtro_regime_classifier_1.csv (se presente)
      2) override da ENV JSON (REGIME_L1_OVERRIDES_JSON)
      3) override da argomento python (massima priorità)
    """


    params = _load_filter_defaults_from_csv()  # OBBLIGATORIO e completo (altrimenti SystemExit)



    # 2) override da ENV JSON (se presente)
    env_json = os.getenv("REGIME_L1_OVERRIDES_JSON", "").strip()
    if env_json:
        try:
            env_over = json.loads(env_json)
            if not isinstance(env_over, dict):
                raise ValueError("REGIME_L1_OVERRIDES_JSON must be a JSON object")
            params.update(env_over)
        except Exception as e:
            raise ValueError(f"[REGIME_L1] Bad REGIME_L1_OVERRIDES_JSON: {e}")

    # 3) override da argomento python (massima priorità)
    if overrides:
        params.update(overrides)

    return params

_AUTO = object()

def update_regime_state_Livello1(
    df: pd.DataFrame,
    *,
    # --- soglie (enter/exit = hysteresis) ---
    adx_trend_enter: float = _AUTO,
    adx_trend_exit: float = _AUTO,
    adx_range_enter: float = _AUTO,
    adx_range_exit: float = _AUTO,
    atr_volatile_enter: float = _AUTO,
    atr_volatile_exit: float = _AUTO,
    # --- debounce (barre consecutive richieste) ---
    confirm_bars_trend: int = _AUTO,
    confirm_bars_volatile: int = _AUTO,
    confirm_bars_range: int = _AUTO,

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
    # ------------------------------------------------------------
    # Policy: nessun default hardcoded. Se non passi esplicitamente
    # i parametri, li risolvo dal CSV obbligatorio (o SystemExit).
    # ------------------------------------------------------------
    resolved = resolve_regime_l1_params()

    if adx_trend_enter is _AUTO: adx_trend_enter = float(resolved["adx_trend_enter"])
    if adx_trend_exit  is _AUTO: adx_trend_exit  = float(resolved["adx_trend_exit"])
    if adx_range_enter is _AUTO: adx_range_enter = float(resolved["adx_range_enter"])
    if adx_range_exit  is _AUTO: adx_range_exit  = float(resolved["adx_range_exit"])
    if atr_volatile_enter is _AUTO: atr_volatile_enter = float(resolved["atr_volatile_enter"])
    if atr_volatile_exit  is _AUTO: atr_volatile_exit  = float(resolved["atr_volatile_exit"])

    if confirm_bars_trend    is _AUTO: confirm_bars_trend    = int(resolved["confirm_bars_trend"])
    if confirm_bars_range    is _AUTO: confirm_bars_range    = int(resolved["confirm_bars_range"])
    if confirm_bars_volatile is _AUTO: confirm_bars_volatile = int(resolved["confirm_bars_volatile"])

    print(
        "[DEBUG][REGIME_L1] usando parametri:",
        f"adx_trend_enter={adx_trend_enter}, adx_trend_exit={adx_trend_exit}, "
        f"adx_range_enter={adx_range_enter}, adx_range_exit={adx_range_exit}, "
        f"atr_volatile_enter={atr_volatile_enter}, atr_volatile_exit={atr_volatile_exit}, "
        f"confirm_bars_trend={confirm_bars_trend}, confirm_bars_range={confirm_bars_range}, "
        f"confirm_bars_volatile={confirm_bars_volatile}"
    )


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
    b = globals().get("REGIME_L1_BASELINE", None)
    if b is None:
        raise RuntimeError("[REGIME_L1] REGIME_L1_BASELINE is not defined (load/config order issue).")


    required_keys = (
        "adx_trend_enter",
        "adx_trend_exit",
        "adx_range_enter",
        "adx_range_exit",
        "atr_volatile_enter",
        "atr_volatile_exit",
        "confirm_bars_trend",
        "confirm_bars_range",
        "confirm_bars_volatile",
        "lateral_label",
    )

    missing = [k for k in required_keys if k not in b]
    if missing:
        raise RuntimeError(
            f"[REGIME_L1] Missing keys in baseline config: {missing}"
        )

    if not isinstance(b["lateral_label"], str):
        raise RuntimeError(
            "[REGIME_L1] lateral_label must be a string"
        )

    if REGIME_L1_VERSION is None:
        raise RuntimeError(
            "[REGIME_L1] REGIME_L1_VERSION must be explicitly set"
        )
