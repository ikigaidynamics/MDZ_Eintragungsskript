import streamlit as st
import pandas as pd
from collections import Counter
import json
from datetime import datetime
import io

st.set_page_config(page_title="MDZ Teilnehmer-Auswertung", layout="wide")

st.title("📊 MDZ Teilnehmer-Auswertung")
st.write("CSV hochladen, Teilnehmende markieren, Zahlen automatisch berechnen.")

# ==============================
# CSV UPLOAD
# ==============================

uploaded_file = st.file_uploader(
    "CSV-Datei hochladen (nur Unternehmen, eine Person pro Zeile)",
    type=["csv"]
)

if uploaded_file is None:
    st.info("Bitte lade eine CSV-Datei hoch.")
    st.stop()

# CSV lesen - verschiedene Encodings versuchen
encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
df = None

for encoding in encodings:
    try:
        df = pd.read_csv(uploaded_file, sep=";", encoding=encoding)
        break
    except:
        continue

if df is None:
    st.error("Konnte CSV-Datei nicht lesen. Bitte prüfe das Dateiformat.")
    st.stop()

# Spalten normalisieren - alle möglichen Varianten von "Firmengröße"
def normalize_columns(columns):
    normalized = []
    for col in columns:
        # BOM entfernen
        col = col.replace("ï»¿", "").replace("\ufeff", "")
        
        # Firmengröße-Varianten normalisieren
        if "firmen" in col.lower() and ("gr" in col.lower() or "size" in col.lower()):
            col = "Firmengröße"
        
        normalized.append(col)
    return normalized

df.columns = normalize_columns(df.columns)

# Debug: Spalten anzeigen
st.write("Verfügbare Spalten:", list(df.columns))

# Erwartete Spalten - flexibler prüfen
required_base = ["Unternehmen"]
firmengröße_found = any("firmengröße" in col.lower() or "firmen" in col.lower() and "gr" in col.lower() for col in df.columns)

if "Unternehmen" not in df.columns:
    st.error("Spalte 'Unternehmen' nicht gefunden!")
    st.stop()

if not firmengröße_found:
    st.warning("Keine Firmengröße-Spalte gefunden. App funktioniert trotzdem.")

# Daten säubern
df["Unternehmen"] = df["Unternehmen"].astype(str).str.strip()

# Unternehmensnamen normalisieren (für konsistente Zählung)
def normalize_company_name(name):
    """Normalisiert Unternehmensnamen für konsistente Gruppierung"""
    if pd.isna(name):
        return ""
    return str(name).strip().lower()

# Funktion zum Normalisieren der bearbeiteten Daten
def process_edited_data(edited_df):
    """Verarbeitet die bearbeiteten Daten und normalisiert Unternehmensnamen"""
    processed_df = edited_df.copy()
    processed_df["Unternehmen"] = processed_df["Unternehmen"].astype(str).str.strip()
    return processed_df

# ==============================
# TEILNAHME-MARKIERUNG
# ==============================

st.subheader("✅ Teilnahme markieren")

if "teilgenommen" not in df.columns:
    df["teilgenommen"] = True  # Default: teilgenommen

if "ist_unternehmen" not in df.columns:
    df["ist_unternehmen"] = True  # Default: Unternehmen

# Institution type columns
institution_types = ["kammer", "verband_verein", "wirtschaftsfoerderung", "hochschule", "mittelstand_digital", "foerderinitiative", "unklar"]
for inst_type in institution_types:
    if inst_type not in df.columns:
        df[inst_type] = False

# Session State für zu löschende Zeilen
if "rows_to_delete" not in st.session_state:
    st.session_state.rows_to_delete = []

