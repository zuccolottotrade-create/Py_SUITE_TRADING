# 04.03 Calcolo KPI (PyKPI_calcolo)

## 04.03.1 Scopo

Il modulo **Calcolo KPI (PyKPI_calcolo)** ha lo scopo di **arricchire i dati di mercato validati**
con indicatori tecnici e metriche quantitative utilizzabili dai moduli successivi.

Il modulo:
- calcola indicatori tecnici standard;
- aggiunge colonne KPI ai dati OHLCV;
- preserva integralmente la struttura temporale del dataset.

Il modulo NON prende decisioni strategiche e NON genera segnali.

---

## 04.03.2 Ambito

Il modulo opera:
- **a valle** di **04.02 Controllo coerenza dati**;
- **a monte** di **04.04 Classificazione Operativa** e **04.07 Run Strategia**.

È responsabile esclusivamente della **trasformazione quantitativa del dato**.

---

## 04.03.3 Input

### File in input

- **Prefisso atteso**: `CLEAN_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`
- **Header**: obbligatorio

Il file deve contenere:
- colonna temporale;
- colonne OHLCV coerenti;
- nessuna anomalia bloccante (dato già validato).

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- Filtro: file con prefisso `CLEAN_`

L’utente seleziona il file da arricchire con i KPI.

#### Modalità pipeline
- Il file di input è determinato automaticamente.
- Nessuna interazione utente.

---

## 04.03.4 Output

### File prodotti

- **Prefisso prodotto**: `KPI_`
- **Formato**: CSV

Il file di output contiene:
- tutte le colonne originali (timestamp, OHLCV);
- colonne KPI aggiuntive;
- nessuna rimozione o modifica dei dati di base.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento;
- timeframe;
- provenienza da dati CLEAN.

Esempio:
KPI_FDAX_15M.csv


---

## 04.03.5 Indicatori e KPI calcolati

Il modulo può calcolare, a titolo esemplificativo:

- medie mobili (SMA, EMA);
- indicatori di trend (Supertrend, slope, R²);
- indicatori di volatilità (ATR, ATR%);
- indicatori di momentum (RSI, ROC);
- metriche statistiche derivate (range, variazioni percentuali).

Gli indicatori calcolati:
- sono configurabili;
- producono una colonna dedicata ciascuno;
- possono contenere valori nulli nelle prime barre.

---

## 04.03.6 Flusso operativo

1. Lettura del file `CLEAN_`.
2. Validazione preliminare del dataset.
3. Calcolo sequenziale degli indicatori configurati.
4. Allineamento temporale delle serie.
5. Scrittura del file `KPI_`.

Il processo è deterministico e riproducibile.

---

## 04.03.7 Modalità di esecuzione

### CLI / runner

Il modulo è invocabile:
- tramite menu della pipeline;
- tramite runner dedicato;
- tramite script `.command`.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- esecuzione non interattiva;
- input determinato automaticamente;
- output scritto nella directory standard.

Senza `PIPELINE_MODE`:
- selezione manuale del file `CLEAN_`;
- conferma dei parametri KPI.

---

## 04.03.8 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- presenza delle colonne OHLCV richieste;
- assenza di valori non numerici nelle colonne di input;
- allineamento temporale delle serie;
- corretto popolamento delle colonne KPI.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file `KPI_`.

---

## 04.03.9 Vincoli e limitazioni

Il modulo PyKPI_calcolo:

- NON modifica i dati OHLCV;
- NON rimuove righe temporali;
- NON filtra segnali o regole;
- NON calcola metriche di performance.

Il modulo assume che il file `CLEAN_` sia coerente e completo.

---

## 04.03.10 Output atteso

L’output principale del modulo è il file:

**`KPI_*.csv`**

che rappresenta l’ingresso per:
- **04.04 Classificazione Operativa**
- **04.07 Run Strategia**

