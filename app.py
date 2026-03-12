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
    help="Sie können sowohl neue Rohdaten als auch bereits bearbeitete CSV-Dateien (mit gespeicherten Einstellungen) hochladen.",
)

if uploaded_file is None:
    st.info("Bitte lade eine CSV-Datei hoch.")
    st.stop()

# CSV lesen - verschiedene Encodings und Separatoren versuchen
encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
separators = [";", ",", "\t"]
df = None
successful_config = None

for encoding in encodings:
    for sep in separators:
        try:
            # Zurück zum Anfang der Datei
            uploaded_file.seek(0)
            # Versuche mit verschiedenen Einstellungen
            df = pd.read_csv(
                uploaded_file, 
                sep=sep, 
                encoding=encoding,
                on_bad_lines='skip',  # Überspringe problematische Zeilen
                skipinitialspace=True  # Entferne Leerzeichen nach Separator
            )
            # Prüfe ob das Ergebnis sinnvoll ist (mindestens 1 Zeile und 3 Spalten)
            if len(df) > 0 and len(df.columns) >= 3:
                successful_config = f"Encoding: {encoding}, Separator: '{sep}'"
                break
        except Exception as e:
            continue
    if df is not None and len(df) > 0:
        break

if df is None or len(df) == 0:
    st.error("Konnte CSV-Datei nicht lesen. Bitte prüfe das Dateiformat.")
    st.write("**Mögliche Probleme:**")
    st.write("- Falsches Encoding (UTF-8, Latin-1, CP1252 probiert)")
    st.write("- Falscher Separator (Semikolon, Komma, Tab probiert)")
    st.write("- Datei ist leer oder beschädigt")
    st.stop()
else:
    st.success(f"✅ CSV erfolgreich eingelesen ({successful_config})")


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

# Leere Spalten entfernen (entstehen durch abschließende Separatoren)
df = df.dropna(axis=1, how='all')
# Auch Spalten mit nur leerem String entfernen
for col in df.columns:
    if df[col].dtype == 'object' and df[col].str.strip().eq('').all():
        df = df.drop(columns=[col])

# Spalten werden nicht mehr angezeigt

# Kategorien definieren
kategorie_optionen = [
    "Unternehmen 1-9 Mitarbeiter",
    "Unternehmen 10-49 Mitarbeiter",
    "Unternehmen 50-249 Mitarbeiter",
    "Unternehmen bis 500 Mitarbeiter",
    "Unternehmen ueber 500 Mitarbeiter",
    "Kammer",
    "Verband/Verein",
    "Wirtschaftsförderung",
    "Hochschule/Bildungseinrichtung",
    "Mittelstand-Digital",
    "Förderinitiative",
    "Unklar",
]

# Prüfen, ob es sich um eine bereits bearbeitete Datei handelt
has_checkbox_columns = "Kategorie" in df.columns or "teilgenommen" in df.columns
if has_checkbox_columns:
    st.success("✅ Bereits bearbeitete Datei erkannt - Einstellungen werden geladen!")
else:
    st.info("ℹ️ Rohdatei erkannt - Standard-Einstellungen werden angewandt.")

# Erwartete Spalten - flexibler prüfen
required_base = ["Unternehmen"]
firmengröße_found = any(
    "firmengröße" in col.lower() or "firmen" in col.lower() and "gr" in col.lower()
    for col in df.columns
)

# Falls die Standard-Spalte "Unternehmen" nicht vorhanden ist, prüfe alternative Varianten
unternehmen_spalte = None
if "Unternehmen" in df.columns:
    unternehmen_spalte = "Unternehmen"
else:
    # Suche nach anderen möglichen Unternehmensspalten
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ["unternehmen", "firma", "betrieb", "organisation"]):
            unternehmen_spalte = col
            # Spalte umbenennen für einheitliche Verarbeitung
            df = df.rename(columns={col: "Unternehmen"})
            break

if unternehmen_spalte is None:
    st.error("Keine Unternehmensspalte gefunden! Gesuchte Spalten: 'Unternehmen', 'Firma', 'Betrieb', 'Organisation'")
    st.stop()

if not firmengröße_found:
    st.warning("Keine Firmengröße-Spalte gefunden. App funktioniert trotzdem.")

# Daten säubern
df["Unternehmen"] = df["Unternehmen"].astype(str).str.strip()

# Umgang mit leeren Unternehmenswerten
original_length = len(df)

# Falls Unternehmensspalte komplett leer ist (wie in der Demo-Datei), verwende Zielgruppe als Platzhalter
empty_companies_mask = df["Unternehmen"].isna() | (df["Unternehmen"] == "") | (df["Unternehmen"] == "nan")
empty_companies_count = empty_companies_mask.sum()

if empty_companies_count > 0:
    if "Zielgruppe" in df.columns:
        # Verwende Zielgruppe + laufende Nummer als Platzhalter-Unternehmen
        for idx, row in df[empty_companies_mask].iterrows():
            zielgruppe = str(row["Zielgruppe"]) if pd.notna(row["Zielgruppe"]) else "Unbekannt"
            df.at[idx, "Unternehmen"] = f"{zielgruppe}_Firma_{idx+1}"
        st.info(f"ℹ️ {empty_companies_count} leere Unternehmenswerte wurden durch Platzhalter basierend auf der Zielgruppe ersetzt.")
    else:
        # Fallback: Verwende generische Platzhalter
        for idx, row in df[empty_companies_mask].iterrows():
            df.at[idx, "Unternehmen"] = f"Unternehmen_{idx+1}"
        st.info(f"ℹ️ {empty_companies_count} leere Unternehmenswerte wurden durch generische Platzhalter ersetzt.")

# Final check: Stelle sicher, dass wir noch Daten haben
if len(df) == 0:
    st.error("Nach der Datenbereinigung sind keine Datensätze mehr vorhanden!")
    st.stop()

# Debug info wird ans Ende verschoben


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
    
    # Stelle sicher, dass teilgenommen ein Boolean ist
    if "teilgenommen" in processed_df.columns:
        # Konvertiere verschiedene Formate zu Boolean
        processed_df["teilgenommen"] = processed_df["teilgenommen"].apply(
            lambda x: bool(x) if isinstance(x, (bool, int)) else 
                     str(x).lower() in ["true", "1", "yes", "ja", "wahr"] if pd.notna(x) else False
        )
    
    return processed_df


# ==============================
# TEILNAHME-MARKIERUNG
# ==============================

st.subheader("✅ Teilnahme markieren")

# Teilnahme-Status initialisieren
if "teilgenommen" not in df.columns:
    df["teilgenommen"] = True  # Default: teilgenommen
else:
    # Importierte Checkbox-Werte richtig interpretieren
    df["teilgenommen"] = (
        df["teilgenommen"].astype(str).str.lower().isin(["true", "1", "yes", "ja"])
    )

