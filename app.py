# app.py - Aluminum Formwork Area & Price Calculator
# Created with Streamlit - no coding knowledge needed to use the final app

import streamlit as st
import ezdxf
import shapely.geometry
import tempfile
import os

# ---------- Page setup ----------
st.set_page_config(page_title="Formwork Calculator", page_icon="📐")
st.title("📐 Aluminum Formwork - Area & Price Calculator")
st.markdown("Upload a DXF drawing, enter your price per square meter, and get an instant quote.")

# ---------- File uploader ----------
uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])

# ---------- Price input ----------
price_per_sqm = st.number_input("Your price per square meter (USD)", min_value=0.0, value=45.0, step=5.0)

# ---------- Area calculation function (the "brain") ----------
def calculate_area_from_dxf(file_bytes):
    """
    Reads a DXF file, finds all closed polylines, and returns total area.
    """
    # Save uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        total_area = 0.0

        # Find all closed polylines (LWPOLYLINE and POLYLINE)
        for entity in msp.query("LWPOLYLINE POLYLINE"):
            if entity.closed:
                # Extract vertices
                points = []
                if entity.dxftype() == "LWPOLYLINE":
                    points = [(x, y) for x, y in entity.vertices()]
                else:  # POLYLINE
                    points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                
                if len(points) >= 3:
                    poly = shapely.geometry.Polygon(points)
                    total_area += poly.area

        return total_area

    except Exception as e:
        st.error(f"Error reading DXF: {e}")
        return None
    finally:
        os.unlink(tmp_path)  # Clean up temporary file

# ---------- Main logic: process uploaded file ----------
if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    area = calculate_area_from_dxf(file_bytes)

    if area is not None and area > 0:
        st.success(f"✅ **Total formwork area: {area:.2f} square meters**")
        
        total_price = area * price_per_sqm
        st.success(f"💰 **Estimated quote: ${total_price:,.2f} USD**")
        
        # Optional: show a button to generate a formal quote
        if st.button("Generate full quote"):
            st.subheader("📄 Final Quotation")
            st.write(f"**Customer drawing:** {uploaded_file.name}")
            st.write(f"**Calculated area:** {area:.2f} m²")
            st.write(f"**Unit price:** ${price_per_sqm:.2f} / m²")
            st.write(f"**Total amount:** **${total_price:,.2f} USD**")
            st.balloons()
    elif area is not None and area == 0:
        st.warning("No closed shapes found in the DXF file. Make sure the drawing contains closed polylines.")
    else:
        st.error("Could not calculate area. Please check the file format.")