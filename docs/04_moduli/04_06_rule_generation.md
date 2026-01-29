# 04.06 Rule Generation

## 04.06.1 Scopo

Il modulo **Rule Generation** ha lo scopo di **materializzare regole operative eseguibili**
a partire dal mapping strategico prodotto dal modulo Strategy Mapping.

Questo modulo:
- traduce strategie selezionate in **condizioni atomiche**;
- genera regole di **ENTRY**, **EXIT** e **filtri operativi**;
- produce un file di regole **direttamente utilizzabile** da `run_strategia`.

Il modulo NON applica le regole ai dati storici e NON calcola performance.

---

## 04.06.2 Ambito

Il modulo opera:
- **a valle** di **04.05 Strategy Mapping**;
- **a monte** di **04.07 Run Strategia**.

È responsabile esclusivamente della **costruzione formale delle regole**,
non della loro valutazione o esecuzione.

---

## 04.06.3 Input

### File in input

- **Prefisso atteso**: `STRATEGY_MAPPING_`
- **Formato**: CSV
- **Separatore**: `;`
- **Separatore decimale**: `,`

Il file di input contiene:
- strategie selezionate;
- contesto operativo;
- metadati necessari alla generazione delle regole.

Il file NON contiene dati OHLCV.

---

### Selezione file

#### Modalità interattiva
- Directory di default: `_data/Test Data`
- Filtro: file con prefisso `STRATEGY_MAPPING_`

L’utente seleziona il file di mapping strategico da processare.

#### Modalità pipeline
- Il file di input è determinato automaticamente dal flusso precedente.
- Nessuna interazione utente.

---

## 04.06.4 Output

### File prodotti

- **Prefisso prodotto**: `STRATEGIA_`
- **Formato**: CSV

Il file di output contiene:
- regole di ingresso (ENTRY);
- regole di uscita (EXIT);
- filtri di regime o contesto;
- parametri operativi normalizzati.

Il file prodotto è **l’unico input strategico** previsto per `run_strategia`.

---

### Naming convention

Il nome del file deve consentire di identificare:
- strumento;
- timeframe;
- provenienza dal mapping strategico.

Esempio:
STRATEGIA_FDAX_15M.csv


---

## 04.06.5 Flusso operativo

Il modulo esegue i seguenti passi:

1. Lettura del file di Strategy Mapping.
2. Validazione della struttura e dei campi.
3. Interpretazione delle strategie selezionate.
4. Generazione delle condizioni operative atomiche.
5. Normalizzazione degli operatori logici.
6. Costruzione delle regole ENTRY e EXIT.
7. Scrittura del file di regole strategiche.

Il processo è completamente deterministico.

---

## 04.06.6 Modalità di esecuzione

### Interfaccia CLI

Il modulo è invocato tramite comando: build-rules


L’esecuzione può avvenire:
- in modalità interattiva;
- come parte di una pipeline automatizzata.

---

### PIPELINE_MODE

Con `PIPELINE_MODE=1`:
- l’esecuzione è non interattiva;
- input e output sono determinati automaticamente;
- non viene richiesta alcuna selezione manuale.

Senza `PIPELINE_MODE`:
- viene richiesta la selezione del file di input;
- l’output è confermato dall’utente.

---

## 04.06.7 Validazioni e controlli

Il modulo esegue i seguenti controlli:

- presenza delle informazioni strategiche richieste;
- coerenza delle strategie selezionate;
- validità degli operatori logici;
- compatibilità delle condizioni generate.

In caso di errore:
- l’esecuzione viene interrotta;
- non viene prodotto alcun file `STRATEGIA_`.

---

## 04.06.8 Vincoli e limitazioni

Il modulo Rule Generation:

- NON accede ai dati OHLCV;
- NON valuta segnali o performance;
- NON modifica il mapping strategico in input;
- NON applica alcuna logica temporale.

Il modulo assume che il mapping strategico sia già coerente e validato.

---

## 04.06.9 Errori tipici e risoluzione

**Errore: mapping strategico non valido**
- Causa: file incompleto o incompatibile.
- Azione: verificare l’output di Strategy Mapping.

**Errore: regole non generabili**
- Causa: strategie prive di definizione operativa.
- Azione: verificare la configurazione delle strategie.

---

## 04.06.10 Output atteso

Il file prodotto da Rule Generation è destinato esclusivamente al modulo:

**04.07 Run Strategia**

Ogni utilizzo del file per scopi diversi è da considerarsi non supportato.
