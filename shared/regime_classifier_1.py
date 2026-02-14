from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Literal


import json
import os
from pathlib import Path

print("[DEBUG] regime_classifier_1 loaded from:", __file__)

def _to_float_series(x: pd.Series) -> pd.Series:
    """
    Robust float conversion:
    - numeric passthrough
    - EU: "3.060,15" -> 3060.15
    - US: "3,060.15" -> 3060.15
    """
    if pd.api.types.is_numeric_dtype(x):
        return x.astype("float64")

    s = x.astype(str).str.strip()

    has_dot = s.str.contains(r"\.", regex=True, na=False)
    has_comma = s.str.contains(r",", regex=True, na=False)
    both = has_dot & has_comma

    s2 = s.copy()

    # EU: ',' is decimal
    eu = both & (s.str.rfind(",") > s.str.rfind("."))
    s2.loc[eu] = (
        s.loc[eu]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    # US: '.' is decimal, ',' thousands
    us = both & ~eu
    s2.loc[us] = s.loc[us].str.replace(",", "", regex=False)

    # only comma => comma is decimal
    only_comma = has_comma & ~has_dot
    s2.loc[only_comma] = s.loc[only_comma].str.replace(",", ".", regex=False)

    out = pd.to_numeric(s2, errors="coerce")
    return out.astype("float64")




def _pick_col(df, names):
    """Ritorna il primo nome colonna esistente in df tra una lista di alias."""
    for n in names:
        if n in df.columns:
            return n
    return None



# =============================================================================
# Config filtro (CSV) - default per fine tuning
# Standard: _data/config_filtro_regime/config_filtro_<nome_filtro>.csv
# NOTE IMPORTANTI:
# - Questo CSV è OBBLIGATORIO (policy "niente fallback").
# - I valori devono essere numerici in formato EU (virgola ammessa) es: 0,35
# =============================================================================

def _find_repo_root(start: Path) -> Path:
    """
    Risale le directory finché trova la root del repo (marker: cartella '_data').
    Fallback: start.
    """
    p = start.resolve()
    for _ in range(10):
        if (p / "_data").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


def _config_path_this_filter() -> Path:
    """
    Config OBBLIGATORIO:
      <REPO_ROOT>/_data/config_filtro_regime/config_filtro_regime_classifier_1.csv

    Nota: REPO_ROOT viene risolto risalendo da questo file (non dal CWD),
    così funziona da qualunque working directory (wizard, pipeline, strategy_creator).
    """
    repo_root = _find_repo_root(Path(__file__).resolve())
    return repo_root / "_data" / "config_filtro_regime" / "config_filtro_regime_classifier_1.csv"


def _parse_decimal_comma(value: str, *, param: str = "") -> float:
    """
    Parse numeri con virgola decimale italiana.
    Accetta:
      - "0,35" -> 0.35
      - "12"   -> 12.0
      - "12.5" -> 12.5
    """
    s = (value or "").strip()
    if not s:
        raise ValueError(f"[REGIME_L1][CFG] valore vuoto per param='{param}'")
    try:
        s = s.replace(",", ".")
        return float(s)
    except Exception as e:
        raise ValueError(f"[REGIME_L1][CFG] numero non valido per param='{param}': '{value}' ({e})")


REGIME_L1_REQUIRED_PARAMS = [
    # --- TREND ---
    "adx_trend_enter",
    "adx_trend_exit",
    # --- ADX band bassa (RANGE/LATERAL) ---
    "adx_range_enter",
    "adx_range_exit",
    # --- VOLATILE (ATR_PCT) ---
    "atr_volatile_enter",
    "atr_volatile_exit",
    # --- RANGE vs LATERAL (REGIME1) ---
    "atr_range_enter",
    "atr_range_exit",
    "bb_width_range_enter",
    "bb_width_range_exit",
    # --- BB params (solo fallback se KPI_BB_WIDTH_PCT assente) ---
    "bb_period",
    "bb_k",
    # --- debounce ---
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
# Required base columns:
# - close
# Required KPI columns:
# - KPI_EMA_21, KPI_EMA_50, KPI_EMA_200
# - KPI_ADX_14
# - KPI_ATR_PCT_14
#
# Optional KPI:
# - KPI_BB_WIDTH_PCT (if missing, we compute BB width from close using bb_period/bb_k from cfg)
# ==========================================================

def _require_columns(df: pd.DataFrame, base: list[str], kpis: list[str]) -> None:
    missing_base = [c for c in base if c not in df.columns]
    missing_kpi = [c for c in kpis if c not in df.columns]
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
    # --- RANGE vs LATERAL (REGIME1) ---
    atr_range_enter: float = _AUTO,
    atr_range_exit: float = _AUTO,
    bb_width_range_enter: float = _AUTO,
    bb_width_range_exit: float = _AUTO,
    # --- Bollinger (solo se KPI_BB_WIDTH_PCT non presente) ---
    bb_period: int = _AUTO,
    bb_k: float = _AUTO,
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
    REGIME – Livello 1 (contesto primario) – implementazione REGIME1 (30m)

    Stati canonici:
      - TREND_UP
      - TREND_DOWN
      - RANGE
      - LATERAL
      - VOLATILE
      - UNKNOWN

    Output:
      - REGIME_L1_RAW    : classificazione istantanea (debug/QC)
      - REGIME_L1        : stato stabilizzato (debounce + hysteresis)
      - REGIME_L1_CODE   : codice numerico stabile (REGIME1)
      - REGIME_L1_SWITCH : 1 quando cambia stato (su barra), altrimenti 0
      - REGIME_L1_REASON : driver dominante dello stato RAW

    Priorità RAW (REGIME1):
      1) VOLATILE
      2) TREND (UP/DOWN)
      3) RANGE
      4) LATERAL
      5) UNKNOWN
    """
    # ------------------------------------------------------------
    # Policy: nessun default hardcoded.
    # Se non passi esplicitamente i parametri, li risolvo dal CSV
    # obbligatorio (o SystemExit in _load_filter_defaults_from_csv).
    # ------------------------------------------------------------
    resolved = resolve_regime_l1_params()

    if adx_trend_enter is _AUTO:
        adx_trend_enter = float(resolved["adx_trend_enter"])
    if adx_trend_exit is _AUTO:
        adx_trend_exit = float(resolved["adx_trend_exit"])
    if adx_range_enter is _AUTO:
        adx_range_enter = float(resolved["adx_range_enter"])
    if adx_range_exit is _AUTO:
        adx_range_exit = float(resolved["adx_range_exit"])
    if atr_volatile_enter is _AUTO:
        atr_volatile_enter = float(resolved["atr_volatile_enter"])
    if atr_volatile_exit is _AUTO:
        atr_volatile_exit = float(resolved["atr_volatile_exit"])

    # --- RANGE vs LATERAL (REGIME1) ---
    if atr_range_enter is _AUTO:
        atr_range_enter = float(resolved["atr_range_enter"])
    if atr_range_exit is _AUTO:
        atr_range_exit = float(resolved["atr_range_exit"])
    if bb_width_range_enter is _AUTO:
        bb_width_range_enter = float(resolved["bb_width_range_enter"])
    if bb_width_range_exit is _AUTO:
        bb_width_range_exit = float(resolved["bb_width_range_exit"])

    # Bollinger (solo fallback)
    if bb_period is _AUTO:
        bb_period = int(resolved["bb_period"])
    if bb_k is _AUTO:
        bb_k = float(resolved["bb_k"])

    if confirm_bars_trend is _AUTO:
        confirm_bars_trend = int(resolved["confirm_bars_trend"])
    if confirm_bars_range is _AUTO:
        confirm_bars_range = int(resolved["confirm_bars_range"])
    if confirm_bars_volatile is _AUTO:
        confirm_bars_volatile = int(resolved["confirm_bars_volatile"])

    print(
        "[DEBUG][REGIME_L1] usando parametri:",
        f"adx_trend_enter={adx_trend_enter}, adx_trend_exit={adx_trend_exit}, "
        f"adx_range_enter={adx_range_enter}, adx_range_exit={adx_range_exit}, "
        f"atr_volatile_enter={atr_volatile_enter}, atr_volatile_exit={atr_volatile_exit}, "
        f"atr_range_enter={atr_range_enter}, atr_range_exit={atr_range_exit}, "
        f"bb_width_range_enter={bb_width_range_enter}, bb_width_range_exit={bb_width_range_exit}, "
        f"bb_period={bb_period}, bb_k={bb_k}, "
        f"confirm_bars_trend={confirm_bars_trend}, confirm_bars_range={confirm_bars_range}, "
        f"confirm_bars_volatile={confirm_bars_volatile}",
    )

    # ------------------------------------------------------------
    # Required columns (base + KPI)
    # ------------------------------------------------------------
    required_base = ["close", "KPI_EMA_21", "KPI_EMA_50", "KPI_EMA_200", "KPI_ADX_14", "KPI_ATR_PCT_14"]
    missing = [c for c in required_base if c not in df.columns]
    if missing:
        raise ValueError(f"[REGIME_L1] Colonne mancanti: {missing}")

    # --- segnali base -----------------------------------------------------
    ema21 = _to_float_series(df["KPI_EMA_21"])
    ema50 = _to_float_series(df["KPI_EMA_50"])
    ema200 = _to_float_series(df["KPI_EMA_200"])

    ema_up = (ema21 > ema50) & (ema50 > ema200)
    ema_dn = (ema21 < ema50) & (ema50 < ema200)

    # KPI regime
    adx = _to_float_series(df["KPI_ADX_14"])
    atrp = _to_float_series(df["KPI_ATR_PCT_14"])

    # --- BB width % (REGIME1) -------------------------------------------
    # Preferiamo una colonna già calcolata, se presente.
    if "KPI_BB_WIDTH_PCT" in df.columns:
        bb_width_pct = _to_float_series(df["KPI_BB_WIDTH_PCT"])
    else:
        # Calcolo BB width % da close:
        # width_pct = (upper - lower) / mid * 100
        close = _to_float_series(df["close"])
        mid = close.rolling(bb_period, min_periods=bb_period).mean()
        std = close.rolling(bb_period, min_periods=bb_period).std(ddof=0)
        upper = mid + (bb_k * std)
        lower = mid - (bb_k * std)
        bb_width_pct = ((upper - lower) / mid) * 100.0

    # --- condizioni ENTER/EXIT (hysteresis) ------------------------------
    # TREND: ADX alto + EMA in ordine
    trend_up_enter = ema_up & (adx >= adx_trend_enter)
    trend_dn_enter = ema_dn & (adx >= adx_trend_enter)
    trend_ok_exit = adx >= adx_trend_exit  # “trend ancora valido” lato ADX

    # VOLATILE: ATR_PCT alto MA non in trend forte (REGIME1)
    volatile_enter = (atrp >= atr_volatile_enter) & (adx < adx_trend_enter)
    volatile_ok_exit = (atrp >= atr_volatile_exit) & (adx < adx_trend_exit)

    # RANGE vs LATERAL (REGIME1)
    # RANGE: ADX basso + ATR_PCT sufficiente + BB width sufficiente
    range_enter = (adx < adx_range_enter) & (atrp >= atr_range_enter) & (bb_width_pct >= bb_width_range_enter)
    range_ok_exit = (adx < adx_range_exit) & (atrp >= atr_range_exit) & (bb_width_pct >= bb_width_range_exit)

    # LATERAL (REGIME1): ADX basso e non classificato come RANGE (fallback "calmo")
    lateral_enter = (adx < adx_range_enter) & ~range_enter

    # --- RAW: classificazione istantanea (priorità REGIME1) ---------------
    # REGIME1: priorità = VOLATILE -> TREND -> RANGE -> LATERAL (fallback)
    raw = np.select(
        [volatile_enter, trend_up_enter, trend_dn_enter, range_enter],
        ["VOLATILE", "TREND_UP", "TREND_DOWN", "RANGE"],
        default="LATERAL",
    )

    df[col_raw] = pd.Series(raw, index=df.index).astype(str).str.strip().str.upper()
    df[col_reason] = df[col_raw]  # reason = raw driver

    # ------------------------------------------------------------
    # REGIME1: fallback deterministico per eliminare UNKNOWN "non necessario"
    # Tutto ciò che non è classificato e NON è in trend ADX alto -> LATERAL
    # ------------------------------------------------------------
    _raw = df[col_raw].astype(str).str.strip().str.upper()
    m_unknown = _raw.eq("UNKNOWN") & (adx < adx_trend_enter)

    df.loc[m_unknown, col_raw] = "LATERAL"
    df.loc[m_unknown, col_reason] = "LATERAL_FALLBACK"

    print("[DEBUG][REGIME1] fallback UNKNOWN->LATERAL rows =", int(m_unknown.sum()))

    # ------------------------------------------------------------
    # REGIME1: fallback deterministico per eliminare UNKNOWN "non necessario"
    # Tutto ciò che non è classificato e NON è in trend ADX alto -> LATERAL
    # ------------------------------------------------------------
    _raw = df[col_raw].astype(str).str.strip().str.upper()
    m_unknown = _raw.eq("UNKNOWN") & (adx < adx_trend_enter)

    df.loc[m_unknown, col_raw] = "LATERAL"
    df.loc[m_unknown, col_reason] = "LATERAL_FALLBACK"
    print("[DEBUG][REGIME1] fallback UNKNOWN->LATERAL rows =", int(m_unknown.sum()))

    # --- Debounce helper: N barre consecutive True ------------------------
    def _confirm(sig: pd.Series, n: int) -> pd.Series:
        if n <= 1:
            return sig.fillna(False)
        return sig.fillna(False).rolling(n, min_periods=n).sum().ge(n)

    trend_up_c = _confirm(trend_up_enter, confirm_bars_trend)
    trend_dn_c = _confirm(trend_dn_enter, confirm_bars_trend)
    volatile_c = _confirm(volatile_enter, confirm_bars_volatile)
    range_c = _confirm(range_enter, confirm_bars_range)
    # lateral non necessita debounce dedicato: è fallback “calmo”

    # --- State machine (sequenziale, deterministica) ----------------------
    # Stato iniziale: RAW della prima riga
    states: list[str] = []
    prev: str | None = None

    for i in range(len(df)):
        if prev is None:
            prev0 = str(df.iloc[i][col_raw]).strip().upper()
            # Se la prima riga è UNKNOWN ma non siamo in trend ADX alto, avvia come LATERAL
            if prev0 == "UNKNOWN" and bool(adx.iat[i] < adx_trend_enter):
                prev0 = "LATERAL"
                df.at[df.index[i], col_reason] = "LATERAL_FALLBACK_INIT"
            prev = prev0
            states.append(prev)
            continue

        # Segnali “confermati”
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

        # Se non lo mantieni, prova transizioni in ordine di priorità REGIME1
        if sv:
            prev = "VOLATILE"
        elif su:
            prev = "TREND_UP"
        elif sd:
            prev = "TREND_DOWN"
        elif sr:
            prev = "RANGE"

        else:
            # fallback: RAW (ma evita UNKNOWN quando ADX non è da trend)
            prev_raw = str(df.iloc[i][col_raw]).strip().upper()
            if prev_raw == "UNKNOWN" and bool(adx.iat[i] < adx_trend_enter):
                prev = "LATERAL"
                df.at[df.index[i], col_reason] = "LATERAL_FALLBACK_SM"
            else:
                prev = prev_raw

        states.append(prev)

    df[col_out] = pd.Series(states, index=df.index)

    # --- SWITCH flag ------------------------------------------------------
    df[col_switch] = (df[col_out] != df[col_out].shift(1)).fillna(False).astype(int)

    # --- CODE mapping (REGIME1, stabile) ---------------------------------
    code_map = {
        "LATERAL": 0,
        "RANGE": 1,
        "VOLATILE": 2,
        "TREND_UP": 3,
        "TREND_DOWN": 4,
        "UNKNOWN": 9,
    }
    df[col_code] = df[col_out].map(code_map).fillna(9).astype(int)

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

    print("[DEBUG][REGIME_L1] apply_regime_L1 rf =", rf, "regime_filter=", regime_filter, "cfg_keys=",
          list(cfg.keys()) if cfg else None)

    if rf == "OFF":
        # garantiamo colonne presenti per stabilità downstream
        out = df.copy()
        out["REGIME_L1_RAW"] = "UNKNOWN"
        out["REGIME_L1"] = "UNKNOWN"
        out["REGIME_L1_CODE"] = 9
        out["REGIME_L1_SWITCH"] = 0
        out["REGIME_L1_REASON"] = "UNKNOWN"
        return out

    if rf != "L1":
        raise ValueError(f"[REGIME_L1] regime_filter non supportato: {regime_filter}")

    out = df.copy()
    out = update_regime_state_Livello1(out)
    return out


def apply_regime(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """
    Bridge legacy: chiamata generica apply_regime(df, cfg) usata da loader/wizard.
    """
    return apply_regime_L1(df, regime_filter="L1", cfg=cfg)


