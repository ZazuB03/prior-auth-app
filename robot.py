import streamlit as st
from groq import Groq
from fpdf import FPDF
import pandas as pd
from datetime import datetime
import base64
import re

# ---- Configuratie ----
st.set_page_config(
    page_title="Prior Auth Pro",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---- Session State Initialisatie ----
if 'icpc_select' not in st.session_state:
    st.session_state.icpc_select = "L84"  # Default ICPC-code
if 'notitie' not in st.session_state:
    st.session_state.notitie = ""
if 'patienten' not in st.session_state:
    st.session_state.patienten = pd.DataFrame(columns=[
        "ID", "Datum", "Naam", "Verzekeraar", "ICPC", "Type", "Urgentie"
    ])
if 'snelkoppelingen' not in st.session_state:
    st.session_state.snelkoppelingen = {
        "MRI Rug": {"icpc": "L84", "text": "MRI lumbale wervelkolom ivm aanhoudende lage rugpijn met uitstraling"},
        "Fysio Knie": {"icpc": "K85", "text": "Fysiotherapie bij artrose van de knie"},
        "Dermatoloog": {"icpc": "H27", "text": "Verwijzing dermatoloog ivm therapieresistent eczeem"}
    }

# ---- CSS ----
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] {
        background-color: #f8f9fa;
    }
    .stTextArea textarea, .stTextInput input {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    .urgentie-hoog { background-color: #ffdddd !important; }
    .urgentie-gemiddeld { background-color: #fff3cd !important; }
    .urgentie-laag { background-color: #d4edda !important; }
    .icpc-highlight { font-weight: bold; color: #0056A6; }
</style>
""", unsafe_allow_html=True)

# ---- ICPC-codes ----
ICPCODES = {
    "L84": "Lage rugpijn", 
    "K85": "Artrose knie",
    "K86": "Artrose heup",
    "H27": "Constitutioneel eczeem",
    "R05": "Hoesten",
    "D84": "Diabetes type 2"
}

# ---- Verzekeraar templates ----
VERZEKERAAR_TEMPLATES = {
    "CZ": {
        "header": "CZ Zorgverzekering - Prior Auth Aanvraag",
        "fields": ["Aanvraagnummer", "Verzekeringsnr", "Poli"]
    },
    "VGZ": {
        "header": "VGZ Verzekeringen - Behandelingsverzoek",
        "fields": ["Kenmerk", "Verzekerdnr", "Behandelaar"]
    },
    "Menzis": {
        "header": "Menzis Zorgaanvraag",
        "fields": ["Dossiernr", "Patiënt-ID", "Regio"]
    }
}

# ---- Functies ----
def generate_form(inputs):
    """Genereer verzekeraarspecifiek formulier"""
    template = f"""
    **{VERZEKERAAR_TEMPLATES[inputs['verzekeraar']]['header']}**
    
    === PATIËNT ===
    Naam: {inputs['naam']}
    Geboortedatum: {inputs['geboortedatum']}
    Verzekeringsnr: {inputs['verzekeringsnr']}
    ICPC-code: {inputs['icpc']} ({ICPCODES.get(inputs['icpc'], 'Onbekend')})
    
    === AANVRAAG ===
    Type: {inputs['type']}
    Urgentie: {inputs['urgentie']}
    
    === MEDISCHE INDICATIE ===
    {inputs['notitie']}
    
    === VERKLARING ===
    Ik verklaar dat deze behandeling medisch noodzakelijk is.
    Datum: {datetime.now().strftime('%d-%m-%Y')}
    """
    
    try:
        client = Groq(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": template}],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"AI-fout: {str(e)}")
        return None

def create_pdf(content, verzekeraar):
    """Maak professionele PDF"""
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=VERZEKERAAR_TEMPLATES[verzekeraar]['header'], ln=1, align='C')
    
    # Body
    pdf.set_font("Arial", size=12)
    for line in content.split('\n'):
        if "===" in line:
            pdf.set_font('', 'B', 14)
            pdf.cell(0, 10, txt=line.replace('===', '').strip(), ln=1)
            pdf.set_font('', '', 12)
        else:
            pdf.multi_cell(0, 8, txt=line)
    
    return pdf.output(dest='S').encode('latin1')

def validate_insurance_nr(nr, verzekeraar):
    """Valideer verzekeringsnummer"""
    patterns = {
        "CZ": r"^[0-9]{4}\s?[0-9]{4}\s?[0-9]{4}$",
        "VGZ": r"^VGZ\d{8}$",
        "Menzis": r"^MZ\d{6}$"
    }
    return re.match(patterns.get(verzekeraar, r".*"), nr)

# ---- UI ----
with st.sidebar:
    st.title("⚙️ Instellingen")
    
    # ICPC-zoeker
    st.subheader("🔍 ICPC-code assistent")
    search_term = st.text_input("Zoek op symptoom")
    filtered_icpc = {k: v for k, v in ICPCODES.items() if search_term.lower() in v.lower()}
    selected_icpc = st.selectbox(
        "Selecteer code",
        options=list(filtered_icpc.keys()),
        format_func=lambda x: f"{x} - {filtered_icpc[x]}",
        key="icpc_select"
    )
    
    # Patiëntenhistorie
    st.subheader("📋 Recente aanvragen")
    st.dataframe(st.session_state.patienten.tail(5), hide_index=True)

# ---- Hoofdformulier ----
st.title("🏥 Prior Auth Pro")
st.markdown("""<div style='height: 2px; background: linear-gradient(90deg, #4CAF50, #2196F3); margin: 10px 0;'></div>""", 
            unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Patiëntgegevens
    with st.expander("👤 Patiëntgegevens", expanded=True):
        naam = st.text_input("Volledige naam*")
        geboortedatum = st.date_input("Geboortedatum*")
        verzekeringsnr = st.text_input("Verzekeringsnummer*")
        
    # Verzekeraar
    verzekeraar = st.radio(
        "Verzekeraar*",
        options=list(VERZEKERAAR_TEMPLATES.keys()),
        horizontal=True
    )

with col2:
    # Aanvraagdetails
    with st.expander("📄 Aanvraagdetails"):
        aanvraag_type = st.selectbox(
            "Type behandeling*",
            options=["MRI", "Fysiotherapie", "Specialist", "Diagnostiek", "Anders"]
        )
        urgentie = st.radio(
            "Urgentie*",
            options=["🔴 Hoog (binnen 48u)", "🟠 Gemiddeld (1-2 weken)", "🟢 Laag (planbaar)"],
            horizontal=True
        )
    
    # Snelkoppelingen
    st.subheader("🚀 Snelkoppelingen")
    cols = st.columns(3)
    for i, (name, data) in enumerate(st.session_state.snelkoppelingen.items()):
        with cols[i % 3]:
            if st.button(name):
                st.session_state.icpc_select = data["icpc"]
                st.session_state.notitie = data["text"]
                st.rerun()

# Medische motivatie
notitie = st.text_area(
    "Medische motivatie*",
    value=st.session_state.notitie,
    height=150,
    placeholder="Beschrijf symptomen, duur, eerdere behandelingen..."
)

# ---- Formulier genereren ----
if st.button("✅ Genereer Formulier", type="primary", use_container_width=True):
    if not all([naam, geboortedatum, verzekeringsnr, notitie]):
        st.warning("Vul alle verplichte velden in (met *)")
    else:
        inputs = {
            "naam": naam,
            "geboortedatum": geboortedatum.strftime("%d-%m-%Y"),
            "verzekeringsnr": verzekeringsnr,
            "verzekeraar": verzekeraar,
            "icpc": st.session_state.icpc_select,
            "type": aanvraag_type,
            "urgentie": urgentie,
            "notitie": notitie
        }
        
        with st.spinner("Formulier genereren..."):
            form_content = generate_form(inputs)
            
            if form_content:
                # Opslaan in historie
                new_id = f"{verzekeraar}-{datetime.now().strftime('%Y%m%d-%H%M')}"
                st.session_state.patienten.loc[len(st.session_state.patienten)] = {
                    "ID": new_id,
                    "Datum": datetime.now(),
                    "Naam": naam,
                    "Verzekeraar": verzekeraar,
                    "ICPC": st.session_state.icpc_select,
                    "Type": aanvraag_type,
                    "Urgentie": urgentie.split()[0]
                }
                
                # Resultaat tonen
                st.subheader("Resultaat")
                st.markdown(f"""
                <div class='icpc-highlight'>
                ICPC: {st.session_state.icpc_select} - {ICPCODES.get(st.session_state.icpc_select, '?')}
                </div>
                """, unsafe_allow_html=True)
                
                urgentie_class = {
                    "🔴": "urgentie-hoog",
                    "🟠": "urgentie-gemiddeld",
                    "🟢": "urgentie-laag"
                }[urgentie.split()[0]]
                
                st.markdown(f"""
                <div class='{urgentie_class}' style='padding: 15px; border-radius: 5px;'>
                {form_content.replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)
                
                # PDF genereren
                pdf_bytes = create_pdf(form_content, verzekeraar)
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"prior_auth_{new_id}.pdf",
                    mime="application/pdf",
                    type="primary"
                )

# ---- Footer ----
st.divider()
st.caption(f"⚡ AI gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')} | v1.3")