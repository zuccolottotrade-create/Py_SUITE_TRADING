"""
strategy_auto_tuning (v1.0)

Package per l'ottimizzazione automatica di strategie rule-based basate su config_strategy (XLSX),
con tuning parametrico per-regime e composizione multi-regime via forward selection.

Vincoli v0:
- Nessuna modifica a struttura/colonne del template config_strategy
- Niente program synthesis (si ottimizzano solo parametri/enable/shift esistenti)
- VOLATILE/UNKNOWN default NO TRADE
"""
