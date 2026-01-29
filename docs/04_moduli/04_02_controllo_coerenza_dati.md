# 04.02 Controllo coerenza dati

## 04.02.1 Scopo

Il modulo **Controllo coerenza dati** ha lo scopo di verificare che i dati OHLCV siano
**coerenti, completi e utilizzabili** dai moduli successivi della pipeline.

Il modulo:
- valida la struttura del CSV (colonne e formati);
- esegue regole di controllo qualità (QC rules);
- produce un output classificato che separa dati accettati e dati rifiutati.

L’obiettivo operativo è produrre un file **CLEAN_** affidabile, utilizzabile da:
- **PyKPI_calcolo**
- moduli successivi (classificazione, strategia, report)

---

## 04.02.2 Ambito

Il modulo opera:
- **a valle** di **Estrazione dati** (dati grezzi);
- **a monte** del calcolo KPI e dell’intera catena strategica.

Il modulo è responsabile della definizione operativa di “dato accettabile”.

---

## 04.02.3 Input

### File in input

- **Prefisso atteso**: tipicamente `RAW_` (o file OHLCV grezzo equivalente)
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`
- **Header**: obbligatorio

### Colonne minime richieste

Il file deve contenere almeno:
- colonna temporale (timestamp / datetime)
- `open`
- `high`
- `low`
- `close`
- `volume` (se previsto per l’asset; se assente deve essere gestito in modo esplicito)

Le colonne devono essere numeriche (eccetto il timestamp).

---

### Selezione file (modalità interattiva)

- Directory di default: `_data/Test Data`
- Filtro: file `.csv` compatibili (es. `RAW_*.csv` o file dati grezzi)

L’utente seleziona manualmente il file da validare.

---

## 04.02.4 Output

Il modulo produce tipicamente tre categorie di output:

### 1) File dati accettati (CLEAN)

- **Prefisso prodotto**: `CLEAN_`
- **Contenuto**: dati OHLCV coerenti, pronti per KPI

Esempio naming:
CLEAN_FDAX_15M.csv


---

## 04.02.5 Regole di controllo qualità (QC Rules)

Il modulo applica un insieme di regole. Le principali categorie operative sono:

### Timestamp
- individuazione di timestamp duplicati;
- verifica ordinamento temporale crescente;
- verifica di buchi temporali (se previsto dal controllo).

### OHLC (coerenza base)
- `high >= max(open, close)`
- `low <= min(open, close)`
- `high >= low`
- valori non nulli e numerici

### OHLC (anomalie strutturali)
- barre con OHLC tutti uguali (potenziale dato sospetto, in base alla regola);
- valori estremi o fuori range (se previsto).

### Volume
- volume non numerico o negativo (non ammesso);
- volume nullo (ammesso solo se definito esplicitamente come accettabile per l’asset).

Le regole possono produrre:
- OK
- WARN
- ERROR

Le regole classificano l’esito globale del file e determinano la produzione di CLEAN vs REJECT.

---

## 04.02.6 Flusso operativo

1. Lettura del CSV di input.
2. Validazione preliminare (struttura, header, separatori, colonne minime).
3. Applicazione sequenziale delle regole QC.
4. Aggregazione degli esiti (OK/WARN/ERROR).
5. Produzione del report QC.
6. Se esito accettabile:
   - scrittura del file `CLEAN_`
7. Se esito non accettabile:
   - scrittura del file `REJECT_`

Il processo deve essere deterministico.

---

## 04.02.7 Modalità di esecuzione

### CLI / runner

Il modulo è invocabile:
- tramite menu della pipeline;
- tramite runner dedicato (`python -m ...` se previsto);
- tramite script `.command`.

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- esecuzione non interattiva;
- input determinato dal flusso precedente;
- output scritto in directory standard.

Senza `PIPELINE_MODE`:
- selezione manuale del file;
- stampa a video del riepilogo QC.

---

## 04.02.8 Validazioni e criteri di accettazione

Un file è considerato **CLEAN** se:

- le colonne minime sono presenti;
- i valori OHLC sono coerenti;
- non esistono anomalie bloccanti (ERROR) secondo le regole attive;
- eventuali WARN sono accettabili secondo le policy operative.

Un file è considerato **REJECT** se:

- mancano colonne minime;
- timestamp non gestibili (duplicati gravi / disordine non recuperabile);
- OHLC incoerenti o non numerici;
- presenza di ERROR non sanabili.

---

## 04.02.9 Errori tipici e risoluzione

**Errore: colonne mancanti**
- Causa: file non conforme allo standard OHLCV.
- Azione: rigenerare il file dall’estrazione o correggere la fonte.

**Errore: timestamp duplicati**
- Causa: esportazione duplicata o merge errato.
- Azione: rigenerare dati; se previsto, attivare routine di deduplica controllata.

**Errore: OHLC incoerenti**
- Causa: dati corrotti o conversioni numeriche errate.
- Azione: verificare separatori e formato numerico; rigenerare.

---

## 04.02.10 Vincoli e limitazioni

Il modulo Controllo coerenza dati:

- NON calcola KPI;
- NON modifica i dati per “aggiustarli” automaticamente (salvo policy esplicite);
- NON prende decisioni strategiche;
- NON produce segnali.

Il modulo definisce il confine operativo tra dato grezzo e dato utilizzabile.

---

## 04.02.11 Output atteso

L’output principale di questo modulo è il file:

**`CLEAN_*.csv`**

che rappresenta l’unico input valido per:
- calcolo KPI;
- classificazione operativa;
- catena strategica completa.