# Zeilen-Auswahl für Löschung
st.write("**Zeile zum Löschen auswählen:**")
if len(df) > 0:
    selected_row = st.selectbox(
        "Welche Zeile soll gelöscht werden?",
        options=[None] + list(range(len(df))),
        format_func=lambda x: "Keine Auswahl" if x is None else f"Zeile {x+1}: {df.iloc[x]['Unternehmen']}"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Ausgewählte Zeile löschen", type="secondary") and selected_row is not None:
            st.session_state.rows_to_delete.append(selected_row)
            st.success(f"Zeile {selected_row+1} wird gelöscht!")
    
    with col2:
        if st.button("↺ Löschungen rückgängig", type="secondary"):
            st.session_state.rows_to_delete = []
            st.success("Alle Löschungen zurückgesetzt!")

# DataFrame nach Löschungen filtern
working_df = df.drop(index=st.session_state.rows_to_delete).reset_index(drop=True)

# Zeilennummer als erste Spalte hinzufügen
working_df_with_index = working_df.copy()
working_df_with_index.insert(0, "Nr.", range(1, len(working_df_with_index) + 1))

if len(st.session_state.rows_to_delete) > 0:
    st.warning(f"⚠️ {len(st.session_state.rows_to_delete)} Zeile(n) werden gelöscht: {[i+1 for i in st.session_state.rows_to_delete]}")

st.write("**Daten bearbeiten:**")

# Create column configuration
column_config = {
    "Nr.": st.column_config.NumberColumn(
        "Nr.",
        help="Zeilennummer",
        disabled=True,
        width="small"
    ),
    "teilgenommen": st.column_config.CheckboxColumn(
        "Hat teilgenommen?",
        help="Häkchen entfernen = nur angemeldet"
    ),
    "ist_unternehmen": st.column_config.CheckboxColumn(
        "Ist Unternehmen?",
        help="Häkchen entfernen = andere Institution"
    ),
    "Unternehmen": st.column_config.TextColumn(
        "Unternehmen",
        help="Unternehmen/Institution bearbeitbar"
    )
}

# Add institution type columns to config
institution_labels = {
    "kammer": "Kammer",
    "verband_verein": "Verband/Verein", 
    "wirtschaftsfoerderung": "Wirtschaftsförderung",
    "hochschule": "Hochschule/Bildungseinrichtung",
    "mittelstand_digital": "Mittelstand-Digital",
    "foerderinitiative": "Förderinitiative",
    "unklar": "Unklar"
}

for inst_type, label in institution_labels.items():
    column_config[inst_type] = st.column_config.CheckboxColumn(
        label,
        help=f"Nur auswählbar wenn nicht 'Ist Unternehmen'"
    )

# Create a callback to handle the conditional logic
def handle_institution_selection(df_input):
    df_result = df_input.copy()
    
    # For each row, if ist_unternehmen is True, set all institution types to False
    for idx, row in df_result.iterrows():
        if row['ist_unternehmen']:
            for inst_type in institution_types:
                df_result.at[idx, inst_type] = False
        else:
            # Ensure only one institution type is selected
            selected_types = [inst_type for inst_type in institution_types if row[inst_type]]
            if len(selected_types) > 1:
                # Keep only the first selected type
                for inst_type in institution_types:
                    df_result.at[idx, inst_type] = (inst_type == selected_types[0])
    
    return df_result

edited_df_with_index = st.data_editor(
    working_df_with_index,
    use_container_width=True,
    num_rows="dynamic",
    column_config=column_config,
    disabled=["Nr."] + (["Firmengröße"] if "Firmengröße" in working_df_with_index.columns else [])
)

# Apply conditional logic
edited_df_with_index = handle_institution_selection(edited_df_with_index)

# Zeilennummer wieder entfernen für weitere Verarbeitung
edited_df = edited_df_with_index.drop(columns=["Nr."])

# ==============================
# FILTER
# ==============================

# Bearbeitete Daten verarbeiten
processed_df = process_edited_data(edited_df)

teilgenommen_df = processed_df[processed_df["teilgenommen"]]
angemeldet_df = processed_df[~processed_df["teilgenommen"]]

# Nach Typ filtern
teilgenommen_unternehmen = teilgenommen_df[teilgenommen_df["ist_unternehmen"]]
angemeldet_unternehmen = angemeldet_df[angemeldet_df["ist_unternehmen"]]

# Institution type filtering for participants
teilgenommen_by_type = {}
angemeldet_by_type = {}

for inst_type in institution_types:
    teilgenommen_by_type[inst_type] = teilgenommen_df[teilgenommen_df[inst_type]]
    angemeldet_by_type[inst_type] = angemeldet_df[angemeldet_df[inst_type]]

# Backward compatibility - all non-company institutions
teilgenommen_institutionen = teilgenommen_df[~teilgenommen_df["ist_unternehmen"]]
angemeldet_institutionen = angemeldet_df[~angemeldet_df["ist_unternehmen"]]

# ==============================
# ZÄHLLOGIK
# ==============================

def personen(df):
    return len(df)

def unternehmen(df):
    return df["Unternehmen"].nunique()

def personen_pro_unternehmen(df):
    return df.groupby("Unternehmen").size().sort_values(ascending=False)

def bucket_auswertung(counts):
    buckets = Counter()
    for n in counts:
        if n == 1:
            buckets["1 Person"] += 1
        elif n == 2:
            buckets["2 Personen"] += 1
        else:
            buckets["3+ Personen"] += 1
    return buckets

def firmengröße_auswertung(df):
    """Auswertung nach Unternehmensgröße-Kategorien"""
    if "Firmengröße" not in df.columns or len(df) == 0:
        return {}
    
    kategorien = {
        "1 bis 9 Mitarbeiter": 0,
        "10 bis 49 Mitarbeiter": 0, 
        "50 bis 249 Mitarbeiter": 0,
        "bis 500 Mitarbeiter": 0,
        "mehr als 500 Mitarbeiter": 0
    }
    
    for größe in df["Firmengröße"]:
        größe_str = str(größe).strip()
        if "1 bis 9" in größe_str:
            kategorien["1 bis 9 Mitarbeiter"] += 1
        elif "10 bis 49" in größe_str:
            kategorien["10 bis 49 Mitarbeiter"] += 1
        elif "50 bis 249" in größe_str:
            kategorien["50 bis 249 Mitarbeiter"] += 1
        elif "bis 500" in größe_str or ("500" in größe_str and "mehr" not in größe_str):
            kategorien["bis 500 Mitarbeiter"] += 1
        elif "mehr als 500" in größe_str or "500+" in größe_str:
            kategorien["mehr als 500 Mitarbeiter"] += 1
    
    return kategorien

# ==============================
# ERGEBNISSE
# ==============================

st.subheader("📈 Ergebnisse")

# Gesamtübersicht
col1, col2 = st.columns(2)

with col1:
    st.write("**Teilgenommen:**")
    st.metric("👤 Personen gesamt", personen(teilgenommen_df))
    st.metric("🏢 Unternehmen", unternehmen(teilgenommen_unternehmen))
    st.metric("👤 Personen aus Unternehmen", personen(teilgenommen_unternehmen))

with col2:
    st.write("**Nur angemeldet:**")
    st.metric("👤 Personen gesamt", personen(angemeldet_df))
    st.metric("🏢 Unternehmen", unternehmen(angemeldet_unternehmen))
    st.metric("👤 Personen aus Unternehmen", personen(angemeldet_unternehmen))

# Institutionen-Aufschlüsselung
st.write("---")
st.subheader("🏛️ Aufschlüsselung nach Institutionstyp")

col1, col2 = st.columns(2)

with col1:
    st.write("**Teilgenommen:**")
    for inst_type, label in institution_labels.items():
        count_persons = personen(teilgenommen_by_type[inst_type])
        count_institutions = unternehmen(teilgenommen_by_type[inst_type])
        if count_persons > 0:
            st.write(f"**{label}:** {count_persons} Personen aus {count_institutions} Institutionen")

with col2:
    st.write("**Nur angemeldet:**")
    for inst_type, label in institution_labels.items():
        count_persons = personen(angemeldet_by_type[inst_type])
        count_institutions = unternehmen(angemeldet_by_type[inst_type])
        if count_persons > 0:
            st.write(f"**{label}:** {count_persons} Personen aus {count_institutions} Institutionen")

# ==============================
# MEHRPERSONEN-AUSWERTUNG
# ==============================

st.subheader("👥 Mehrere Personen pro Unternehmen/Institution")

# Nur Unternehmen
counts_unternehmen = personen_pro_unternehmen(teilgenommen_unternehmen)
buckets_unternehmen = bucket_auswertung(counts_unternehmen)

st.write("**Unternehmen:**")
for k, v in buckets_unternehmen.items():
    st.write(f"**{k}:** {v}")

mehrfach_unternehmen = counts_unternehmen[counts_unternehmen > 1]

if not mehrfach_unternehmen.empty:
    st.markdown("**Unternehmen mit mehreren teilnehmenden Personen:**")
    st.dataframe(mehrfach_unternehmen.rename("Anzahl Personen"))
else:
    st.success("Alle Unternehmen waren nur mit einer Person vertreten.")

# Andere Institutionen
if len(teilgenommen_institutionen) > 0:
    counts_institutionen = personen_pro_unternehmen(teilgenommen_institutionen)
    buckets_institutionen = bucket_auswertung(counts_institutionen)
    
    st.write("**Andere Institutionen:**")
    for k, v in buckets_institutionen.items():
        st.write(f"**{k}:** {v}")
    
    mehrfach_institutionen = counts_institutionen[counts_institutionen > 1]
    
    if not mehrfach_institutionen.empty:
        st.markdown("**Andere Institutionen mit mehreren teilnehmenden Personen:**")
        st.dataframe(mehrfach_institutionen.rename("Anzahl Personen"))

# ==============================
# FIRMENGRÖSSE-AUSWERTUNG  
# ==============================

st.write("---")
st.subheader("📊 Aufschlüsselung nach Unternehmensgröße")

if "Firmengröße" in df.columns and len(teilgenommen_unternehmen) > 0:
    # Personen nach Firmengröße
    personen_nach_größe_teilgenommen = firmengröße_auswertung(teilgenommen_unternehmen)
    personen_nach_größe_angemeldet = firmengröße_auswertung(angemeldet_unternehmen)
    
    # Unternehmen nach Firmengröße 
    unternehmen_nach_größe_teilgenommen = {}
    unternehmen_nach_größe_angemeldet = {}
    
    for kategorie in personen_nach_größe_teilgenommen.keys():
        # Teilgenommen
        unternehmen_dieser_größe_teil = teilgenommen_unternehmen[
            teilgenommen_unternehmen["Firmengröße"].str.contains(
                kategorie.replace(" Mitarbeiter", ""), na=False
            )
        ]
        unternehmen_nach_größe_teilgenommen[kategorie] = unternehmen(unternehmen_dieser_größe_teil)
        
        # Angemeldet
        unternehmen_dieser_größe_ang = angemeldet_unternehmen[
            angemeldet_unternehmen["Firmengröße"].str.contains(
                kategorie.replace(" Mitarbeiter", ""), na=False
            )
        ]
        unternehmen_nach_größe_angemeldet[kategorie] = unternehmen(unternehmen_dieser_größe_ang)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Teilgenommen:**")
        for kategorie in personen_nach_größe_teilgenommen.keys():
            anzahl_personen = personen_nach_größe_teilgenommen[kategorie]
            anzahl_unternehmen = unternehmen_nach_größe_teilgenommen[kategorie]
            if anzahl_personen > 0:
                st.write(f"**{kategorie}:** {anzahl_personen} Personen aus {anzahl_unternehmen} Unternehmen")
    
    with col2:
        st.write("**Nur angemeldet:**")
        for kategorie in personen_nach_größe_angemeldet.keys():
            anzahl_personen = personen_nach_größe_angemeldet[kategorie]
            anzahl_unternehmen = unternehmen_nach_größe_angemeldet[kategorie]
            if anzahl_personen > 0:
                st.write(f"**{kategorie}:** {anzahl_personen} Personen aus {anzahl_unternehmen} Unternehmen")
else:
    st.info("Keine Unternehmensgröße-Daten verfügbar oder keine teilnehmenden Unternehmen.")

# ==============================
# TEXTBAUSTEIN
# ==============================

st.subheader("📝 Textbaustein (z. B. für MDZ / Verwendungsnachweis)")

text_parts = []

# Gesamtanmeldungen
gesamt_angemeldet = personen(processed_df)
gesamt_teilgenommen = personen(teilgenommen_df)

text_parts.append(f"Für die Veranstaltung haben sich insgesamt {gesamt_angemeldet} Personen angemeldet.")
text_parts.append(f"Davon nahmen {gesamt_teilgenommen} Personen teil.")

if unternehmen(teilgenommen_unternehmen) > 0:
    text_parts.append(f"Von den Teilnehmenden kamen {personen(teilgenommen_unternehmen)} Personen aus {unternehmen(teilgenommen_unternehmen)} Unternehmen.")
    
    if len(mehrfach_unternehmen) > 0:
        text_parts.append(f"{len(mehrfach_unternehmen)} Unternehmen waren mit mehreren Personen vertreten.")

# Add details for each institution type
institution_details = []
for inst_type, label in institution_labels.items():
    count_persons = personen(teilgenommen_by_type[inst_type])
    count_institutions = unternehmen(teilgenommen_by_type[inst_type])
    if count_persons > 0:
        if count_institutions == 1:
            institution_details.append(f"{count_persons} Personen aus {count_institutions} {label}")
        else:
            institution_details.append(f"{count_persons} Personen aus {count_institutions} {label}")

if institution_details:
    if len(institution_details) == 1:
        text_parts.append(f"Zusätzlich nahmen {institution_details[0]} teil.")
    else:
        text_parts.append(f"Zusätzlich nahmen teil: {', '.join(institution_details[:-1])} und {institution_details[-1]}.")

text = " ".join(text_parts)

st.text_area("Automatisch generierter Text", text, height=120)

# ==============================
# EXPORT-FUNKTIONEN
# ==============================

st.subheader("💾 Daten exportieren")

col1, col2, col3 = st.columns(3)

# CSV Export der bearbeiteten Tabelle
with col1:
    st.write("**Bearbeitete Tabelle (CSV):**")
    csv_data = processed_df.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        label="📋 Tabelle als CSV",
        data=csv_data,
        file_name=f"MDZ_Teilnehmer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# Excel Export mit mehreren Sheets
with col2:
    st.write("**Vollständige Auswertung (Excel):**")
    
    # Excel-Daten vorbereiten
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: Bearbeitete Rohdaten
        processed_df.to_excel(writer, sheet_name='Teilnehmerdaten', index=False)
        
        # Sheet 2: Ergebnisse zusammenfassen
        results_data = []
        
        # Gesamtzahlen
        results_data.append(['Kategorie', 'Teilgenommen Personen', 'Teilgenommen Institutionen', 'Angemeldet Personen', 'Angemeldet Institutionen'])
        results_data.append(['Unternehmen', personen(teilgenommen_unternehmen), unternehmen(teilgenommen_unternehmen), personen(angemeldet_unternehmen), unternehmen(angemeldet_unternehmen)])
        
        # Institutionstypen
        for inst_type, label in institution_labels.items():
            teil_pers = personen(teilgenommen_by_type[inst_type])
            teil_inst = unternehmen(teilgenommen_by_type[inst_type])
            ang_pers = personen(angemeldet_by_type[inst_type])
            ang_inst = unternehmen(angemeldet_by_type[inst_type])
            if teil_pers > 0 or ang_pers > 0:
                results_data.append([label, teil_pers, teil_inst, ang_pers, ang_inst])
        
        results_df = pd.DataFrame(results_data[1:], columns=results_data[0])
        results_df.to_excel(writer, sheet_name='Auswertung', index=False)
        
        # Sheet 3: Unternehmensgröße (falls verfügbar)
        if "Firmengröße" in df.columns and len(teilgenommen_unternehmen) > 0:
            groesse_data = []
            groesse_data.append(['Unternehmensgröße', 'Teilgenommen Personen', 'Teilgenommen Unternehmen', 'Angemeldet Personen', 'Angemeldet Unternehmen'])
            
            personen_nach_größe_teil = firmengröße_auswertung(teilgenommen_unternehmen)
            personen_nach_größe_ang = firmengröße_auswertung(angemeldet_unternehmen)
            
            for kategorie in personen_nach_größe_teil.keys():
                teil_pers = personen_nach_größe_teil[kategorie]
                ang_pers = personen_nach_größe_ang.get(kategorie, 0)
                
                # Unternehmen zählen
                teil_unt = len(teilgenommen_unternehmen[teilgenommen_unternehmen["Firmengröße"].str.contains(kategorie.replace(" Mitarbeiter", ""), na=False)].groupby("Unternehmen"))
                ang_unt = len(angemeldet_unternehmen[angemeldet_unternehmen["Firmengröße"].str.contains(kategorie.replace(" Mitarbeiter", ""), na=False)].groupby("Unternehmen"))
                
                if teil_pers > 0 or ang_pers > 0:
                    groesse_data.append([kategorie, teil_pers, teil_unt, ang_pers, ang_unt])
            
            groesse_df = pd.DataFrame(groesse_data[1:], columns=groesse_data[0])
            groesse_df.to_excel(writer, sheet_name='Unternehmensgröße', index=False)
    
    excel_data = output.getvalue()
    st.download_button(
        label="📊 Auswertung als Excel",
        data=excel_data,
        file_name=f"MDZ_Auswertung_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# JSON Export für maschinelle Weiterverarbeitung
with col3:
    st.write("**Daten für Software (JSON):**")
    
    json_data = {
        "export_timestamp": datetime.now().isoformat(),
        "gesamtzahlen": {
            "angemeldet_gesamt": personen(processed_df),
            "teilgenommen_gesamt": personen(teilgenommen_df),
            "unternehmen_teilgenommen": unternehmen(teilgenommen_unternehmen),
            "personen_aus_unternehmen_teilgenommen": personen(teilgenommen_unternehmen)
        },
        "institutionstypen": {},
        "unternehmensgröße": {},
        "generierter_text": text,
        "rohdaten": processed_df.to_dict('records')
    }
    
    # Institutionstypen
    for inst_type, label in institution_labels.items():
        json_data["institutionstypen"][label] = {
            "teilgenommen_personen": personen(teilgenommen_by_type[inst_type]),
            "teilgenommen_institutionen": unternehmen(teilgenommen_by_type[inst_type]),
            "angemeldet_personen": personen(angemeldet_by_type[inst_type]),
            "angemeldet_institutionen": unternehmen(angemeldet_by_type[inst_type])
        }
    
    # Unternehmensgröße
    if "Firmengröße" in df.columns:
        personen_nach_größe_teil = firmengröße_auswertung(teilgenommen_unternehmen)
        personen_nach_größe_ang = firmengröße_auswertung(angemeldet_unternehmen)
        
        for kategorie in personen_nach_größe_teil.keys():
            json_data["unternehmensgröße"][kategorie] = {
                "teilgenommen_personen": personen_nach_größe_teil[kategorie],
                "angemeldet_personen": personen_nach_größe_ang.get(kategorie, 0)
            }
    
    json_string = json.dumps(json_data, indent=2, ensure_ascii=False)
    st.download_button(
        label="🔧 Daten als JSON",
        data=json_string,
        file_name=f"MDZ_Daten_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

# Textbaustein als separate Datei
st.write("---")
st.write("**Textbaustein separat:**")
st.download_button(
    label="📝 Textbaustein als TXT",
    data=text,
    file_name=f"MDZ_Textbaustein_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
    mime="text/plain"
)