# Kategorie-Spalte initialisieren
if "Kategorie" not in df.columns:
    def intelligent_category_detection(row):
        """Intelligente Erkennung der Kategorie basierend auf Unternehmen und Zielgruppe"""
        unternehmen = str(row.get("Unternehmen", "")).lower().strip()
        zielgruppe = str(row.get("Zielgruppe", "")).lower().strip()
        firmengroesse = str(row.get("Firmengröße", "")).lower().strip()
        
        # GmbH hat Vorrang - bleibt bei Firmengröße-basierter Kategorisierung
        if "gmbh" in unternehmen or "gmbh & co" in unternehmen or "gmbh&co" in unternehmen:
            # Verwende Firmengröße-basierte Kategorisierung für GmbHs
            if "Firmengröße" in df.columns and pd.notna(row.get("Firmengröße")):
                groesse_str = firmengroesse
                if "1 bis 9" in groesse_str or "1-9" in groesse_str:
                    return "Unternehmen 1-9 Mitarbeiter"
                elif "10 bis 49" in groesse_str or "10-49" in groesse_str:
                    return "Unternehmen 10-49 Mitarbeiter"
                elif "50 bis 249" in groesse_str or "50-249" in groesse_str:
                    return "Unternehmen 50-249 Mitarbeiter"
                elif "bis 500" in groesse_str or "250-500" in groesse_str:
                    return "Unternehmen bis 500 Mitarbeiter"
                elif "mehr als 500" in groesse_str or "500+" in groesse_str:
                    return "Unternehmen ueber 500 Mitarbeiter"
                else:
                    return "Unternehmen 1-9 Mitarbeiter"
            else:
                return "Unternehmen 1-9 Mitarbeiter"
        
        # Bildungseinrichtungen erkennen (aber nicht wenn GmbH)
        bildung_keywords = [
            "uni", "universität", "university", "hochschule", "institut", "fachhochschule", 
            "fh", "th", "technische hochschule", "btü", "btu", "btu cottbus", "btu cottbus-senftenberg",
            "btu cottbus senftenberg", "chesco", "akademie", "college", "school"
        ]
        if any(keyword in unternehmen for keyword in bildung_keywords) or "bildung" in zielgruppe or "hochschule" in zielgruppe:
            return "Hochschule/Bildungseinrichtung"
        
        # Verbände/Vereine erkennen
        verband_keywords = ["e.v.", "e.v", "e. v.", "e. v", "eingetragener verein", "verband", "verein", "bund", "gesellschaft e.v", "förderverein", "innung"]
        if any(keyword in unternehmen for keyword in verband_keywords) or "verband" in zielgruppe or "verein" in zielgruppe:
            return "Verband/Verein"
        
        # Kammern erkennen
        if "kammer" in unternehmen or "ihk" in unternehmen or "handwerkskammer" in unternehmen:
            return "Kammer"
        
        # Wirtschaftsförderung erkennen
        if "wirtschaftsförderung" in unternehmen or "wirtschaftsfoerderung" in unternehmen:
            return "Wirtschaftsförderung"
        
        # Mittelstand Digital erkennen
        mdz_keywords = ["mdz", "mittelstand-digitalzentrum", "mittelstand digitalzentrum"]
        if (any(keyword in unternehmen for keyword in mdz_keywords) or 
            ("mittelstand" in unternehmen and "digital" in unternehmen)):
            return "Mittelstand-Digital"
        
        # Sonst: Unternehmen basierend auf Firmengröße
        if "Firmengröße" in df.columns and pd.notna(row.get("Firmengröße")):
            groesse_str = firmengroesse
            if "1 bis 9" in groesse_str or "1-9" in groesse_str:
                return "Unternehmen 1-9 Mitarbeiter"
            elif "10 bis 49" in groesse_str or "10-49" in groesse_str:
                return "Unternehmen 10-49 Mitarbeiter"
            elif "50 bis 249" in groesse_str or "50-249" in groesse_str:
                return "Unternehmen 50-249 Mitarbeiter"
            elif "bis 500" in groesse_str or "250-500" in groesse_str:
                return "Unternehmen bis 500 Mitarbeiter"
            elif "mehr als 500" in groesse_str or "500+" in groesse_str:
                return "Unternehmen ueber 500 Mitarbeiter"
            else:
                return "Unternehmen 1-9 Mitarbeiter"
        else:
            return "Unternehmen 1-9 Mitarbeiter"  # Default
    
    df["Kategorie"] = df.apply(intelligent_category_detection, axis=1)

# Legacy-Spalten entfernen falls vorhanden (für Rückwärtskompatibilität)
legacy_columns = [
    "ist_unternehmen",
    "kammer",
    "verband_verein",
    "wirtschaftsfoerderung",
    "hochschule",
    "mittelstand_digital",
    "foerderinitiative",
    "unklar",
]
for col in legacy_columns:
    if col in df.columns:
        df = df.drop(columns=[col])

# Session State für zu löschende Zeilen
if "rows_to_delete" not in st.session_state:
    st.session_state.rows_to_delete = []

# Session State für persistente Bearbeitungen (überleben Sortieränderungen)
if "saved_edits" not in st.session_state:
    st.session_state.saved_edits = {}  # {row_id: {col: value, ...}}
if "last_sort_option" not in st.session_state:
    st.session_state.last_sort_option = "Ursprüngliche Reihenfolge"

# Zeilen-Auswahl für Löschung
st.write("**Zeile zum Löschen auswählen:**")
if len(df) > 0:
    selected_row = st.selectbox(
        "Welche Zeile soll gelöscht werden?",
        options=[None] + list(range(len(df))),
        format_func=lambda x: "Keine Auswahl"
        if x is None
        else f"Zeile {x + 1}: {df.iloc[x]['Unternehmen']}",
    )

    col1, col2 = st.columns(2)
    with col1:
        if (
            st.button("🗑️ Ausgewählte Zeile löschen", type="secondary")
            and selected_row is not None
        ):
            st.session_state.rows_to_delete.append(selected_row)
            st.success(f"Zeile {selected_row + 1} wird gelöscht!")

    with col2:
        if st.button("↺ Löschungen rückgängig", type="secondary"):
            st.session_state.rows_to_delete = []
            st.success("Alle Löschungen zurückgesetzt!")

# Reset-Button für alle Änderungen
if st.button("🔄 Alle Änderungen zurücksetzen", type="secondary"):
    st.session_state.rows_to_delete = []
    st.session_state.saved_edits = {}
    st.session_state.last_sort_option = "Ursprüngliche Reihenfolge"
    if "main_data_editor" in st.session_state:
        del st.session_state["main_data_editor"]
    st.success("Alle Änderungen wurden zurückgesetzt!")
    st.rerun()


# Verwende ursprünglichen DataFrame und filtere gelöschte Zeilen
working_df = df.drop(index=st.session_state.rows_to_delete).reset_index(drop=True)

# Stabile Zeilen-ID hinzufügen (überlebt Sortieränderungen)
working_df["_row_id"] = range(len(working_df))

# Gespeicherte Bearbeitungen auf working_df anwenden
editable_cols = ["teilgenommen", "Kategorie", "Unternehmen"]
for row_id, edits in st.session_state.saved_edits.items():
    if row_id < len(working_df):
        for col, val in edits.items():
            if col in working_df.columns:
                working_df.at[row_id, col] = val

