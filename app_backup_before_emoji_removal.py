import streamlit as st
import pandas as pd
from collections import Counter
import json
from datetime import datetime
import io

st.set_page_config(page_title="MDZ Teilnehmer-Auswertung", layout="wide")

st.title("MDZ Teilnehmer-Auswertung")
st.write("CSV hochladen, Teilnehmende markieren, Zahlen automatisch berechnen.")

# ==============================
# BEDIENUNGSANLEITUNG
# ==============================

with st.expander("Bedienungsanleitung", expanded=False):
    st.markdown("""
    ### Wie verwenden Sie diese Anwendung?
    
    **1. CSV-Datei vorbereiten:**
    - Spalte "Unternehmen" (erforderlich)
    - Spalte "Firmengröße" (optional, für Größenauswertung)
    - Eine Zeile = eine Person
    
    **2. Datei hochladen:**
    - Neue Rohdaten: Standard-Einstellungen werden angewandt
    - Bereits bearbeitete Datei: Ihre Markierungen werden wiederhergestellt
    
    **3. Daten bearbeiten:**
    - **Hat teilgenommen**: Nur ankreuzen für tatsächliche Teilnehmer
    - **Ist Unternehmen**: Ankreuzen für Unternehmen, nicht ankreuzen für andere Institutionen
    - **Institutionstyp**: Nur auswählen wenn NICHT Unternehmen (Kammer, Verband, etc.)
    - **WICHTIG**: Institutionen mit mehreren Vertretern müssen **exakt gleich benannt** sein!
    
    **4. Qualitätskontrolle:**
    - Prüfen Sie Unternehmensnamen auf Konsistenz
    - Achten Sie auf korrekte Kategorisierung (Unternehmen vs. Institution)
    - Kontrollieren Sie die Teilnahme-Markierungen
    
    **5. Auswertung & Export:**
    - Automatische Berechnung aller Kennzahlen
    - Export als CSV, Excel oder JSON
    - Textbaustein für Berichte
    """)
    
st.write("---")

# ==============================
# CSV UPLOAD
# ==============================

