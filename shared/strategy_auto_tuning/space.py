from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Iterable

import re

import pandas as pd


_SPLIT_RE = re.compile(r"\s*[|;]\s*")


def _coerce_scalar(x: str) -> Any:
    """
    Convert a single token to int/float when possible, otherwise keep as string.
    Also handles Italian decimal comma (e.g. '10,5') -> 10.5 if the token is numeric-like.
    """
    s = str(x).strip()
    if s == "":
        return s

    # try int (pure digits, optional sign)
    if re.fullmatch(r"[+-]?\d+", s):
        try:
            return int(s)
        except Exception:
            return s

    # try float (allow decimal comma)
    s_norm = s.replace(",", ".")
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", s_norm):
        try:
            return float(s_norm)
        except Exception:
            return s

    return s


def parse_candidate_values(raw: Any) -> List[Any]:
    """
    Parse TUNING.candidate_values into a list of discrete candidate values.

        Supported examples:
      - "10|15|20"
      - "10;15;20"
      - "0,03;0,04;0,05"
      - "-0,01;0,00;0,01"

    Notes:
      - comma is treated as decimal separator, not as list separator
      - list separators supported: ";" and "|"

    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []

    s = str(raw).strip()

    # strip optional brackets
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
        s = s[1:-1].strip()

    if s == "":
        return []

    parts = [p for p in _SPLIT_RE.split(s) if p.strip() != ""]
    return [_coerce_scalar(p) for p in parts]


@dataclass(frozen=True)
class ParamSpec:
    param_name: str
    candidate_values: Sequence[Any]
    base_condition_id: Optional[int] = None
    field: Optional[str] = None
    how_to_use: Optional[str] = None
    notes: Optional[str] = None

    @property
    def name(self) -> str:
        # compatibility with engine.py which expects ParamSpec.name
        return self.param_name

@dataclass(frozen=True)
class SearchSpace:
    params: Sequence[ParamSpec]

    def as_dict(self) -> Dict[str, ParamSpec]:
        return {p.param_name: p for p in self.params}


REQUIRED_TUNING_COLS = ["param_name", "candidate_values", "base_condition_id", "field"]

def filter_tuning_by_condition_group(
    df_tuning: pd.DataFrame,
    df_conditions: pd.DataFrame,
    active_group: Optional[str],
) -> pd.DataFrame:
    """
    Keep only tuning rows whose base_condition_id belongs
    to CONDITIONS rows of the active ENTRY group.

    If active_group is None -> return df_tuning unchanged.
    """

    if active_group is None:
        return df_tuning

    if "id" not in df_conditions.columns or "group" not in df_conditions.columns:
        raise ValueError("CONDITIONS must contain 'id' and 'group' columns")

    cond = df_conditions.copy()

    cond["id"] = cond["id"].astype(str).str.strip()
    cond["group"] = cond["group"].astype(str).str.strip()

    cond = cond[cond["group"] == str(active_group).strip()]

    allowed_ids = set(cond["id"][cond["id"] != ""].tolist())

    if not allowed_ids:
        return df_tuning.iloc[0:0]

    df = df_tuning.copy()
    df["base_condition_id"] = df["base_condition_id"].astype(str).str.strip()

    return df[df["base_condition_id"].isin(allowed_ids)]


def build_space_from_tuning_df(df_tuning: pd.DataFrame) -> SearchSpace:
    missing = [c for c in REQUIRED_TUNING_COLS if c not in df_tuning.columns]
    if missing:
        raise ValueError(f"TUNING missing required columns: {missing}")

    params: List[ParamSpec] = []
    for _, row in df_tuning.iterrows():
        name = str(row.get("param_name", "")).strip()
        if name == "" or name.upper() == "USAGE":
            continue

        cand = parse_candidate_values(row.get("candidate_values"))
        if not cand:
            # skip empty space rows
            continue

        base_id_raw = row.get("base_condition_id")
        base_id: Optional[int] = None
        if base_id_raw is not None and not (isinstance(base_id_raw, float) and pd.isna(base_id_raw)):
            try:
                base_id = int(float(str(base_id_raw).replace(",", ".")))
            except Exception:
                # keep None if cannot parse
                base_id = None

        field = str(row.get("field", "")).strip() or None

        params.append(
            ParamSpec(
                param_name=name,
                candidate_values=cand,
                base_condition_id=base_id,
                field=field,
                how_to_use=str(row.get("how_to_use", "")).strip() or None,
                notes=str(row.get("notes", "")).strip() or None,
            )
        )

    if not params:
        return SearchSpace(params=[])

    return SearchSpace(params=params)


def build_space_from_tuning(
    config_strategy_xlsx: str,
    active_group: Optional[str] = None,
) -> SearchSpace:

    """
    Compatibility wrapper expected by engine.py:
    reads sheet TUNING from the XLSX and builds a discrete SearchSpace
    from candidate_values.
    """

    df_tuning = pd.read_excel(config_strategy_xlsx, sheet_name="TUNING")
    df_conditions = pd.read_excel(config_strategy_xlsx, sheet_name="CONDITIONS")

    df_tuning = filter_tuning_by_condition_group(
        df_tuning,
        df_conditions,
        active_group,
    )
    return build_space_from_tuning_df(df_tuning)