# Zeilennummer als erste Spalte hinzufügen
working_df_with_index = working_df.copy()
working_df_with_index.insert(0, "Nr.", range(1, len(working_df_with_index) + 1))


if len(st.session_state.rows_to_delete) > 0:
    st.warning(
        f"{len(st.session_state.rows_to_delete)} Zeile(n) werden gelöscht: {[i + 1 for i in st.session_state.rows_to_delete]}"
    )

# Warnung für Namenskonsistenz
st.info(
    "**Tipp**: Achten Sie ggbf. darauf, dass Unternehmen/Institutionen mit mehreren Vertretern exakt gleich benannt sind (z.B. 'BTU Cottbus-Senftenberg' und nicht 'BTU Cottbus Senftenberg')."
)

st.write("**Daten bearbeiten:**")

# Sortier-Option
sort_options = ["Ursprüngliche Reihenfolge", "Unternehmen (A-Z)", "Unternehmen (Z-A)", "Kategorie (A-Z)", "Kategorie (Z-A)"]
if "Firmengröße" in working_df_with_index.columns:
    sort_options.extend(["Firmengröße (Klein → Groß)", "Firmengröße (Groß → Klein)"])

sort_option = st.selectbox(
    "Tabelle sortieren nach:",
    options=sort_options,
    help="Wählen Sie, wie die Tabelle sortiert werden soll",
    key="sort_selector",
)

# Sortieränderung erkennen: data_editor zurücksetzen
# Hinweis: Bearbeitungen wurden bereits im vorherigen Run durch den Post-Editor-Save
# (nach dem data_editor) korrekt in saved_edits gespeichert. Hier muss nur der
# Widget-State gelöscht werden, damit der Editor mit der neuen Sortierung neu startet.
if sort_option != st.session_state.last_sort_option:
    if "main_data_editor" in st.session_state:
        del st.session_state["main_data_editor"]
    st.session_state.last_sort_option = sort_option
    st.rerun()

# Tabelle sortieren
if sort_option == "Unternehmen (A-Z)":
    working_df_with_index = working_df_with_index.sort_values(
        "Unternehmen", key=lambda x: x.str.lower(), ascending=True
    ).reset_index(drop=True)
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Unternehmen (Z-A)":
    working_df_with_index = working_df_with_index.sort_values(
        "Unternehmen", key=lambda x: x.str.lower(), ascending=False
    ).reset_index(drop=True)
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Kategorie (A-Z)":
    working_df_with_index = working_df_with_index.sort_values(
        "Kategorie", ascending=True
    ).reset_index(drop=True)
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif sort_option == "Kategorie (Z-A)":
    working_df_with_index = working_df_with_index.sort_values(
        "Kategorie", ascending=False
    ).reset_index(drop=True)
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif (
    sort_option == "Firmengröße (Klein → Groß)"
    and "Firmengröße" in working_df_with_index.columns
):
    # Größenordnung definieren
    size_order = {
        "1 bis 9 Mitarbeiter": 1,
        "10 bis 49 Mitarbeiter": 2,
        "50 bis 249 Mitarbeiter": 3,
        "bis 500 Mitarbeiter": 4,
        "mehr als 500 Mitarbeiter": 5,
    }
    working_df_with_index["_sort_key"] = working_df_with_index["Firmengröße"].map(
        lambda x: size_order.get(str(x).strip(), 99)
    )
    working_df_with_index = working_df_with_index.sort_values(
        "_sort_key", ascending=True
    ).reset_index(drop=True)
    working_df_with_index = working_df_with_index.drop(columns=["_sort_key"])
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)
elif (
    sort_option == "Firmengröße (Groß → Klein)"
    and "Firmengröße" in working_df_with_index.columns
):
    # Größenordnung definieren
    size_order = {
        "1 bis 9 Mitarbeiter": 1,
        "10 bis 49 Mitarbeiter": 2,
        "50 bis 249 Mitarbeiter": 3,
        "bis 500 Mitarbeiter": 4,
        "mehr als 500 Mitarbeiter": 5,
    }
    working_df_with_index["_sort_key"] = working_df_with_index["Firmengröße"].map(
        lambda x: size_order.get(str(x).strip(), 99)
    )
    working_df_with_index = working_df_with_index.sort_values(
        "_sort_key", ascending=False
    ).reset_index(drop=True)
    working_df_with_index = working_df_with_index.drop(columns=["_sort_key"])
    working_df_with_index["Nr."] = range(1, len(working_df_with_index) + 1)

# Spalten in gewünschter Reihenfolge anordnen
# Gewünschte Reihenfolge: Nr., Unternehmen, Hat teilgenommen?, Kategorie, dann alle anderen
desired_order = ["Nr.", "Unternehmen", "teilgenommen", "Kategorie"]

# Alle anderen Spalten hinzufügen (außer den bereits in desired_order)
other_columns = [
    col for col in working_df_with_index.columns if col not in desired_order
]
final_column_order = desired_order + other_columns

# DataFrame mit neuer Spaltenreihenfolge
working_df_with_index = working_df_with_index[final_column_order]

# Create column configuration
column_config = {
    "Nr.": st.column_config.NumberColumn(
        "Nr.", help="Zeilennummer", disabled=True, width="small"
    ),
    "teilgenommen": st.column_config.CheckboxColumn(
        "Hat teilgenommen?", help="Häkchen entfernen = nur angemeldet"
    ),
    "Kategorie": st.column_config.SelectboxColumn(
        "Kategorie",
        help="Wählen Sie die passende Kategorie",
        options=kategorie_optionen,
        required=True,
    ),
    "Unternehmen": st.column_config.TextColumn(
        "Unternehmen", help="Unternehmen/Institution bearbeitbar"
    ),
    "_row_id": None,  # Spalte im Editor ausblenden
}


# Hilfsfunktionen für Kategorisierung
def ist_unternehmen(kategorie):
    """Prüft ob eine Kategorie ein Unternehmen ist"""
    return kategorie.startswith("Unternehmen")


def get_firmengroesse_from_kategorie(kategorie):
    """Extrahiert Firmengröße aus Kategorie"""
    if kategorie == "Unternehmen 1-9 Mitarbeiter":
        return "1 bis 9 Mitarbeiter"
    elif kategorie == "Unternehmen 10-49 Mitarbeiter":
        return "10 bis 49 Mitarbeiter"
    elif kategorie == "Unternehmen 50-249 Mitarbeiter":
        return "50 bis 249 Mitarbeiter"
    elif kategorie == "Unternehmen bis 500 Mitarbeiter":
        return "bis 500 Mitarbeiter"
    elif kategorie == "Unternehmen ueber 500 Mitarbeiter":
        return "mehr als 500 Mitarbeiter"
    else:
        return None


edited_df_with_index = st.data_editor(
    working_df_with_index,
    use_container_width=True,
    num_rows="dynamic",
    column_config=column_config,
    disabled=["Nr.", "_row_id"]
    + (["Firmengröße"] if "Firmengröße" in working_df_with_index.columns else []),
    key="main_data_editor"
)

