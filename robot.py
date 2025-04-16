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
</style>
""", unsafe_allow_html=True)

# ---- Initialisatie ----
if 'patienten' not in st.session_state:
    st.session_state.patienten = pd.DataFrame(columns=["ID", "Datum", "Naam", "Geboortedatum", "Verzekeraar", "Urgentie", "Notitie", "Formulier"])

# ---- Functies ----
def generate_form(inputs):
    """Genereer formulier met context-specifieke template"""
    templates = {
        "CZ": "CZ-template: Aanvraagnummer [AUTO], Behandelaar [NAAM]",
        "VGZ": "VGZ-template: Kenmerk [AUTO], Verzekerdnr [NR]",
        "Menzis": "Menzis-template: Dossier [AUTO]"
    }
    
    prompt = f"""
    **Prior Auth Formulier ({inputs['verzekeraar']})**
    
    === PATIËNT ===
    Naam: {inputs['naam']}
    Geboortedatum: {inputs['geboortedatum']}
    Verzekeringsnr: [AUTO]
    
    === AANVRAAG ===
    Type: {inputs['type']}
    Urgentie: {inputs['urgentie']}
    ICD-10: {inputs['icpc']}
    
    === MEDISCHE INDICATIE ===
    {inputs['notitie']}
    
    Gebruik exact dit format en Nederlandse medische terminologie.
    """
    
    try:
        client = Groq(api_key=st.secrets["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
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
    pdf.cell(200, 10, txt=f"Prior Auth - {verzekeraar}", ln=1, align='C')
    
    # Body
    pdf.set_font("Arial", size=12)
    for line in content.split('\n'):
        if "===" in line:
            pdf.set_font('', 'B', 14)
            pdf.cell(0, 10, txt=line.replace('===', '').strip(), ln=1)
            pdf.set_font('', '', 12)
        else:
            pdf.multi_cell(0, 8, txt=line)
    
    # Footer
    pdf.set_y(-15)
    pdf.set_font('', 'I', 8)
    pdf.cell(0, 10, txt=f" gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=1)
    
    return pdf.output(dest='S').encode('latin1')

def validate_phone(tel):
    """Valideer Nederlands telefoonnummer"""
    return re.match(r'^(\+31|0)[0-9]{9,11}$', tel)

# ---- UI ----
with st.sidebar:
    st.title("⚙️ Instellingen")
    st.image("https://i.imgur.com/XYZ123.png", width=200)
    
    st.selectbox("Thema", ["Licht", "Donker"], key="theme")
    
    if st.button("📋 Patiëntenoverzicht"):
        st.dataframe(st.session_state.patienten, hide_index=True)

# ---- Hoofdformulier ----
st.title("🏥 Prior Auth Pro")
st.markdown("""<div style='height: 2px; background: linear-gradient(90deg, #4CAF50, #2196F3); margin: 10px 0;'></div>""", 
            unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Patiëntgegevens
    with st.expander("👤 Patiëntgegevens", expanded=True):
        naam = st.text_input("Volledige naam")
        geboortedatum = st.date_input("Geboortedatum")
        tel = st.text_input("Telefoonnummer (optioneel)")
        if tel and not validate_phone(tel):
            st.warning("Voer een geldig NL nummer in (06 of +31)")
        
    # Verzekering
    with st.expander("🏦 Verzekeraar"):
        verzekeraar = st.selectbox("Selecteer", ["CZ", "VGZ", "Menzis"])
        verzekeringsnr = st.text_input("Verzekeringsnummer")
        
with col2:
    # Aanvraag
    with st.expander("📄 Aanvraagdetails"):
        aanvraag_type = st.selectbox("Type", ["MRI", "Fysiotherapie", "Specialist", "Anders"])
        icpc = st.text_input("ICPC-code", placeholder="Bijv. L84 voor rugpijn")
        
        urgentie = st.radio("Urgentie", 
                           ["🔴 Hoog (binnen 48u)", "🟠 Gemiddeld (1-2 weken)", "🟢 Laag (planbaar)"],
                           horizontal=True)
    
    # Notitie
    notitie = st.text_area("Medische motivatie", height=150,
                          placeholder="Beschrijf symptomen, voorgeschiedenis en noodzaak...")

# ---- Generatie ----
if st.button("🔄 Genereer Formulier", type="primary", use_container_width=True):
    if not all([naam, geboortedatum, verzekeraar, notitie]):
        st.warning("Vul verplichte velden in (naam, geboortedatum, verzekeraar, notitie)")
    else:
        inputs = {
            "naam": naam,
            "geboortedatum": geboortedatum.strftime("%d-%m-%Y"),
            "verzekeraar": verzekeraar,
            "type": aanvraag_type,
            "icpc": icpc,
            "urgentie": urgentie,
            "notitie": notitie
        }
        
        with st.spinner("AI genereert formulier..."):
            form_content = generate_form(inputs)
            
            if form_content:
                # Opslaan in database
                new_id = len(st.session_state.patienten) + 1
                new_entry = {
                    "ID": new_id,
                    "Datum": datetime.now(),
                    **inputs,
                    "Formulier": form_content[:500] + "..."
                }
                st.session_state.patienten.loc[len(st.session_state.patienten)] = new_entry
                
                # Toon resultaat
                st.subheader("Resultaat:")
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
                
                # PDF generatie
                pdf_bytes = create_pdf(form_content, verzekeraar)
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"prior_auth_{new_id}.pdf",
                    mime="application/pdf"
                )

# ---- Snelkoppelingen ----
st.divider()
st.subheader("🚀 Snelstart")
cols = st.columns(3)
with cols[0]:
    if st.button("MRI Rug", help="Standaard MRI-aanvraag"):
        st.session_state["notitie"] = "MRI lumbale wervelkolom ivm aanhoudende lage rugpijn met uitstraling"
with cols[1]:
    if st.button("Fysiotherapie"):
        st.session_state["notitie"] = "Aanvraag fysiotherapie bij artrose van de knie"
with cols[2]:
    if st.button("Cardioloog"):
        st.session_state["notitie"] = "Verwijzing cardioloog ivm ritmestoornissen"

# ---- Footer ----
st.divider()
st.caption("""
⚡ Powered by Groq (Llama 3) | 📅 Versie {datetime.now().strftime('%d-%m-%Y')}
""")