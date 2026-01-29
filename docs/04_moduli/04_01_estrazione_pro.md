# 04.01 Estrazione dati (estrazione_pro)

## 04.01.1 Scopo

Il modulo **Estrazione dati (estrazione_pro)** ha lo scopo di **ottenere dati di mercato grezzi**
da fonti esterne e salvarli in formato strutturato per l’elaborazione successiva.

Il modulo:
- interroga una o più fonti dati (es. broker / data provider);
- normalizza il formato dei dati estratti;
- produce file CSV grezzi pronti per il controllo di coerenza.

Il modulo NON esegue controlli di qualità avanzati sui dati.

---

## 04.01.2 Ambito

Il modulo opera:
- come **primo step** della pipeline Py_SUITE_TRADING;
- a monte di **04.02 Controllo coerenza dati**.

È responsabile esclusivamente della **raccolta e serializzazione del dato di mercato**.

---

## 04.01.3 Input

### Parametri di input

Il modulo richiede tipicamente:
- strumento finanziario (symbol / contract);
- timeframe (es. 1m, 5m, 15m, 1h, 1d);
- intervallo temporale;
- eventuali parametri specifici della fonte dati.

I parametri possono essere forniti:
- tramite CLI;
- tramite configurazione;
- tramite interazione guidata.

---

### Fonti dati

Il modulo può interrogare:
- broker (es. Interactive Brokers);
- data provider esterni;
- archivi storici locali.

La fonte dati è astratta rispetto ai moduli successivi.

---

## 04.01.4 Output

### File prodotti

- **Prefisso prodotto**: `RAW_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`
- **Encoding**: UTF-8

Il file prodotto contiene:
- colonna temporale (timestamp);
- colonne OHLCV;
- eventuali metadati minimi.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento finanziario;
- timeframe;
- intervallo o variante di estrazione.

Esempio:
RAW_FDAX_15M.csv


---

## 04.01.5 Flusso operativo

Il modulo esegue i seguenti passi:

1. Inizializzazione della connessione alla fonte dati.
2. Validazione dei parametri di richiesta.
3. Richiesta dei dati storici.
4. Normalizzazione dei dati ricevuti.
5. Scrittura del file CSV grezzo (`RAW_`).

Il processo è sincrono e deterministico rispetto alla fonte dati.

---

## 04.01.6 Modalità di esecuzione

### Interfaccia CLI

Il modulo è invocabile:
- tramite runner dedicato;
- tramite menu della pipeline;
- tramite script `.command`.

L’esecuzione può avvenire:
- in modalità interattiva;
- come parte di una pipeline automatizzata.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- i parametri sono forniti automaticamente;
- nessuna interazione utente è richiesta;
- l’output è scritto nella directory standard `_data`.

Senza `PIPELINE_MODE`:
- l’utente fornisce o conferma i parametri di estrazione;
- l’output è confermato prima della scrittura.

---

## 04.01.7 Validazioni minime

Il modulo esegue esclusivamente validazioni minime:

- risposta non vuota dalla fonte dati;
- presenza delle colonne richieste;
- formati numerici coerenti.

Non vengono eseguiti:
- controlli su timestamp duplicati;
- controlli di coerenza OHLC;
- controlli di qualità avanzati.

Tali controlli sono demandati al modulo **04.02 Controllo coerenza dati**.

---

## 04.01.8 Errori tipici e risoluzione

**Errore: nessun dato restituito**
- Causa: parametri errati o finestra temporale vuota.
- Azione: verificare symbol, timeframe e date.

**Errore: connessione alla fonte dati**
- Causa: servizio non disponibile o credenziali errate.
- Azione: verificare la connessione e lo stato del provider.

---

## 04.01.9 Vincoli e limitazioni

Il modulo Estrazione dati:

- NON filtra dati anomali;
- NON corregge errori di mercato;
- NON calcola KPI;
- NON prende decisioni operative.

Il dato prodotto è considerato **grezzo** fino al superamento del controllo di coerenza.

---

## 04.01.10 Output atteso

L’output principale del modulo è il file:

**`RAW_*.csv`**

che rappresenta l’ingresso obbligatorio per:

**04.02 Controllo coerenza dati**
