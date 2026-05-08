# app.py - Aluminum Formwork Area & Price Calculator (Final Version)
# Handles unit scaling (meters, cm, mm, inches) and can merge individual line segments.

import streamlit as st
import ezdxf
from ezdxf import units
import shapely.geometry
from shapely.geometry import Polygon, MultiLineString
import shapely.ops
import tempfile
import os

# ---------- Page setup ----------
st.set_page_config(page_title="Formwork Area Calculator", page_icon="📐")
st.title("📐 Aluminum Formwork Area & Price Calculator")
st.markdown("Upload a DXF drawing – the app automatically detects units and calculates total formwork area.")

# ---------- File uploader ----------
uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])

# ---------- Price input ----------
price_per_sqm = st.number_input("Your price per square meter (USD)", min_value=0.0, value=45.0, step=5.0)

# ---------- Core calculation function (handles units & line merging) ----------
def calculate_area_from_dxf(file_bytes):
    """
    Reads a DXF file, detects drawing units, finds all closed shapes,
    and returns total area in square meters.
    """
    # Save uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        
        # --- Determine unit scaling factor ---
        doc_units = doc.units
        if doc_units == units.M:
            scale_factor = 1.0          # 1 drawing unit = 1 meter
            unit_desc = "meters"
        elif doc_units == units.CM:
            scale_factor = 0.01         # 1 unit = 1 cm = 0.01 m
            unit_desc = "centimeters"
        elif doc_units == units.MM:
            scale_factor = 0.001        # 1 unit = 1 mm = 0.001 m
            unit_desc = "millimeters"
        elif doc_units == units.INCH:
            scale_factor = 0.0254       # 1 inch = 0.0254 m
            unit_desc = "inches"
        else:
            # If units are missing, assume meters (most common in architectural CAD)
            st.warning("Drawing units not specified in file. Assuming meters.")
            scale_factor = 1.0
            unit_desc = "meters (assumed)"
        
        total_area = 0.0
        
        # --- 1) First pass: closed polylines & polygons ---
        for entity in msp.query("LWPOLYLINE POLYLINE"):
            if entity.closed:
                points = []
                if entity.dxftype() == "LWPOLYLINE":
                    points = [(x, y) for x, y in entity.vertices()]
                else:  # POLYLINE
                    points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                
                if len(points) >= 3:
                    poly = Polygon(points)
                    area_in_sq_units = poly.area
                    total_area += area_in_sq_units * (scale_factor ** 2)
        
        # --- 2) Second pass: if no closed polylines found, try merging LINE entities ---
        if total_area == 0.0:
            line_entities = msp.query("LINE")
            if line_entities:
                # Collect start and end points of each LINE
                segments = []
                for line in line_entities:
                    start = line.dxf.start
                    end = line.dxf.end
                    if start and end:
                        segments.append(((start.x, start.y), (end.x, end.y)))
                
                if segments:
                    # Convert to a MultiLineString and try to merge
                    multiline = MultiLineString(segments)
                    merged = shapely.ops.linemerge(multiline)
                    
                    # If the merged result is a Polygon, we can calculate its area
                    if isinstance(merged, Polygon):
                        area_in_sq_units = merged.area
                        total_area = area_in_sq_units * (scale_factor ** 2)
                        st.info("📐 The drawing used individual line segments; they were merged into a closed shape.")
                    elif merged.geom_type == 'MultiLineString':
                        # Try to find the largest closed loop
                        for geom in merged.geoms:
                            if geom.is_ring:  # closed linestring
                                poly = Polygon(geom)
                                area_in_sq_units = poly.area
                                total_area += area_in_sq_units * (scale_factor ** 2)
                        if total_area > 0:
                            st.info("📐 Merged line segments – area calculated from the largest closed loop.")
        
        return total_area, unit_desc
        
    except Exception as e:
        st.error(f"Error reading DXF: {e}")
        return None, None
    finally:
        os.unlink(tmp_path)  # Clean up temporary file

# ---------- Main logic: process uploaded file ----------
if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    area, unit_desc = calculate_area_from_dxf(file_bytes)
    
    if area is not None and area > 0:
        st.success(f"✅ **Total formwork area: {area:.2f} square meters**")
        st.caption(f"(Drawing units: {unit_desc})")
        
        total_price = area * price_per_sqm
        st.success(f"💰 **Estimated quote: ${total_price:,.2f} USD**")
        
        # Optional: generate a formal quote
        if st.button("Generate full quote"):
            st.subheader("📄 Final Quotation")
            st.write(f"**Customer drawing:** {uploaded_file.name}")
            st.write(f"**Calculated area:** {area:.2f} m²")
            st.write(f"**Unit price:** ${price_per_sqm:.2f} / m²")
            st.write(f"**Total amount:** **${total_price:,.2f} USD**")
            st.balloons()
    elif area is not None and area == 0:
        st.warning("No closed shapes found. The DXF may contain only lines that do not form a closed boundary, or the drawing is empty.")
    else:
        st.error("Could not calculate area. Please check the file format or upload a different DXF.")