# Bearbeitungen aus data_editor in saved_edits sichern (für Persistenz über Sortierungen hinweg)
if "main_data_editor" in st.session_state:
    editor_state = st.session_state["main_data_editor"]
    edited_rows = editor_state.get("edited_rows", {})
    for row_idx_str, changes in edited_rows.items():
        row_idx = int(row_idx_str)
        if row_idx < len(edited_df_with_index):
            row_id = int(edited_df_with_index.iloc[row_idx]["_row_id"])
            if row_id not in st.session_state.saved_edits:
                st.session_state.saved_edits[row_id] = {}
            st.session_state.saved_edits[row_id].update(changes)

# Zeilennummer und _row_id entfernen für weitere Verarbeitung
edited_df = edited_df_with_index.drop(columns=["Nr.", "_row_id"])


# Dynamische Kategorie-Aktualisierung bei geänderten Unternehmensnamen
def update_category_if_needed(row):
    """Aktualisiert die Kategorie wenn der Unternehmensname geändert wurde"""
    unternehmen = str(row.get("Unternehmen", "")).lower().strip()
    aktuelle_kategorie = row.get("Kategorie", "")
    
    # GmbH hat Vorrang - bleibt bei Firmengröße-basierter Kategorisierung
    if "gmbh" in unternehmen or "gmbh & co" in unternehmen or "gmbh&co" in unternehmen:
        # Behalte aktuelle Kategorie für GmbHs (meist schon korrekt nach Firmengröße)
        return aktuelle_kategorie
    
    # Nur für Unternehmen, die gerade geändert wurden oder noch Default-Kategorien haben
    bildung_keywords = [
        "uni", "universität", "university", "hochschule", "institut", "fachhochschule", 
        "fh", "th", "technische hochschule", "btü", "btu", "btu cottbus", "btu cottbus-senftenberg",
        "btu cottbus senftenberg", "chesco", "akademie", "college", "school"
    ]
    verband_keywords = ["e.v.", "e.v", "e. v.", "e. v", "eingetragener verein", "verband", "verein", "bund", "gesellschaft e.v", "förderverein", "innung"]

    if any(keyword in unternehmen for keyword in bildung_keywords):
        return "Hochschule/Bildungseinrichtung"
    elif any(keyword in unternehmen for keyword in verband_keywords):
        return "Verband/Verein"
    elif "kammer" in unternehmen or "ihk" in unternehmen:
        return "Kammer"
    elif "wirtschaftsförderung" in unternehmen or "wirtschaftsfoerderung" in unternehmen:
        return "Wirtschaftsförderung"
    elif ("mdz" in unternehmen or "mittelstand-digitalzentrum" in unternehmen or "mittelstand digitalzentrum" in unternehmen or
          ("mittelstand" in unternehmen and "digital" in unternehmen)):
        return "Mittelstand-Digital"
    else:
        # Behalte die aktuelle Kategorie bei, wenn keine Schlüsselwörter gefunden
        return aktuelle_kategorie

# HINWEIS: Die automatische Kategorie-Aktualisierung wurde entfernt,
# damit manuelle Änderungen des Benutzers nicht überschrieben werden.
# Die initiale Kategorisierung erfolgt bereits beim CSV-Import (Zeile 323).

# Die edited_df wird direkt für die weitere Verarbeitung verwendet
# Keine komplexen Session State Updates mehr

# ==============================
# FILTER
# ==============================

# Bearbeitete Daten verarbeiten
processed_df = process_edited_data(edited_df)


teilgenommen_df = processed_df[processed_df["teilgenommen"]]
angemeldet_df = processed_df[~processed_df["teilgenommen"]]

# Nach Kategorie filtern
teilgenommen_unternehmen = teilgenommen_df[
    teilgenommen_df["Kategorie"].apply(ist_unternehmen)
]
angemeldet_unternehmen = angemeldet_df[
    angemeldet_df["Kategorie"].apply(ist_unternehmen)
]

# Institution type filtering for participants
institution_labels = {
    "Kammer": "Kammer",
    "Verband/Verein": "Verband/Verein",
    "Wirtschaftsförderung": "Wirtschaftsförderung",
    "Hochschule/Bildungseinrichtung": "Hochschule/Bildungseinrichtung",
    "Mittelstand-Digital": "Mittelstand-Digital",
    "Förderinitiative": "Förderinitiative",
    "Unklar": "Unklar",
}

teilgenommen_by_type = {}
angemeldet_by_type = {}

for kategorie, label in institution_labels.items():
    teilgenommen_by_type[kategorie] = teilgenommen_df[
        teilgenommen_df["Kategorie"] == kategorie
    ]
    angemeldet_by_type[kategorie] = angemeldet_df[
        angemeldet_df["Kategorie"] == kategorie
    ]

# Backward compatibility - all non-company institutions
teilgenommen_institutionen = teilgenommen_df[
    ~teilgenommen_df["Kategorie"].apply(ist_unternehmen)
]
angemeldet_institutionen = angemeldet_df[
    ~angemeldet_df["Kategorie"].apply(ist_unternehmen)
]

# ==============================
# ZÄHLLOGIK
# ==============================


def personen(df):
    return len(df)


def unternehmen(df):
    if len(df) == 0 or "Unternehmen" not in df.columns:
        return 0
    return df["Unternehmen"].nunique()


def personen_pro_unternehmen(df):
    if len(df) == 0 or "Unternehmen" not in df.columns:
        return pd.Series(dtype=int)
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


# Firmengröße-Auswertung wird jetzt über die Kategorie-Spalte gemacht

# ==============================
# ERGEBNISSE
# ==============================

st.subheader("📈 Ergebnisse")

# Gesamtübersicht - 3 Spalten mit Gesamt hinzugefügt
col1, col2, col3 = st.columns(3)

total_personen_gesamt = personen(processed_df)
total_unternehmen_gesamt = unternehmen(
    processed_df[processed_df["Kategorie"].apply(ist_unternehmen)]
)
total_personen_aus_unternehmen_gesamt = personen(
    processed_df[processed_df["Kategorie"].apply(ist_unternehmen)]
)
total_institutionen_gesamt = unternehmen(
    processed_df[~processed_df["Kategorie"].apply(ist_unternehmen)]
)

teilgenommen_institutionen_gesamt = unternehmen(
    teilgenommen_df[~teilgenommen_df["Kategorie"].apply(ist_unternehmen)]
)
angemeldet_institutionen_gesamt = unternehmen(
    angemeldet_df[~angemeldet_df["Kategorie"].apply(ist_unternehmen)]
)

with col1:
    st.write("**Gesamt (Angemeldet):**")
    st.metric("👤 Personen", total_personen_gesamt)
    st.metric("🏢 Unternehmen", total_unternehmen_gesamt)
    st.metric("👤 Personen aus Unternehmen", total_personen_aus_unternehmen_gesamt)
    st.metric("🏛️ Institutionen", total_institutionen_gesamt)

