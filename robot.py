import streamlit as st
from groq import Groq
from fpdf import FPDF
import pandas as pd
from datetime import datetime
import base64
import re
import time
from PIL import Image
import io
import hashlib

# ---- Configuratie ----
st.set_page_config(
    page_title="Prior Auth AI Pro",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---- Geheimen ----
@st.cache_data
def load_secrets():
    return {
        "GROQ_KEY": st.secrets["OPENAI_API_KEY"],
        "FHIR_ENDPOINT": st.secrets.get("FHIR_ENDPOINT", ""),
        "SIGNATURE_KEY": st.secrets.get("SIGNATURE_KEY", "")
    }

secrets = load_secrets()

# ---- Databases ----
if 'patienten_db' not in st.session_state:
    st.session_state.patienten_db = pd.DataFrame(columns=[
        "id", "timestamp", "naam", "geboortedatum", "verzekeraar", 
        "urgentie", "icpc", "aanvraag_type", "notitie", "formulier",
        "epd_id", "ondertekend"
    ])

if 'verzekeraar_templates' not in st.session_state:
    st.session_state.verzekeraar_templates = {
        "CZ": {
            "header": "CZ Zorgverzekeringen\nAanvraag Prior Authorisatie",
            "footer": "Verzekerdnr: [POLISNR]\nAanvraagnummer: [AUTO]"
        },
        "VGZ": {
            "header": "VGZ Prior Auth Formulier\nDossiernr: [AUTO]",
            "footer": "Behandelcode: [SPECIALISME]\nVerzekerdnr: [POLISNR]"
        },
        "Menzis": {
            "header": "Menzis Zorgaanvraag\nDatum: [DD-MM-YYYY]",
            "footer": "Declaratiecode: [AUTO]\nVerzekerdnr: [POLISNR]"
        }
    }

# ---- Functies ----
class PDFGenerator:
    def __init__(self, verzekeraar):
        self.pdf = FPDF()
        self.verzekeraar = verzekeraar
        self.logo = {
            "CZ": "cz_logo.png",
            "VGZ": "vgz_logo.png",
            "Menzis": "menzis_logo.png"
        }.get(verzekeraar, "generic_logo.png")
        
    def add_header(self):
        self.pdf.add_page()
        self.pdf.set_font("Arial", 'B', 16)
        self.pdf.cell(200, 10, txt=st.session_state.verzekeraar_templates[self.verzekeraar]["header"], ln=1, align='C')
        self.pdf.ln(10)
        
    def add_content(self, text):
        self.pdf.set_font("Arial", size=12)
        for line in text.split('\n'):
            if line.startswith("==="):
                self.pdf.set_font('', 'B', 14)
                self.pdf.cell(0, 10, txt=line.replace('===', '').strip(), ln=1)
                self.pdf.set_font('', '', 12)
            else:
                self.pdf.multi_cell(0, 8, txt=line)
                
    def add_footer(self, signature=None):
        self.pdf.ln(10)
        self.pdf.set_font('', 'I', 10)
        self.pdf.multi_cell(0, 5, txt=st.session_state.verzekeraar_templates[self.verzekeraar]["footer"])
        if signature:
            self.pdf.image(signature, x=160, y=250, w=30)
        self.pdf.set_font('', 'I', 8)
        self.pdf.cell(0, 10, txt=f" gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=1)
        
    def generate(self, content, signature=None):
        self.add_header()
        self.add_content(content)
        self.add_footer(signature)
        return self.pdf.output(dest='S').encode('latin1')

def validate_dutch_phone(tel):
    return re.match(r'^(\+31|0)[0-9]{9,11}$', tel)

def validate_bsn(bsn):
    return re.match(r'^[0-9]{8,9}$', bsn)

def generate_signature(naam):
    """Simpele digitale handtekening (voor demo)"""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(10, 10, f"Digitale handtekening: {naam}")
    c.drawString(10, 30, datetime.now().strftime("%d-%m-%Y %H:%M"))
    c.save()
    
    packet.seek(0)
    return packet.getvalue()

def icpc_suggestions(query):
    """ICPC-code autocomplete"""
    codes = {
        "rugpijn": "L84",
        "artrose": "L89",
        "diabetes": "T90",
        "hypertensie": "K86"
    }
    return [v for k,v in codes.items() if query.lower() in k]

# ---- UI Components ----
def patient_form():
    with st.expander("👤 Patiëntgegevens", expanded=True):
        cols = st.columns(3)
        with cols[0]:
            naam = st.text_input("Volledige naam*")
        with cols[1]:
            geboortedatum = st.date_input("Geboortedatum*")
        with cols[2]:
            bsn = st.text_input("BSN (optioneel)", help="Voor EPD koppeling")
            
        cols = st.columns(2)
        with cols[0]:
            tel = st.text_input("Telefoonnummer (optioneel)")
            if tel and not validate_dutch_phone(tel):
                st.warning("Voer geldig NL nummer in (06 of +31)")
        with cols[1]:
            email = st.text_input("E-mail (optioneel)")
            
        return {
            "naam": naam,
            "geboortedatum": geboortedatum,
            "bsn": bsn,
            "tel": tel,
            "email": email
        }

def insurance_form():
    with st.expander("🏦 Verzekeringsgegevens"):
        cols = st.columns(2)
        with cols[0]:
            verzekeraar = st.selectbox("Verzekeraar*", ["CZ", "VGZ", "Menzis"])
        with cols[1]:
            verzekeringsnr = st.text_input("Verzekeringsnummer*")
            
        return {
            "verzekeraar": verzekeraar,
            "verzekeringsnr": verzekeringsnr
        }

def request_form():
    with st.expander("📄 Aanvraagdetails"):
        cols = st.columns(3)
        with cols[0]:
            aanvraag_type = st.selectbox("Type aanvraag*", 
                ["MRI", "Fysiotherapie", "Specialist", "Operatie", "Anders"])
        with cols[1]:
            icpc_query = st.text_input("ICPC-code zoeken", key="icpc_search")
            if icpc_query:
                st.caption(f"Suggesties: {', '.join(icpc_suggestions(icpc_query))}")
            icpc = st.text_input("ICPC-code*", value=icpc_suggestions(icpc_query)[0] if icpc_query else "")
        with cols[2]:
            urgentie = st.radio("Urgentie*", 
                ["🔴 Hoog (binnen 48u)", "🟠 Gemiddeld (1-2 weken)", "🟢 Laag (planbaar)"],
                horizontal=True)
                
        notitie = st.text_area("Medische motivatie*", height=150,
            placeholder="Beschrijf symptomen, voorgeschiedenis en noodzaak...")
            
        return {
            "type": aanvraag_type,
            "icpc": icpc,
            "urgentie": urgentie,
            "notitie": notitie
        }

# ---- Hoofdapplicatie ----
def main():
    st.title("🏥 Prior Auth AI Pro")
    st.markdown("""<div style='height: 2px; background: linear-gradient(90deg, #4CAF50, #2196F3); margin: 10px 0;'></div>""", 
                unsafe_allow_html=True)
    
    # Formulier secties
    patient_data = patient_form()
    insurance_data = insurance_form()
    request_data = request_form()
    
    # Handtekening
    signature = None
    if st.checkbox("📝 Digitale handtekening toevoegen"):
        signature = generate_signature(patient_data["naam"])
        st.image(signature, width=150)
    
    # Generatie
    if st.button("🔄 Genereer Prior Auth", type="primary", use_container_width=True):
        if not all([patient_data["naam"], patient_data["geboortedatum"], 
                  insurance_data["verzekeraar"], insurance_data["verzekeringsnr"],
                  request_data["notitie"]]):
            st.warning("Vul alle verplichte velden in (met *)")
        else:
            with st.spinner("AI genereert formulier..."):
                # Combineer alle data
                form_data = {**patient_data, **insurance_data, **request_data}
                form_data["geboortedatum"] = form_data["geboortedatum"].strftime("%d-%m-%Y")
                
                # AI Generatie
                prompt = f"""
                **Prior Auth Formulier ({form_data['verzekeraar']})**
                
                === PATIËNTGEGEVENS ===
                Naam: {form_data['naam']}
                Geboortedatum: {form_data['geboortedatum']}
                Verzekeringsnr: {form_data['verzekeringsnr']}
                ICPC-code: {form_data['icpc']}
                
                === AANVRAAG ===
                Type: {form_data['type']}
                Urgentie: {form_data['urgentie']}
                
                === MEDISCHE INDICATIE ===
                {form_data['notitie']}
                
                === VERANTWOORDING ===
                Medische noodzaak: [AI genereert hier een beknopte motivatie]
                
                Gebruik exact dit format en Nederlandse medische terminologie.
                """
                
                try:
                    client = Groq(api_key=secrets["GROQ_KEY"])
                    response = client.chat.completions.create(
                        model="llama3-70b-8192",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                    form_content = response.choices[0].message.content
                    
                    # Opslaan in database
                    new_id = hashlib.sha256(f"{datetime.now()}{form_data['naam']}".encode()).hexdigest()[:8]
                    new_entry = {
                        "id": new_id,
                        "timestamp": datetime.now(),
                        **form_data,
                        "formulier": form_content[:500] + "...",
                        "ondertekend": bool(signature)
                    }
                    st.session_state.patienten_db.loc[len(st.session_state.patienten_db)] = new_entry
                    
                    # Toon resultaat
                    st.success("Formulier succesvol gegenereerd!")
                    with st.expander("🔍 Bekijk formulier", expanded=True):
                        st.markdown(f"```\n{form_content}\n```")
                        
                    # PDF generatie
                    pdf_gen = PDFGenerator(form_data['verzekeraar'])
                    pdf_bytes = pdf_gen.generate(form_content, signature)
                    
                    # Download knop
                    st.download_button(
                        label="📥 Download PDF",
                        data=pdf_bytes,
                        file_name=f"prior_auth_{new_id}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
                except Exception as e:
                    st.error(f"Fout tijdens genereren: {str(e)}")

# ---- Sidebar ----
with st.sidebar:
    st.title("⚙️ Dashboard")
    
    if st.button("🔄 Vernieuw database"):
        st.session_state.patienten_db = st.session_state.patienten_db.sort_values("timestamp", ascending=False)
        st.rerun()
        
    st.metric("Totaal aanvragen", len(st.session_state.patienten_db))
    
    with st.expander("📋 Patiëntenoverzicht"):
        st.dataframe(
            st.session_state.patienten_db[["id", "naam", "verzekeraar", "timestamp"]],
            hide_index=True,
            use_container_width=True
        )
    
    with st.expander("🔎 Zoek patiënt"):
        search_term = st.text_input("Naam/BSN")
        if search_term:
            results = st.session_state.patienten_db[
                st.session_state.patienten_db["naam"].str.contains(search_term, case=False) |
                st.session_state.patienten_db["bsn"].str.contains(search_term)
            ]
            st.dataframe(results[["id", "naam", "verzekeraar"]], hide_index=True)

# ---- Snelstart ----
st.divider()
st.subheader("🚀 Snelstart")
cols = st.columns(4)
template_actions = {
    "MRI Rug": "MRI lumbale wervelkolom ivm aanhoudende lage rugpijn met uitstraling naar been",
    "Fysio Knie": "Aanvraag fysiotherapie bij artrose van de knie (ICPC L89)",
    "Cardioloog": "Verwijzing cardioloog ivm ritmestoornissen",
    "Dermatoloog": "Verwijzing dermatoloog ivm psoriasis"
}

for col, (label, template) in zip(cols, template_actions.items()):
    with col:
        if st.button(label, use_container_width=True):
            st.session_state["notitie"] = template
            st.rerun()

# ---- Start App ----
if __name__ == "__main__":
    main()