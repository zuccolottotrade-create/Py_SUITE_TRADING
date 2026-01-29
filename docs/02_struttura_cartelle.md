# 02. Struttura delle cartelle e dei file

## 02.1 Root del progetto

La root del progetto **Py_SUITE_TRADING** contiene:
- i moduli operativi della suite;
- la documentazione tecnica;
- le directory di configurazione;
- le directory dati.

La struttura della root non è libera.  
L’aggiunta di nuove directory deve rispettare le convenzioni definite in questo documento.

---

## 02.2 Directory `_data`

La directory `_data` è il contenitore unico di tutti i dati utilizzati dalla suite.

All’interno di `_data` devono essere presenti esclusivamente:
- dati di input;
- dati intermedi;
- output finali prodotti dai moduli.

Non è consentito salvare dati al di fuori di `_data`.

---

## 02.3 Sottostruttura `_data/Test Data`

La directory `_data/Test Data` è utilizzata come area operativa standard per:

- test manuali;
- esecuzioni interattive;
- sviluppo e debug dei moduli.

Tutti i moduli che prevedono una selezione interattiva dei file devono puntare a questa directory come percorso di default.

---

## 02.4 Altre sottodirectory dati

Eventuali sottodirectory aggiuntive sotto `_data` possono essere utilizzate per:

- archiviazione storica;
- separazione per asset;
- separazione per timeframe.

Tali directory devono comunque rispettare le convenzioni di naming dei file.

---

## 02.5 Directory dei moduli

Ogni modulo della Py_SUITE_TRADING è contenuto in una directory dedicata, posizionata nella root del progetto.

Caratteristiche:
- una directory = un modulo logico;
- codice, launcher e configurazioni del modulo sono mantenuti insieme;
- non è previsto l’accesso diretto ai file di altri moduli.

---

## 02.6 Directory `docs`

La directory `docs` contiene esclusivamente documentazione tecnica in formato markdown.

Caratteristiche:
- numerazione coerente con la struttura del manuale operativo;
- un file = una sezione concettuale;
- nessun file di dati o codice all’interno.

La directory `docs` è la fonte ufficiale per la documentazione del progetto.

---

## 02.7 File di configurazione

I file di configurazione:
- sono mantenuti in directory dedicate;
- non devono essere mescolati ai dati di mercato;
- devono essere versionabili tramite Git.

I file Excel e CSV di configurazione non devono essere modificati automaticamente dai moduli.

---

## 02.8 Convenzioni di naming dei file

Tutti i file CSV operativi devono seguire convenzioni di naming esplicite.

Il nome del file deve consentire di identificare:
- lo stato del dato;
- lo strumento finanziario;
- il timeframe;
- eventuali varianti operative.

Esempio:
CLEAN_FDAX_15M.csv
CLASSIFICAZIONE_OPERATIVA_CLEAN_FDAX_15M.csv
STRATEGIA_CLASSIFICAZIONE_FDAX_15M.csv
REPORT_STRATEGIA_FDAX_15M.csv


---

## 02.9 Prefissi obbligatori

I prefissi identificano lo stato del file all’interno della pipeline.

Prefissi ammessi:
- `RAW_`
- `CLEAN_`
- `QC_`
- `CLASSIFICAZIONE_`
- `STRATEGIA_`
- `REPORT_`

L’utilizzo di prefissi non previsti è considerato un errore operativo.

---

## 02.10 Vincoli operativi

Sono vietate le seguenti pratiche:

- scrivere file di output fuori da `_data`;
- sovrascrivere file CSV esistenti senza cambio di prefisso;
- usare nomi di file ambigui o incompleti;
- condividere directory di dati tra moduli senza convenzioni esplicite.

Il rispetto di questi vincoli è essenziale per garantire ordine, tracciabilità e riproducibilità.