with col2:
    st.write("**Teilgenommen:**")
    st.metric("👤 Personen gesamt", personen(teilgenommen_df))
    st.metric("🏢 Unternehmen", unternehmen(teilgenommen_unternehmen))
    st.metric("👤 Personen aus Unternehmen", personen(teilgenommen_unternehmen))
    st.metric("🏛️ Institutionen", teilgenommen_institutionen_gesamt)

with col3:
    st.write("**Nur angemeldet:**")
    st.metric("👤 Personen gesamt", personen(angemeldet_df))
    st.metric("🏢 Unternehmen", unternehmen(angemeldet_unternehmen))
    st.metric("👤 Personen aus Unternehmen", personen(angemeldet_unternehmen))
    st.metric("🏛️ Institutionen", angemeldet_institutionen_gesamt)


# Hilfsfunktion für Besucherkennzahlen definieren
def calculate_visitor_statistics():
    """Berechnet Besucherstatistiken - Unternehmen nach Größe + Institutionen"""
    stats = []

    # Definierte Reihenfolge und Anzeigenamen für Besucherkennzahlen
    ordered_categories = [
        ("Unternehmen 1-9 Mitarbeiter",       "Kleinstunternehmen (1-9 Mitarbeiter)"),
        ("Unternehmen 10-49 Mitarbeiter",      "Kleine Unternehmen (10-49 Mitarbeiter)"),
        ("Unternehmen 50-249 Mitarbeiter",     "Mittlere Unternehmen (50-249 Mitarbeiter)"),
        ("Unternehmen bis 500 Mitarbeiter",    "Gr\u00f6\u00dfere Unternehmen (250-500 Mitarbeiter)"),
        ("Kammer",                             "Kammer"),
        ("Verband/Verein",                     "Verband/Verein"),
        ("Wirtschaftsf\u00f6rderung",          "Wirtschaftsf\u00f6rderung"),
        ("Unternehmen ueber 500 Mitarbeiter",  "Gro\u00dfunternehmen (500+ Mitarbeiter)"),
        ("Hochschule/Bildungseinrichtung",     "Hochschulen/Bildungseinrichtungen"),
        ("Mittelstand-Digital",                "Mittelstand-Digital"),
        ("F\u00f6rderinitiative",              "F\u00f6rderinitiative"),
    ]

    # Kategorien in definierter Reihenfolge durchgehen - ALLE anzeigen, auch bei 0
    for kategorie, display_name in ordered_categories:
        category_df = processed_df[processed_df["Kategorie"] == kategorie]

        angemeldet_personen = len(category_df)
        teilgenommen_personen = len(category_df[category_df["teilgenommen"]]) if len(category_df) > 0 else 0
        angemeldet_organisationen = category_df["Unternehmen"].nunique() if len(category_df) > 0 else 0
        teilgenommen_organisationen = (
            category_df[category_df["teilgenommen"]]["Unternehmen"].nunique()
            if len(category_df) > 0 and len(category_df[category_df["teilgenommen"]]) > 0
            else 0
        )

        stats.append(
            [
                display_name,
                angemeldet_personen,
                teilgenommen_personen,
                angemeldet_organisationen,
                teilgenommen_organisationen,
            ]
        )

    return stats


# Besucherkennzahlen / Reichweite
st.write("---")
st.subheader("📋 Besucherkennzahlen / Reichweite")
st.write("**Geschätzte Besucherkennzahlen**")

# Statistiken berechnen
visitor_stats = calculate_visitor_statistics()

# Tabelle erstellen
stats_df = pd.DataFrame(
    visitor_stats,
    columns=[
        "Kategorie",
        "Anzahl angemeldeter Personen",
        "Anzahl teilnehmender/erreichter Personen",
        "Anzahl angemeldeter Unternehmen/Institutionen",
        "Anzahl teilnehmender/erreichter Unternehmen/Institutionen",
    ],
)

# Tabelle anzeigen (Höhe so, dass alle 11 Kategorien ohne Scrollen sichtbar sind)
st.dataframe(stats_df, use_container_width=True, hide_index=True, height=422)

# Aggregierte Zahlen berechnen und anzeigen
total_angemeldet_personen = stats_df["Anzahl angemeldeter Personen"].sum()
total_teilgenommen_personen = stats_df["Anzahl teilnehmender/erreichter Personen"].sum()
total_angemeldet_organisationen = stats_df[
    "Anzahl angemeldeter Unternehmen/Institutionen"
].sum()
total_teilgenommen_organisationen = stats_df[
    "Anzahl teilnehmender/erreichter Unternehmen/Institutionen"
].sum()

# Aggregierte Summen als Tabelle darstellen
st.write("---")
st.write("**📊 Aggregierte Summen (Kontrolle):**")

aggregated_data = {
    "Kategorie": ["SUMME ALLER KATEGORIEN"],
    "Anzahl angemeldeter Personen": [total_angemeldet_personen],
    "Anzahl teilnehmender/erreichter Personen": [total_teilgenommen_personen],
    "Anzahl angemeldeter Unternehmen/Institutionen": [total_angemeldet_organisationen],
    "Anzahl teilnehmender/erreichter Unternehmen/Institutionen": [
        total_teilgenommen_organisationen
    ],
}

aggregated_df = pd.DataFrame(aggregated_data)

# Spezielle Formatierung für die Summenzeile
st.dataframe(
    aggregated_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Kategorie": st.column_config.TextColumn("Kategorie", width="medium"),
        "Anzahl angemeldeter Personen": st.column_config.NumberColumn(
            "Anzahl angemeldeter Personen", format="%d"
        ),
        "Anzahl teilnehmender/erreichter Personen": st.column_config.NumberColumn(
            "Anzahl teilnehmender/erreichter Personen", format="%d"
        ),
        "Anzahl angemeldeter Unternehmen/Institutionen": st.column_config.NumberColumn(
            "Anzahl angemeldeter Unternehmen/Institutionen", format="%d"
        ),
        "Anzahl teilnehmender/erreichter Unternehmen/Institutionen": st.column_config.NumberColumn(
            "Anzahl teilnehmender/erreichter Unternehmen/Institutionen", format="%d"
        ),
    },
)

# Vergleich mit den aggregierten Zahlen aus der Hauptstatistik
st.write("**🔍 Plausibilitätsprüfung:**")
col1, col2 = st.columns(2)

with col1:
    st.write("**Aus Besucherkennzahlen-Tabelle:**")
    st.write(f"• Angemeldete Personen: {total_angemeldet_personen}")
    st.write(f"• Teilnehmende Personen: {total_teilgenommen_personen}")
    st.write(f"• Angemeldete Organisationen: {total_angemeldet_organisationen}")
    st.write(f"• Teilnehmende Organisationen: {total_teilgenommen_organisationen}")

with col2:
    st.write("**Aus Hauptstatistik (zur Kontrolle):**")
    st.write(f"• Personen gesamt: {total_personen_gesamt}")
    st.write(f"• Personen teilgenommen: {personen(teilgenommen_df)}")
    main_total_org_angemeldet = total_unternehmen_gesamt + total_institutionen_gesamt
    main_total_org_teilgenommen = (
        unternehmen(teilgenommen_unternehmen) + teilgenommen_institutionen_gesamt
    )
    st.write(f"• Organisationen gesamt: {main_total_org_angemeldet}")
    st.write(f"• Organisationen teilgenommen: {main_total_org_teilgenommen}")