uploaded_file = st.file_uploader(
    "CSV-Datei hochladen (Rohdaten oder bereits bearbeitete Datei)",
    type=["csv"],
    help="Sie können sowohl neue Rohdaten als auch bereits bearbeitete CSV-Dateien (mit gespeicherten Einstellungen) hochladen."
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

# Institution type columns definieren (für Prüfung)
institution_types = ["kammer", "verband_verein", "wirtschaftsfoerderung", "hochschule", "mittelstand_digital", "foerderinitiative", "unklar"]

# Prüfen, ob es sich um eine bereits bearbeitete Datei handelt
has_checkbox_columns = any(col in df.columns for col in ["teilgenommen", "ist_unternehmen"] + institution_types)
if has_checkbox_columns:
    st.success("Bereits bearbeitete Datei erkannt - Einstellungen werden geladen!")
else:
    st.info("Rohdatei erkannt - Standard-Einstellungen werden angewandt.")

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
else:
    # Importierte Checkbox-Werte richtig interpretieren
    df["teilgenommen"] = df["teilgenommen"].astype(str).str.lower().isin(['true', '1', 'yes', 'ja'])

if "ist_unternehmen" not in df.columns:
    df["ist_unternehmen"] = True  # Default: Unternehmen
else:
    # Importierte Checkbox-Werte richtig interpretieren
    df["ist_unternehmen"] = df["ist_unternehmen"].astype(str).str.lower().isin(['true', '1', 'yes', 'ja'])

# Institution type columns (bereits oben definiert)
for inst_type in institution_types:
    if inst_type not in df.columns:
        df[inst_type] = False
    else:
        # Importierte Checkbox-Werte richtig interpretieren
        df[inst_type] = df[inst_type].astype(str).str.lower().isin(['true', '1', 'yes', 'ja'])

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

# Warnung für Namenskonsistenz
st.info("💡 **Tipp**: Achten Sie darauf, dass Unternehmen/Institutionen mit mehreren Vertretern exakt gleich benannt sind (z.B. 'EMIS GmbH' nicht 'EMIS' und 'EMIS GmbH').")

st.write("**Daten bearbeiten:**")

# Sortier-Option
sort_options = ["Ursprüngliche Reihenfolge", "Unternehmen (A-Z)", "Unternehmen (Z-A)"]
if "Firmengröße" in working_df_with_index.columns:
    sort_options.extend(["Firmengröße (Klein → Groß)", "Firmengröße (Groß → Klein)"])

sort_option = st.selectbox(
    "Tabelle sortieren nach:",
    options=sort_options,
    help="Wählen Sie, wie die Tabelle sortiert werden soll"
)

# Tabelle sortieren
if sort_option == "Unternehmen (A-Z)":
    working_df_with_index = working_df_with_index.sort_values("Unternehmen", key=lambda x: x.str.lower(), ascending=True).reset_index(drop=True)
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Unternehmen (Z-A)":
    working_df_with_index = working_df_with_index.sort_values("Unternehmen", key=lambda x: x.str.lower(), ascending=False).reset_index(drop=True) 
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Firmengröße (Klein → Groß)" and "Firmengröße" in working_df_with_index.columns:
    # Größenordnung definieren
    size_order = {
        "1 bis 9 Mitarbeiter": 1,
        "10 bis 49 Mitarbeiter": 2,
        "50 bis 249 Mitarbeiter": 3,
        "bis 500 Mitarbeiter": 4,
        "mehr als 500 Mitarbeiter": 5
    }
    working_df_with_index["_sort_key"] = working_df_with_index["Firmengröße"].map(lambda x: size_order.get(str(x).strip(), 99))
    working_df_with_index = working_df_with_index.sort_values("_sort_key", ascending=True).reset_index(drop=True)
    working_df_with_index = working_df_with_index.drop(columns=["_sort_key"])
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Firmengröße (Groß → Klein)" and "Firmengröße" in working_df_with_index.columns:
    # Größenordnung definieren
    size_order = {
        "1 bis 9 Mitarbeiter": 1,
        "10 bis 49 Mitarbeiter": 2,
        "50 bis 249 Mitarbeiter": 3,
        "bis 500 Mitarbeiter": 4,
        "mehr als 500 Mitarbeiter": 5
    }
    working_df_with_index["_sort_key"] = working_df_with_index["Firmengröße"].map(lambda x: size_order.get(str(x).strip(), 99))
    working_df_with_index = working_df_with_index.sort_values("_sort_key", ascending=False).reset_index(drop=True)
    working_df_with_index = working_df_with_index.drop(columns=["_sort_key"])
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)

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

# Detaillierte Aufschlüsselung
st.write("---")
st.subheader("🏛️ Detaillierte Aufschlüsselung nach Institutionstyp")

col1, col2 = st.columns(2)

with col1:
    st.write("**Teilgenommen:**")
    for inst_type, label in institution_labels.items():
        count_persons = personen(teilgenommen_by_type[inst_type])
        count_institutions = unternehmen(teilgenommen_by_type[inst_type])
        if count_persons > 0:
            st.write(f"**{label}:** {count_persons} Personen aus {count_institutions} Institutionen")
            
            # Detailaufschlüsselung: Welche Institutionen mit wie vielen Personen
            if len(teilgenommen_by_type[inst_type]) > 0:
                institution_breakdown = teilgenommen_by_type[inst_type].groupby("Unternehmen").size().sort_values(ascending=False)
                if len(institution_breakdown) > 1:  # Nur anzeigen wenn mehr als eine Institution
                    st.write("   └─ Details:")
                    for institution_name, person_count in institution_breakdown.items():
                        st.write(f"     • {institution_name}: {person_count} Person(en)")

