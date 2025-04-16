import streamlit as st
from groq import Groq
from fpdf import FPDF
import base64
import time

# ---- Configuratie ----
st.set_page_config(
    page_title="AI Prior Auth Assistent",
    page_icon="🏥",
    layout="wide"
)

# Fix voor onzichtbare tekst
st.markdown("""
<style>
    .stTextArea textarea {
        color: #000000 !important;
    }
    .stTextArea label {
        color: #000000 !important;
        font-weight: bold !important;
    }
    .stButton>button {
        background-color: #4CAF50 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ---- Groq Client ----
try:
    client = Groq(api_key="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")  # 👈 Vervang dit!
except Exception as e:
    st.error(f"Groq initialisatiefout: {str(e)}")
    st.stop()

# ---- Functies ----
def generate_form(note):
    """Genereer formulier met Llama 3"""
    prompt = f"""
    Je bent een Nederlandse AI-assistent voor huisartsen. Vul dit prior auth formulier in volgens onderstaand format:

    === PATIËNTGEGEVENS ===
    Naam: [Auto]
    Leeftijd: [Auto]
    Verzekeringsnummer: [Auto]
    Verzekeraar: [Zorgverzekeraar]

    === MEDISCHE INDICATIE ===
    Primaire diagnose: [DIAGNOSE]
    ICD-10 code: [Auto]
    Symptomen: {note}
    Relevant medisch verleden: [Auto]
    Urgentie: [Laag/Medium/Hoog]

    === AANVRAAG ===
    Type behandeling: [MRI/Fysiotherapie/etc.]
    Frequentie: [1x/week etc.]
    Verwachte duur: [Aantal weken]
    Alternatieven geprobeerd: [Auto]

    === VERANTWOORDING ===
    Medische noodzaak: [Beknopte motivatie]

    Gebruik uitsluitend Nederlandse medische terminologie en houd het professioneel.
    """
    
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"AI-fout: {str(e)}")
        return None

def create_pdf(text, filename="prior_auth.pdf"):
    """Maak PDF van de tekst"""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 10, txt=text)
        pdf.output(filename)
        return filename
    except Exception as e:
        st.error(f"PDF-fout: {str(e)}")
        return None

# ---- UI ----
with st.sidebar:
    st.image("https://i.imgur.com/XYZ123.png", width=200)  # Voeg eigen logo toe
    st.markdown("### Instellingen")
    st.info("""
    **Gebruiksaanwijzing:**
    1. Plak patiëntinformatie
    2. Klik 'Genereer Formulier'
    3. Download en controleer PDF
    """)

st.title("🏥 Prior Auth Formulier Generator")
st.markdown("Automatisch zorgverzekeringsformulieren invullen met AI")

# ---- Hoofdcontent ----
note = st.text_area(
    "**Patiëntnotitie:**",
    height=200,
    placeholder="Bijv.: 'Pat. heeft sinds 3 maanden chronische lage rugpijn met uitstraling naar been...'",
    key="patient_notes"
)

if st.button("🔄 Genereer Formulier", type="primary"):
    if not note.strip():
        st.warning("Voer eerst een patiëntnotitie in!")
    else:
        with st.spinner("AI genereert formulier... Dit duurt ~10 seconden"):
            start_time = time.time()
            
            # Genereer inhoud
            form_content = generate_form(note)
            
            if form_content:
                # Toon resultaat
                st.subheader("Resultaat:")
                st.markdown(f"""
                <div style='background-color: #f0f0f0; padding: 15px; border-radius: 5px;'>
                {form_content}
                </div>
                """, unsafe_allow_html=True)
                
                # Maak PDF
                pdf_path = create_pdf(form_content)
                
                if pdf_path:
                    # Download knop
                    with open(pdf_path, "rb") as f:
                        pdf_data = f.read()
                    b64 = base64.b64encode(pdf_data).decode()
                    
                    st.download_button(
                        label="📥 Download PDF",
                        data=pdf_data,
                        file_name="prior_auth.pdf",
                        mime="application/pdf",
                        help="Sla het formulier op als PDF"
                    )
                    
                    st.success(f"Formulier gegenereerd in {time.time()-start_time:.1f} seconden")
                else:
                    st.error("PDF kon niet worden aangemaakt")
            else:
                st.error("Formulier genereren mislukt")

# ---- Footer ----
st.divider()
st.caption("""
Gebouwd met 🦙 Llama 3 via Groq | Voor Nederlandse huisartsen
""")