# Warnungen bei Abweichungen
if total_angemeldet_personen != total_personen_gesamt:
    st.warning(
        f"⚠️ **Abweichung Personen gesamt**: Tabelle ({total_angemeldet_personen}) ≠ Hauptstatistik ({total_personen_gesamt})"
    )
if total_teilgenommen_personen != personen(teilgenommen_df):
    st.warning(
        f"⚠️ **Abweichung Personen teilgenommen**: Tabelle ({total_teilgenommen_personen}) ≠ Hauptstatistik ({personen(teilgenommen_df)})"
    )
if total_angemeldet_organisationen != main_total_org_angemeldet:
    st.warning(
        f"⚠️ **Abweichung Organisationen gesamt**: Tabelle ({total_angemeldet_organisationen}) ≠ Hauptstatistik ({main_total_org_angemeldet})"
    )
if total_teilgenommen_organisationen != main_total_org_teilgenommen:
    st.warning(
        f"⚠️ **Abweichung Organisationen teilgenommen**: Tabelle ({total_teilgenommen_organisationen}) ≠ Hauptstatistik ({main_total_org_teilgenommen})"
    )

if (
    total_angemeldet_personen == total_personen_gesamt
    and total_teilgenommen_personen == personen(teilgenommen_df)
    and total_angemeldet_organisationen == main_total_org_angemeldet
    and total_teilgenommen_organisationen == main_total_org_teilgenommen
):
    st.success("✅ **Alle Zahlen stimmen überein** - Die Statistiken sind konsistent!")

# Detaillierte Aufschlüsselung
st.write("---")
st.subheader("🏛️ Detaillierte Aufschlüsselung nach Kategorien")

# Tabs für bessere Übersicht
tab1, tab2 = st.tabs(["👥 Teilgenommen", "📝 Nur angemeldet"])

unternehmen_kategorien = [
    ("Unternehmen 1-9 Mitarbeiter", "Kleinstunternehmen"),
    ("Unternehmen 10-49 Mitarbeiter", "Kleine Unternehmen"),
    ("Unternehmen 50-249 Mitarbeiter", "Mittlere Unternehmen"),
    ("Unternehmen bis 500 Mitarbeiter", "Größere Unternehmen"),
    ("Unternehmen ueber 500 Mitarbeiter", "Großunternehmen"),
]

institution_icons = {
    "Kammer": "⚖️",
    "Verband/Verein": "🤝",
    "Wirtschaftsförderung": "📈",
    "Hochschule/Bildungseinrichtung": "🎓",
    "Mittelstand-Digital": "💻",
    "Förderinitiative": "🚀",
    "Unklar": "❓",
}

with tab1:
    st.write("### 🏢 Unternehmen")
    
    # Container für Unternehmen
    with st.container():
        for kategorie, display_name in unternehmen_kategorien:
            kategorie_teilgenommen = teilgenommen_df[teilgenommen_df["Kategorie"] == kategorie]
            anzahl_personen = personen(kategorie_teilgenommen)
            anzahl_unternehmen = unternehmen(kategorie_teilgenommen)
            if anzahl_personen > 0:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**{display_name}**")
                    with col2:
                        st.metric("👤 Personen", anzahl_personen)
                    with col3:
                        st.metric("🏢 Unternehmen", anzahl_unternehmen)

    st.write("### 🏛️ Institutionen")
    
    # Container für Institutionen mit besserer Struktur
    for inst_type, label in institution_labels.items():
        count_persons = personen(teilgenommen_by_type[inst_type])
        count_institutions = unternehmen(teilgenommen_by_type[inst_type])
        if count_persons > 0:
            icon = institution_icons.get(label, "🏛️")
            
            with st.expander(f"{icon} **{label}** ({count_persons} Personen aus {count_institutions} Institutionen)"):
                # Detailaufschlüsselung
                if len(teilgenommen_by_type[inst_type]) > 0:
                    institution_breakdown = (
                        teilgenommen_by_type[inst_type]
                        .groupby("Unternehmen")
                        .size()
                        .sort_values(ascending=False)
                    )
                    
                    if len(institution_breakdown) > 1:
                        st.write("**Aufschlüsselung nach Institutionen:**")
                        for institution_name, person_count in institution_breakdown.items():
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.write(f"• {institution_name}")
                            with col2:
                                st.write(f"👤 {person_count}")
                    else:
                        st.write(f"Alle Personen von: **{institution_breakdown.index[0]}**")

with tab2:
    st.write("### 🏢 Unternehmen")
    
    # Container für Unternehmen
    with st.container():
        for kategorie, display_name in unternehmen_kategorien:
            kategorie_angemeldet = angemeldet_df[angemeldet_df["Kategorie"] == kategorie]
            anzahl_personen = personen(kategorie_angemeldet)
            anzahl_unternehmen = unternehmen(kategorie_angemeldet)
            if anzahl_personen > 0:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**{display_name}**")
                    with col2:
                        st.metric("👤 Personen", anzahl_personen)
                    with col3:
                        st.metric("🏢 Unternehmen", anzahl_unternehmen)

    st.write("### 🏛️ Institutionen")
    
    # Container für Institutionen
    for inst_type, label in institution_labels.items():
        count_persons = personen(angemeldet_by_type[inst_type])
        count_institutions = unternehmen(angemeldet_by_type[inst_type])
        if count_persons > 0:
            icon = institution_icons.get(label, "🏛️")
            
            with st.expander(f"{icon} **{label}** ({count_persons} Personen aus {count_institutions} Institutionen)"):
                # Detailaufschlüsselung
                if len(angemeldet_by_type[inst_type]) > 0:
                    institution_breakdown = (
                        angemeldet_by_type[inst_type]
                        .groupby("Unternehmen")
                        .size()
                        .sort_values(ascending=False)
                    )
                    
                    if len(institution_breakdown) > 1:
                        st.write("**Aufschlüsselung nach Institutionen:**")
                        for institution_name, person_count in institution_breakdown.items():
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.write(f"• {institution_name}")
                            with col2:
                                st.write(f"👤 {person_count}")
                    else:
                        st.write(f"Alle Personen von: **{institution_breakdown.index[0]}**")


# Spezielle Kategorie "Unklar" hervorheben
unklar_personen_teilgenommen = personen(teilgenommen_by_type["Unklar"])
unklar_personen_angemeldet = personen(
    processed_df[processed_df["Kategorie"] == "Unklar"]
)
unklar_institutionen_teilgenommen = unternehmen(teilgenommen_by_type["Unklar"])
unklar_institutionen_angemeldet = unternehmen(
    processed_df[processed_df["Kategorie"] == "Unklar"]
)