with col2:
    st.write("**Nur angemeldet:**")
    for inst_type, label in institution_labels.items():
        count_persons = personen(angemeldet_by_type[inst_type])
        count_institutions = unternehmen(angemeldet_by_type[inst_type])
        if count_persons > 0:
            st.write(f"**{label}:** {count_persons} Personen aus {count_institutions} Institutionen")
            
            # Detailaufschlüsselung: Welche Institutionen mit wie vielen Personen
            if len(angemeldet_by_type[inst_type]) > 0:
                institution_breakdown = angemeldet_by_type[inst_type].groupby("Unternehmen").size().sort_values(ascending=False)
                if len(institution_breakdown) > 1:  # Nur anzeigen wenn mehr als eine Institution
                    st.write("   └─ Details:")
                    for institution_name, person_count in institution_breakdown.items():
                        st.write(f"     • {institution_name}: {person_count} Person(en)")

# Aggregierte Zusammenfassung
st.write("---")
st.subheader("📊 Aggregierte Zusammenfassung")

total_angemeldet = personen(processed_df)
total_teilgenommen = personen(teilgenommen_df)
total_nicht_teilgenommen = total_angemeldet - total_teilgenommen

unternehmen_angemeldet = unternehmen(processed_df[processed_df["ist_unternehmen"]])
unternehmen_teilgenommen = unternehmen(teilgenommen_unternehmen)

# Korrekte Berechnung: Unternehmen die angemeldet sind ABER nicht teilgenommen haben
angemeldete_unternehmen = processed_df[processed_df["ist_unternehmen"]]
unternehmen_mit_teilnahme = set(teilgenommen_unternehmen["Unternehmen"].unique())
alle_angemeldeten_unternehmen = set(angemeldete_unternehmen["Unternehmen"].unique())
unternehmen_ohne_teilnahme = alle_angemeldeten_unternehmen - unternehmen_mit_teilnahme
unternehmen_nicht_teilgenommen = len(unternehmen_ohne_teilnahme)

institutionen_angemeldet = unternehmen(processed_df[~processed_df["ist_unternehmen"]])
institutionen_teilgenommen = unternehmen(teilgenommen_df[~teilgenommen_df["ist_unternehmen"]])

# Korrekte Berechnung: Institutionen die angemeldet sind ABER nicht teilgenommen haben
angemeldete_institutionen = processed_df[~processed_df["ist_unternehmen"]]
institutionen_mit_teilnahme = set(teilgenommen_df[~teilgenommen_df["ist_unternehmen"]]["Unternehmen"].unique())
alle_angemeldeten_institutionen = set(angemeldete_institutionen["Unternehmen"].unique())
institutionen_ohne_teilnahme = alle_angemeldeten_institutionen - institutionen_mit_teilnahme
institutionen_nicht_teilgenommen = len(institutionen_ohne_teilnahme)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("👥 Personen gesamt", total_angemeldet)
    st.metric("🏢 Unternehmen gesamt", unternehmen_angemeldet)
    st.metric("🏛️ Institutionen gesamt", institutionen_angemeldet)

with col2:
    st.metric("✅ Personen teilgenommen", total_teilgenommen)
    st.metric("✅ Unternehmen teilgenommen", unternehmen_teilgenommen)
    st.metric("✅ Institutionen teilgenommen", institutionen_teilgenommen)

with col3:
    st.metric("❌ Personen nicht teilgenommen", total_nicht_teilgenommen)
    st.metric("❌ Unternehmen nicht teilgenommen", unternehmen_nicht_teilgenommen)
    st.metric("❌ Institutionen nicht teilgenommen", institutionen_nicht_teilgenommen)

# Spezielle Kategorie "Unklar" hervorheben
unklar_personen_teilgenommen = personen(teilgenommen_by_type["unklar"])
unklar_personen_angemeldet = personen(processed_df[processed_df["unklar"]])
unklar_institutionen_teilgenommen = unternehmen(teilgenommen_by_type["unklar"])
unklar_institutionen_angemeldet = unternehmen(processed_df[processed_df["unklar"]])

