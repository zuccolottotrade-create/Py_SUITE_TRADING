# 04.04 Classificazione Operativa

## 04.04.1 Scopo

Il modulo **Classificazione Operativa** ha lo scopo di **interpretare i KPI quantitativi**
per descrivere il **contesto operativo del mercato** mediante etichette strutturate.

Il modulo:
- analizza indicatori e metriche calcolate a monte;
- applica criteri quantitativi e soglie configurabili;
- produce una classificazione sintetica del contesto.

Il modulo NON genera strategie, NON produce regole operative
e NON applica segnali ai dati storici.

---

## 04.04.2 Ambito

Il modulo opera:
- **a valle** di **04.03 PyKPI_calcolo**;
- **a monte** di **04.05 Strategy Mapping**.

È responsabile della **traduzione dei numeri in categorie operative**.

---

## 04.04.3 Input

### File in input

- **Prefisso atteso**: `KPI_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`
- **Header**: obbligatorio

Il file di input contiene:
- dati OHLCV validati;
- colonne KPI (trend, volatilità, liquidità, ecc.).

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- Filtro: file con prefisso `KPI_`

L’utente seleziona il file KPI da classificare.

#### Modalità pipeline
- Il file di input è determinato automaticamente.
- Nessuna interazione utente.

---

## 04.04.4 Output

### File prodotti

- **Prefisso prodotto**: `CLASSIFICAZIONE_OPERATIVA_`
- **Formato**: CSV

Il file di output contiene:
- criteri di classificazione;
- etichette operative;
- motivazioni quantitative;
- metriche di supporto serializzate.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento;
- timeframe;
- provenienza dai KPI.

Esempio:
CLASSIFICAZIONE_OPERATIVA_KPI_FDAX_15M.csv


---

## 04.04.5 Criteri di classificazione

Il modulo applica criteri quantitativi configurabili, tipicamente suddivisi in categorie:

### Liquidità
- volume medio;
- variabilità del volume;
- numerosità delle osservazioni.

### Volatilità
- deviazione standard dei rendimenti;
- ATR;
- ATR percentuale.

### Direzionalità
- pendenza del trend;
- coefficiente di determinazione (R²);
- rapporto movimento netto / range.

Ogni criterio produce:
- una **label operativa** (es. bassa, media, alta);
- una **motivazione quantitativa**.

---

## 04.04.6 Flusso operativo

1. Lettura del file `KPI_`.
2. Validazione delle colonne richieste.
3. Calcolo delle metriche di classificazione.
4. Applicazione delle soglie configurate.
5. Assegnazione delle etichette operative.
6. Serializzazione delle metriche di supporto.
7. Scrittura del file di classificazione operativa.

Il processo è deterministico e riproducibile.

---

## 04.04.7 Modalità di esecuzione

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
- selezione manuale del file KPI;
- stampa a video del riepilogo di classificazione.

---

## 04.04.8 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- presenza delle colonne KPI richieste;
- coerenza dei valori numerici;
- disponibilità di un numero sufficiente di osservazioni;
- validità delle soglie configurate.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file `CLASSIFICAZIONE_OPERATIVA_`.

---

## 04.04.9 Vincoli e limitazioni

Il modulo Classificazione Operativa:

- NON modifica i dati OHLCV;
- NON calcola KPI aggiuntivi;
- NON seleziona strategie;
- NON genera regole operative.

Il modulo produce esclusivamente una **descrizione del contesto**.

---

## 04.04.10 Output atteso

L’output principale del modulo è il file:

**`CLASSIFICAZIONE_OPERATIVA_*.csv`**

che rappresenta l’ingresso obbligatorio per:

**04.05 Strategy Mapping**