if unklar_personen_angemeldet > 0:
    st.write("---")
    st.subheader("❓ Kategorie 'Unklar'")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("👤 Personen 'Unklar' (angemeldet)", unklar_personen_angemeldet)
        st.metric(
            "🏛️ Institutionen 'Unklar' (angemeldet)", unklar_institutionen_angemeldet
        )

    with col2:
        st.metric("👤 Personen 'Unklar' (teilgenommen)", unklar_personen_teilgenommen)
        st.metric(
            "🏛️ Institutionen 'Unklar' (teilgenommen)", unklar_institutionen_teilgenommen
        )

    st.warning(
        f"⚠️ **Auswirkung auf Statistiken**: {unklar_personen_angemeldet} Personen aus {unklar_institutionen_angemeldet} "
        + f"Institutionen sind als 'Unklar' kategorisiert. Diese werden NICHT zu den Unternehmenszahlen "
        + f"hinzugezählt, sondern separat als Institutionen vom Typ 'Unklar' behandelt. "
        + f"Sie beeinflussen somit die Gesamtstatistik der Institutionen, nicht der Unternehmen."
    )

    if unklar_personen_angemeldet > 0:
        st.info(
            "💡 **Tipp**: Prüfen Sie die als 'Unklar' markierten Einträge und kategorisieren Sie diese "
            + "korrekt als Unternehmen oder spezifischen Institutionstyp, um präzisere Statistiken zu erhalten."
        )

# ==============================
# MEHRPERSONEN-AUSWERTUNG
# ==============================

st.subheader("👥 Mehrere Personen pro Unternehmen/Institution")

# Nur Unternehmen
counts_unternehmen = personen_pro_unternehmen(teilgenommen_unternehmen)
buckets_unternehmen = bucket_auswertung(counts_unternehmen)

with st.container():
    st.markdown("**🏢 Unternehmen:**")
    
    # Buckets als Metrics anzeigen
    if buckets_unternehmen:
        col1, col2, col3 = st.columns(3)
        bucket_keys = list(buckets_unternehmen.keys())
        
        if "1 Person" in buckets_unternehmen:
            with col1:
                st.metric("1 Person", buckets_unternehmen["1 Person"])
        
        if "2 Personen" in buckets_unternehmen:
            with col2:
                st.metric("2 Personen", buckets_unternehmen["2 Personen"])
        
        if "3+ Personen" in buckets_unternehmen:
            with col3:
                st.metric("3+ Personen", buckets_unternehmen["3+ Personen"])
    
    # Mehrfach vertretene Unternehmen
    mehrfach_unternehmen = counts_unternehmen[counts_unternehmen > 1]
    
    if not mehrfach_unternehmen.empty:
        with st.expander("📋 Unternehmen mit mehreren teilnehmenden Personen"):
            st.dataframe(
                mehrfach_unternehmen.rename("Anzahl Personen"),
                use_container_width=True,
                column_config={
                    "Anzahl Personen": st.column_config.NumberColumn(
                        "Anzahl Personen", 
                        help="Anzahl der teilnehmenden Personen aus diesem Unternehmen"
                    )
                }
            )
    else:
        st.success("✅ Alle Unternehmen waren nur mit einer Person vertreten.")

# Andere Institutionen
if len(teilgenommen_institutionen) > 0:
    counts_institutionen = personen_pro_unternehmen(teilgenommen_institutionen)
    buckets_institutionen = bucket_auswertung(counts_institutionen)
    
    with st.container():
        st.markdown("**🏛️ Andere Institutionen:**")
        
        # Buckets als Metrics anzeigen
        if buckets_institutionen:
            col1, col2, col3 = st.columns(3)
            
            if "1 Person" in buckets_institutionen:
                with col1:
                    st.metric("1 Person", buckets_institutionen["1 Person"])
            
            if "2 Personen" in buckets_institutionen:
                with col2:
                    st.metric("2 Personen", buckets_institutionen["2 Personen"])
            
            if "3+ Personen" in buckets_institutionen:
                with col3:
                    st.metric("3+ Personen", buckets_institutionen["3+ Personen"])
        
        # Mehrfach vertretene Institutionen
        mehrfach_institutionen = counts_institutionen[counts_institutionen > 1]
        
        if not mehrfach_institutionen.empty:
            with st.expander("📋 Institutionen mit mehreren teilnehmenden Personen"):
                st.dataframe(
                    mehrfach_institutionen.rename("Anzahl Personen"),
                    use_container_width=True,
                    column_config={
                        "Anzahl Personen": st.column_config.NumberColumn(
                            "Anzahl Personen", 
                            help="Anzahl der teilnehmenden Personen aus dieser Institution"
                        )
                    }
                )

# ==============================
# FIRMENGRÖSSE-AUSWERTUNG
# ==============================

st.write("---")
# Kombiniert mit obigem Abschnitt

# Diese Aufschlüsselung wurde mit dem obigen Abschnitt kombiniert

# ==============================
# TEXTBAUSTEIN
# ==============================

st.subheader("📝 Textbaustein (z. B. für MDZ / Verwendungsnachweis)")

text_parts = []

# Gesamtanmeldungen
gesamt_angemeldet = personen(processed_df)
gesamt_teilgenommen = personen(teilgenommen_df)

text_parts.append(
    f"Für die Veranstaltung haben sich insgesamt {gesamt_angemeldet} Personen angemeldet."
)
text_parts.append(f"Davon nahmen {gesamt_teilgenommen} Personen teil.")

if unternehmen(teilgenommen_unternehmen) > 0:
    text_parts.append(
        f"Von den Teilnehmenden kamen {personen(teilgenommen_unternehmen)} Personen aus {unternehmen(teilgenommen_unternehmen)} Unternehmen."
    )

    if len(mehrfach_unternehmen) > 0:
        text_parts.append(
            f"{len(mehrfach_unternehmen)} Unternehmen waren mit mehreren Personen vertreten."
        )

# Add details for each institution type
institution_details = []
for kategorie, label in institution_labels.items():
    count_persons = personen(teilgenommen_by_type[kategorie])
    count_institutions = unternehmen(teilgenommen_by_type[kategorie])
    if count_persons > 0:
        if count_institutions == 1:
            institution_details.append(
                f"{count_persons} Personen aus {count_institutions} {label}"
            )
        else:
            institution_details.append(
                f"{count_persons} Personen aus {count_institutions} {label}"
            )

if institution_details:
    if len(institution_details) == 1:
        text_parts.append(f"Zusätzlich nahmen {institution_details[0]} teil.")
    else:
        text_parts.append(
            f"Zusätzlich nahmen teil: {', '.join(institution_details[:-1])} und {institution_details[-1]}."
        )

text = " ".join(text_parts)

st.text_area("Automatisch generierter Text", text, height=120)

# Besucherkennzahlen-Abschnitt wurde nach oben verschoben


# Firmengröße-Mapping erfolgt über die Kategorie-Spalte

# Duplikat entfernt - Aggregierte Summen sind bereits weiter oben berechnet

# Zusätzliche Detailanalyse für gemischte Teilnahme
st.write("---")
st.subheader("🔍 Detailanalyse: Unternehmen/Institutionen mit gemischter Teilnahme")