if unklar_personen_angemeldet > 0:
    st.write("---")
    st.subheader("❓ Kategorie 'Unklar'")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("👤 Personen 'Unklar' (angemeldet)", unklar_personen_angemeldet)
        st.metric("🏛️ Institutionen 'Unklar' (angemeldet)", unklar_institutionen_angemeldet)
    
    with col2:
        st.metric("👤 Personen 'Unklar' (teilgenommen)", unklar_personen_teilgenommen)
        st.metric("🏛️ Institutionen 'Unklar' (teilgenommen)", unklar_institutionen_teilgenommen)
    
    st.warning(f"⚠️ **Auswirkung auf Statistiken**: {unklar_personen_angemeldet} Personen aus {unklar_institutionen_angemeldet} " +
               f"Institutionen sind als 'Unklar' kategorisiert. Diese werden NICHT zu den Unternehmenszahlen " +
               f"hinzugezählt, sondern separat als Institutionen vom Typ 'Unklar' behandelt. " +
               f"Sie beeinflussen somit die Gesamtstatistik der Institutionen, nicht der Unternehmen.")
    
    if unklar_personen_angemeldet > 0:
        st.info("💡 **Tipp**: Prüfen Sie die als 'Unklar' markierten Einträge und kategorisieren Sie diese " +
                "korrekt als Unternehmen oder spezifischen Institutionstyp, um präzisere Statistiken zu erhalten.")

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
# BESUCHERKENNZAHLEN / REICHWEITE TABELLE
# ==============================

st.subheader("📋 Besucherkennzahlen / Reichweite")
st.write("**Geschätzte Besucherkennzahlen**")

def map_company_size_to_category(size_str):
    """Mappt Firmengröße zu den gewünschten Kategorien"""
    if pd.isna(size_str):
        return "Unbekannt"
    
    size_str = str(size_str).strip().lower()
    
    if "1 bis 9" in size_str or "1-9" in size_str:
        return "Kleinstunternehmen (1 - 9)"
    elif "10 bis 49" in size_str or "10-49" in size_str:
        return "Kleine Unternehmen (10 - 49)"
    elif "50 bis 249" in size_str or "50-249" in size_str:
        return "Mittlere Unternehmen (50 - 249)"
    elif "bis 500" in size_str or "250-500" in size_str:
        return "Größere Unternehmen (250 - 500)"
    elif "mehr als 500" in size_str or "500+" in size_str or "> 500" in size_str:
        return "Großunternehmen (> 500)"
    else:
        return "Unbekannt"

def calculate_visitor_statistics():
    """Berechnet Besucherstatistiken für alle Kategorien - unterscheidet zwischen vollständig und teilweise teilnehmenden Organisationen"""
    stats = []
    
    # Unternehmen nach Größe
    if "Firmengröße" in df.columns:
        # Alle Unternehmen mit Firmengröße kategorisieren
        processed_df_with_category = processed_df.copy()
        processed_df_with_category["Größenkategorie"] = processed_df_with_category["Firmengröße"].apply(map_company_size_to_category)
        
        # Nur echte Unternehmen (ist_unternehmen = True)
        unternehmen_df = processed_df_with_category[processed_df_with_category["ist_unternehmen"]]
        
        categories = [
            "Kleinstunternehmen (1 - 9)",
            "Kleine Unternehmen (10 - 49)", 
            "Mittlere Unternehmen (50 - 249)",
            "Größere Unternehmen (250 - 500)",
            "Großunternehmen (> 500)"
        ]
        
        for category in categories:
            category_df = unternehmen_df[unternehmen_df["Größenkategorie"] == category]
            
            angemeldet_personen = len(category_df)
            teilgenommen_personen = len(category_df[category_df["teilgenommen"]])
            angemeldet_unternehmen = category_df["Unternehmen"].nunique()
            
            # Unternehmen mit mindestens einer teilnehmenden Person
            teilgenommen_unternehmen = category_df[category_df["teilgenommen"]]["Unternehmen"].nunique()
            
            stats.append([
                category,
                angemeldet_personen,
                teilgenommen_personen,
                angemeldet_unternehmen,
                teilgenommen_unternehmen
            ])
    
    # Institutionstypen
    institution_categories = [
        ("kammer", "Kammer"),
        ("verband_verein", "Verband/Verein"),
        ("wirtschaftsfoerderung", "Wirtschaftsförderung"),
        ("hochschule", "Hochschulen/Bildungseinrichtung"),
        ("mittelstand_digital", "Mittelstand-Digital"),
        ("foerderinitiative", "Förderinitiative"),
        ("unklar", "Unklar")
    ]
    
    for inst_type, label in institution_categories:
        # Alle Personen mit diesem Institutionstyp
        category_df = processed_df[processed_df[inst_type]]
        
        angemeldet_personen = len(category_df)
        teilgenommen_personen = len(category_df[category_df["teilgenommen"]])
        angemeldet_institutionen = category_df["Unternehmen"].nunique() if len(category_df) > 0 else 0
        
        # Institutionen mit mindestens einer teilnehmenden Person
        teilgenommen_institutionen = category_df[category_df["teilgenommen"]]["Unternehmen"].nunique() if len(category_df[category_df["teilgenommen"]]) > 0 else 0
        
        stats.append([
            label,
            angemeldet_personen,
            teilgenommen_personen,
            angemeldet_institutionen,
            teilgenommen_institutionen
        ])
    
    return stats

