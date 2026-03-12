# MDZ Teilnehmer-Auswertung – Streamlit-Anwendung
## Projektbeschreibung für Claude Code

---

## Ziel des Projekts

Dieses Projekt dient der **Auswertung von Teilnehmenden an einer Veranstaltung** im Kontext von **Mittelstand-Digital (MDZ)**.

Ausgangspunkt ist **eine CSV-Datei mit ALLEN angemeldeten Personen**.  
Im Programm (Streamlit-Interface) wird **interaktiv markiert**, welche Personen **tatsächlich teilgenommen haben**.

Zielgrößen sind:
- Anzahl **teilnehmender Personen**
- Anzahl **teilnehmender Unternehmen (unique, ohne Doppelzählung)**
- Transparente Erklärung, **warum sich Personen- und Unternehmenszahlen unterscheiden**

Die Anwendung ist bewusst **einfach, nachvollziehbar und prüfsicher** aufgebaut.

---

## Technischer Stack

- Python 3.x
- pandas
- streamlit
- Kein virtuelles Environment zwingend erforderlich

Installation (minimal):
```bash
python -m pip install pandas streamlit
Start der Anwendung:

bash
Code kopieren
python -m streamlit run app.py
Grundannahmen (fachlich verbindlich)
CSV-Datei (Input)
Die CSV-Datei enthält alle angemeldeten Personen, nicht nur Teilnehmende.

Wichtige Annahmen:

Eine Zeile = eine Person

Mehrere Zeilen mit gleichem Unternehmensnamen = mehrere Personen aus demselben Unternehmen

Institutionen (z. B. Hochschulen, Kammern, Verbände) können enthalten sein

Die CSV wird nicht vorab gefiltert

Der Teilnahme-Status wird ausschließlich im Programm gesetzt

Erwartete Spalten in der CSV
Pflichtspalten:

Unternehmen

Unternehmensgröße

Weitere Spalten dürfen vorhanden sein, werden aber ignoriert.

Beispiel:

csv
Code kopieren
Unternehmen;Unternehmensgröße
Damm Consulting;1 bis 9 Mitarbeiter
EMIS;bis 500 Mitarbeiter
EMIS;bis 500 Mitarbeiter
BTU;mehr als 500 Mitarbeiter
Zähl- und Logikprinzipien
Personen
Anzahl Personen = Anzahl Zeilen

Filterbar in:

angemeldet, aber nicht teilgenommen

tatsächlich teilgenommen

Unternehmen
Unternehmen werden unique gezählt

Mehrere Personen eines Unternehmens zählen:

mehrfach als Personen

einmal als Unternehmen

Zentrales Prinzip
Personen ≠ Unternehmen
Diese Differenz ist erwartet und korrekt und wird explizit erklärt.

Streamlit-Interface – Funktionalität
Die Streamlit-App bietet:

1. CSV-Upload
Upload der vollständigen Angemeldetenliste

Validierung der erforderlichen Spalten

2. Interaktive Teilnahme-Markierung
Tabelle mit allen angemeldeten Personen

Checkbox-Spalte:

☑️ = hat teilgenommen

⬜ = nur angemeldet

Unternehmensname und Unternehmensgröße sind nicht editierbar

3. Automatische Auswertung
Getrennte Zählung von:

teilnehmenden Personen

teilnehmenden Unternehmen (unique)

nur angemeldeten (nicht teilgenommenen) Personen

Unternehmen mit mehreren teilnehmenden Personen

4. Transparente Erklärung
Die App zeigt:

wie viele Unternehmen mit:

1 Person

2 Personen

3+ Personen

explizite Liste der mehrfach vertretenen Unternehmen

5. Textbaustein (Output)
Automatisch generierter Text, z. B.:

„An der Veranstaltung nahmen 41 Personen aus 36 Unternehmen teil.
Mehrere Personen nahmen aus einzelnen Unternehmen teil, wodurch sich die Differenz zwischen Personen- und Unternehmensanzahl erklärt.“

Dieser Text ist direkt nutzbar für:

MDZ-Formulare

Verwendungsnachweise

Projektberichte

Explizit NICHT Bestandteil des Projekts
Um Fehlannahmen zu vermeiden, ist Folgendes nicht Teil der aktuellen Anwendung:

❌ automatische Trennung Unternehmen vs. Institutionen

❌ Förderlogik oder MDZ-spezifische Bewertung

❌ Datenbank oder Persistenz

❌ Benutzerverwaltung

❌ automatische Excel-Bearbeitung

❌ automatische Bereinigung oder Zusammenführung von Unternehmensnamen

Alle inhaltlichen Entscheidungen (z. B. welche Einträge als Unternehmen gelten) erfolgen außerhalb der App.

Erweiterbarkeit (bewusst optional)
Mögliche, aber aktuell nicht implementierte Erweiterungen:

Aufschlüsselung nach Unternehmensgröße

Export der Ergebnisse als CSV oder JSON

Speicherung des Checkbox-Status

Warnhinweise bei ungewöhnlich vielen Teilnehmenden aus einem Unternehmen

Normalisierung ähnlicher Unternehmensnamen (z. B. EMIS-Varianten)

Leitlinien für Weiterentwicklung
Bei jeder Änderung gelten folgende Prinzipien:

Nachvollziehbarkeit vor Automatisierung

Keine stillschweigenden Annahmen

Jede Zahl muss erklärbar sein

Keine Doppelzählung von Unternehmen

Trennung von Rohdaten (CSV) und Auswertelogik (App)

Wenn eine Erweiterung diese Prinzipien verletzt, muss sie explizit dokumentiert oder verworfen werden.