mixed_participation_data = []

# Unternehmen analysieren
for company in processed_df[processed_df["Kategorie"].apply(ist_unternehmen)][
    "Unternehmen"
].unique():
    company_data = processed_df[
        (processed_df["Kategorie"].apply(ist_unternehmen))
        & (processed_df["Unternehmen"] == company)
    ]
    total_registered = len(company_data)
    total_participated = len(company_data[company_data["teilgenommen"]])

    if total_registered > 1 and 0 < total_participated < total_registered:
        company_kategorie = (
            company_data["Kategorie"].iloc[0] if len(company_data) > 0 else "Unbekannt"
        )
        mixed_participation_data.append(
            {
                "Organisation": company,
                "Typ": company_kategorie,
                "Angemeldet": total_registered,
                "Teilgenommen": total_participated,
                "Status": f"{total_participated} von {total_registered} Personen",
            }
        )

# Institutionen analysieren
for kategorie in institution_labels.keys():
    for institution in processed_df[processed_df["Kategorie"] == kategorie][
        "Unternehmen"
    ].unique():
        institution_data = processed_df[
            (processed_df["Kategorie"] == kategorie)
            & (processed_df["Unternehmen"] == institution)
        ]
        total_registered = len(institution_data)
        total_participated = len(institution_data[institution_data["teilgenommen"]])

        if total_registered > 1 and 0 < total_participated < total_registered:
            mixed_participation_data.append(
                {
                    "Organisation": institution,
                    "Typ": kategorie,
                    "Angemeldet": total_registered,
                    "Teilgenommen": total_participated,
                    "Status": f"{total_participated} von {total_registered} Personen",
                }
            )

if mixed_participation_data:
    mixed_df = pd.DataFrame(mixed_participation_data)
    st.dataframe(mixed_df, use_container_width=True, hide_index=True)

    st.info(
        f"📊 **Wichtiger Hinweis**: {len(mixed_participation_data)} Organisationen haben nur teilweise teilgenommen. "
        + "Diese werden in der Besucherkennzahlen-Tabelle als 'teilnehmende Organisationen' gezählt, "
        + "obwohl nicht alle ihre Vertreter anwesend waren."
    )
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
    mime="text/csv",
    key="download_visitor_stats"
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
        mime="text/csv",
        key="download_csv_data"
    )

# Excel Export mit mehreren Sheets
with col2:
    st.write("**Vollständige Auswertung (Excel):**")

    # Excel-Daten vorbereiten
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: Bearbeitete Rohdaten
        processed_df.to_excel(writer, sheet_name="Teilnehmerdaten", index=False)

        # Sheet 2: Ergebnisse zusammenfassen
        results_data = []

        # Gesamtzahlen
        results_data.append(
            [
                "Kategorie",
                "Teilgenommen Personen",
                "Teilgenommen Institutionen",
                "Angemeldet Personen",
                "Angemeldet Institutionen",
            ]
        )
        results_data.append(
            [
                "Unternehmen",
                personen(teilgenommen_unternehmen),
                unternehmen(teilgenommen_unternehmen),
                personen(angemeldet_unternehmen),
                unternehmen(angemeldet_unternehmen),
            ]
        )

        # Kategorien
        for kategorie in kategorie_optionen:
            kategorie_alle = processed_df[processed_df["Kategorie"] == kategorie]
            kategorie_teilgenommen = kategorie_alle[kategorie_alle["teilgenommen"]]
            kategorie_angemeldet = kategorie_alle[~kategorie_alle["teilgenommen"]]

            teil_pers = personen(kategorie_teilgenommen)
            teil_org = unternehmen(kategorie_teilgenommen)
            ang_pers = personen(kategorie_angemeldet)
            ang_org = unternehmen(kategorie_angemeldet)

            if teil_pers > 0 or ang_pers > 0:
                results_data.append([kategorie, teil_pers, teil_org, ang_pers, ang_org])

        results_df = pd.DataFrame(results_data[1:], columns=results_data[0])
        results_df.to_excel(writer, sheet_name="Auswertung", index=False)

        # Sheet 3: Kategorien
        if len(processed_df) > 0:
            kategorien_data = []
            kategorien_data.append(
                [
                    "Kategorie",
                    "Teilgenommen Personen",
                    "Teilgenommen Organisationen",
                    "Angemeldet Personen",
                    "Angemeldet Organisationen",
                ]
            )

            for kategorie in kategorie_optionen:
                kategorie_alle = processed_df[processed_df["Kategorie"] == kategorie]
                kategorie_teilgenommen = kategorie_alle[kategorie_alle["teilgenommen"]]
                kategorie_angemeldet = kategorie_alle[~kategorie_alle["teilgenommen"]]

                teil_pers = personen(kategorie_teilgenommen)
                teil_org = unternehmen(kategorie_teilgenommen)
                ang_pers = personen(kategorie_angemeldet)
                ang_org = unternehmen(kategorie_angemeldet)

                if teil_pers > 0 or ang_pers > 0:
                    kategorien_data.append(
                        [kategorie, teil_pers, teil_org, ang_pers, ang_org]
                    )

            kategorien_df = pd.DataFrame(
                kategorien_data[1:], columns=kategorien_data[0]
            )
            kategorien_df.to_excel(writer, sheet_name="Kategorien", index=False)

    excel_data = output.getvalue()
    st.download_button(
        label="📊 Auswertung als Excel",
        data=excel_data,
        file_name=f"MDZ_Auswertung_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_data"
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
            "personen_aus_unternehmen_teilgenommen": personen(teilgenommen_unternehmen),
        },
        "kategorien": {},
        "generierter_text": text,
        "rohdaten": processed_df.to_dict("records"),
    }

    # Kategorien
    json_data["kategorien"] = {}
    for kategorie in kategorie_optionen:
        kategorie_alle = processed_df[processed_df["Kategorie"] == kategorie]
        kategorie_teilgenommen = kategorie_alle[kategorie_alle["teilgenommen"]]

        json_data["kategorien"][kategorie] = {
            "teilgenommen_personen": personen(kategorie_teilgenommen),
            "teilgenommen_organisationen": unternehmen(kategorie_teilgenommen),
            "angemeldet_personen": personen(kategorie_alle),
            "angemeldet_organisationen": unternehmen(kategorie_alle),
        }

    json_string = json.dumps(json_data, indent=2, ensure_ascii=False)
    st.download_button(
        label="🔧 Daten als JSON",
        data=json_string,
        file_name=f"MDZ_Daten_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        key="download_json_data"
    )

# Textbaustein als separate Datei
st.write("---")
st.write("**Textbaustein separat:**")
st.download_button(
    label="📝 Textbaustein als TXT",
    data=text,
    file_name=f"MDZ_Textbaustein_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
    mime="text/plain",
    key="download_text_data"
)

# ==============================
# DEBUG-INFORMATION
# ==============================

st.write("---")
st.write(f"**Debug**: {len(processed_df)} Zeilen nach Bereinigung, Spalten: {list(processed_df.columns)}")