# Statistiken berechnen
visitor_stats = calculate_visitor_statistics()

# Tabelle erstellen
stats_df = pd.DataFrame(visitor_stats, columns=[
    "Kategorie",
    "Anzahl angemeldeter Personen",
    "Anzahl teilnehmender/erreichter Personen", 
    "Anzahl angemeldeter Unternehmen/Institutionen",
    "Anzahl teilnehmender/erreichter Unternehmen/Institutionen"
])

# Tabelle anzeigen
st.dataframe(stats_df, use_container_width=True, hide_index=True)

# Zusätzliche Detailanalyse für gemischte Teilnahme
st.write("---")
st.subheader("🔍 Detailanalyse: Unternehmen/Institutionen mit gemischter Teilnahme")

mixed_participation_data = []

# Unternehmen analysieren
for company in processed_df[processed_df["ist_unternehmen"]]["Unternehmen"].unique():
    company_data = processed_df[(processed_df["ist_unternehmen"]) & (processed_df["Unternehmen"] == company)]
    total_registered = len(company_data)
    total_participated = len(company_data[company_data["teilgenommen"]])
    
    if total_registered > 1 and 0 < total_participated < total_registered:
        mixed_participation_data.append({
            "Organisation": company,
            "Typ": "Unternehmen",
            "Angemeldet": total_registered,
            "Teilgenommen": total_participated,
            "Status": f"{total_participated} von {total_registered} Personen"
        })

# Institutionen analysieren  
for inst_type in institution_types:
    for institution in processed_df[processed_df[inst_type]]["Unternehmen"].unique():
        institution_data = processed_df[(processed_df[inst_type]) & (processed_df["Unternehmen"] == institution)]
        total_registered = len(institution_data)
        total_participated = len(institution_data[institution_data["teilgenommen"]])
        
        if total_registered > 1 and 0 < total_participated < total_registered:
            mixed_participation_data.append({
                "Organisation": institution,
                "Typ": institution_labels[inst_type],
                "Angemeldet": total_registered,
                "Teilgenommen": total_participated,
                "Status": f"{total_participated} von {total_registered} Personen"
            })

if mixed_participation_data:
    mixed_df = pd.DataFrame(mixed_participation_data)
    st.dataframe(mixed_df, use_container_width=True, hide_index=True)
    
    st.info(f"📊 **Wichtiger Hinweis**: {len(mixed_participation_data)} Organisationen haben nur teilweise teilgenommen. " + 
           "Diese werden in der Besucherkennzahlen-Tabelle als 'teilnehmende Organisationen' gezählt, " +
           "obwohl nicht alle ihre Vertreter anwesend waren.")
else:
    st.success("✅ Keine Organisationen mit gemischter Teilnahme gefunden.")

# Exportierbare Version der Tabelle
st.write("---")
st.write("**Tabelle als CSV exportieren:**")
visitor_stats_csv = stats_df.to_csv(index=False, sep=";", encoding="utf-8-sig")
st.download_button(
    label="📊 Besucherkennzahlen als CSV",
    data=visitor_stats_csv,
    file_name=f"MDZ_Besucherkennzahlen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

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
