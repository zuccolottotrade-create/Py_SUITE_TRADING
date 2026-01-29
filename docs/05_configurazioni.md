# 05. Configurazioni e file di controllo

## 05.1 Scopo

Questa sezione definisce:
- dove risiedono i file di configurazione della Py_SUITE_TRADING;
- quali file sono considerati “fonte di verità” per regole e parametri;
- come devono essere versionati e mantenuti;
- come viene validata la configurazione prima dell’esecuzione.

Le configurazioni sono considerate parte integrante del sistema e devono essere gestite con la stessa disciplina del codice.

---

## 05.2 Principi di gestione delle configurazioni

Le configurazioni della suite seguono questi principi:

- **Configurazione esterna**: regole e parametri non devono essere hard-coded.
- **Versionamento**: i file di configurazione devono essere tracciati via Git quando possibile.
- **Riproducibilità**: a parità di config e dati l’output deve essere deterministico.
- **Validazione preventiva**: ogni configurazione deve passare un controllo QC prima dell’uso operativo.

---

## 05.3 Tipologie di configurazione

La suite utilizza tipicamente tre famiglie di configurazioni:

1. **Configurazioni KPI**
   - definiscono quali indicatori calcolare, finestre, parametri.
   - influenzano direttamente l’output `KPI_`.

2. **Configurazioni Strategia**
   - definiscono regole ENTRY/EXIT/filtri in formato tabellare.
   - influenzano `STRATEGIA_` e quindi `SIGNAL_` e `REPORT_`.

3. **Configurazioni di soglia / classificazione**
   - definiscono soglie numeriche per etichette operative (bassa/media/alta).
   - influenzano `CLASSIFICAZIONE_OPERATIVA_`.

---

## 05.4 File di configurazione strategia (config_strategy)

### Ruolo

Il file di configurazione strategia (tipicamente `config_strategy.xlsx` o equivalente CSV)
rappresenta la definizione esplicita delle regole operative.

La configurazione strategica deve consentire di definire:
- condizioni di regime (filtri);
- condizioni di ingresso (ENTRY);
- condizioni di uscita (EXIT);
- lato (LONG/SHORT/BOTH);
- logiche di composizione (AND/OR) e raggruppamenti.

---

### Requisiti operativi

La configurazione strategica:
- deve essere **tabellare**;
- deve prevedere campi consistenti (nomi colonne stabili);
- deve essere validata dal **Strategy QC Preflight** prima dell’esecuzione.

Non è ammesso usare configurazioni “parziali” o modificate manualmente senza validazione.

---

## 05.5 Colonne operative tipiche (schema logico)

Le colonne operative tipiche includono:

- `id` : identificatore univoco della regola/condizione
- `enabled` : flag attivazione (VERO/FALSO)
- `scope` : ambito (REGIME / ENTRY / EXIT)
- `side` : lato (LONG / SHORT / BOTH)
- `group` : gruppo logico (G0, G1, …)
- `logic` : aggregazione (AND / OR)
- `lhs_col` : colonna KPI o campo (sinistra)
- `operator` : operatore (==, >, <, between, cross_above, cross_below, …)
- `rhs_type` : tipo RHS (VALUE / COLUMN / LIST)
- `rhs_value` : valore fisso o lista
- `rhs_col` : colonna RHS (se rhs_type=COLUMN)
- `shift` : shift temporale per evaluation
- `negate` : negazione della condizione

Lo schema esatto può variare per versione, ma i concetti operativi devono essere mantenuti.

---

## 05.6 Strategy QC Preflight

### Scopo

Il **Strategy QC Preflight** è una fase obbligatoria di validazione preventiva della configurazione strategica.

Verifica:
- completezza delle colonne richieste;
- validità degli operatori;
- validità di scope/side/logic;
- coerenza dei gruppi logici;
- presenza di regole abilitabili e non ambigue.

---

### Output del QC

Il QC produce tipicamente:
- riepilogo conteggi: OK / WARN / ERROR / DISABLED
- lista regole verificate (solo enabled=VERO)
- eventuale tabella normalizzata di controllo

In presenza di ERROR:
- la strategia non deve essere eseguita.

---

## 05.7 Gestione delle versioni di configurazione

È ammesso mantenere più versioni della configurazione (es. template, test, v2, ecc.).

Regole operative:
- le versioni devono essere chiaramente distinguibili nel naming;
- la pipeline deve utilizzare una versione esplicita e non ambigua;
- il QC deve essere rieseguito dopo ogni modifica.

Esempi:
- `config_strategy_template.xlsx`
- `config_strategy_v2.xlsx`
- `config_strategy_vtest.xlsx`

---

## 05.8 Vincoli e best practice

- Non modificare configurazioni in corsa durante l’esecuzione.
- Non copiare “a mano” righe tra versioni senza rieseguire QC.
- Mantenere naming stabile delle colonne KPI referenziate dalle regole.
- Ogni modifica a operatori o semantica deve aggiornare:
  - QC preflight
  - documentazione
  - (se previsto) test automatici

---

## 05.9 Output atteso

Le configurazioni, una volta validate, determinano in modo diretto:

- KPI calcolati (`KPI_*.csv`)
- classificazione (`CLASSIFICAZIONE_OPERATIVA_*.csv`)
- regole strategiche (`STRATEGIA_*.csv`)
- segnali (`SIGNAL_*.csv`)
- report (`REPORT_*.csv`)

Le configurazioni sono quindi parte determinante della riproducibilità della suite.
