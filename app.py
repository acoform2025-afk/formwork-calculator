# app.py - Aluminum Formwork Calculator (Hybrid Mode)
# Manual input + DXF-assisted calculation with full transparency.

import streamlit as st
import ezdxf
from ezdxf import units
import tempfile
import os
import math

st.set_page_config(page_title="Formwork Calculator", page_icon="📐")
st.title("📐 Aluminum Formwork – Area & Price Calculator")
st.markdown("Choose a mode: **Manual** (enter dimensions) or **DXF Assisted** (upload a drawing).")

# ---------- Helper: price & quote display ----------
def show_quote(area_m2, price_per_sqm, drawing_name=None):
    if area_m2 > 0:
        st.success(f"✅ **Total formwork area: {area_m2:.2f} m²**")
        total = area_m2 * price_per_sqm
        st.success(f"💰 **Estimated quote: ${total:,.2f} USD**")
        if st.button("Generate full quote"):
            st.subheader("📄 Final Quotation")
            if drawing_name:
                st.write(f"**Drawing:** {drawing_name}")
            st.write(f"**Calculated area:** {area_m2:.2f} m²")
            st.write(f"**Unit price:** ${price_per_sqm:.2f} / m²")
            st.write(f"**Total amount:** **${total:,.2f} USD**")
            st.balloons()
    else:
        st.warning("No area calculated. Please check inputs.")

# ---------- Mode selection ----------
mode = st.radio("Select input mode", ["Manual entry", "DXF Assisted upload"])

price_per_sqm = st.number_input("Your price per square meter (USD)", min_value=0.0, value=45.0, step=5.0)

# ============================================
# MODE 1: MANUAL ENTRY (following your formulas)
# ============================================
if mode == "Manual entry":
    st.subheader("➕ Add structural elements")
    
    # Initialize session state to store components
    if "components" not in st.session_state:
        st.session_state.components = []
    
    col1, col2 = st.columns(2)
    with col1:
        comp_type = st.selectbox("Component type", ["Wall (both sides)", "Wall (one side)", "Column (rectangular)", 
                                                    "Column (circular)", "Beam", "Slab (ceiling)", "Stair (projection)"])
    with col2:
        add_clicked = st.button("➕ Add this component")
    
    # Input fields based on type
    if comp_type == "Wall (both sides)":
        length = st.number_input("Length (m)", 0.0, 100.0, 5.0)
        height = st.number_input("Height (m)", 0.0, 10.0, 3.0)
        area = 2 * length * height
        desc = f"Wall 2 sides: {length}m x {height}m"
    elif comp_type == "Wall (one side)":
        length = st.number_input("Length (m)", 0.0, 100.0, 5.0)
        height = st.number_input("Height (m)", 0.0, 10.0, 3.0)
        area = length * height
        desc = f"Wall 1 side: {length}m x {height}m"
    elif comp_type == "Column (rectangular)":
        length = st.number_input("Length (m)", 0.0, 10.0, 0.45)
        width = st.number_input("Width (m)", 0.0, 10.0, 0.45)
        height = st.number_input("Height (m)", 0.0, 20.0, 3.6)
        perimeter = 2 * (length + width)
        area = perimeter * height
        desc = f"Rect. column: {length}x{width}m, h={height}m"
    elif comp_type == "Column (circular)":
        diameter = st.number_input("Diameter (m)", 0.0, 5.0, 0.5)
        height = st.number_input("Height (m)", 0.0, 20.0, 3.6)
        area = math.pi * diameter * height
        desc = f"Circ. column: dia={diameter}m, h={height}m"
    elif comp_type == "Beam":
        length = st.number_input("Length (m)", 0.0, 100.0, 4.0)
        depth = st.number_input("Depth (m)", 0.0, 2.0, 0.5)
        width = st.number_input("Width (m)", 0.0, 1.0, 0.3)
        area = length * (2 * depth + width)
        desc = f"Beam: {length}m, {depth}x{width}m"
    elif comp_type == "Slab (ceiling)":
        length = st.number_input("Length (m)", 0.0, 100.0, 6.0)
        width = st.number_input("Width (m)", 0.0, 100.0, 4.0)
        area = length * width
        desc = f"Slab: {length}x{width}m"
    else:  # Stair
        proj_length = st.number_input("Horizontal projection length (m)", 0.0, 50.0, 3.0)
        proj_width = st.number_input("Horizontal projection width (m)", 0.0, 10.0, 1.2)
        area = proj_length * proj_width
        desc = f"Stair projection: {proj_length}x{proj_width}m"
    
    if add_clicked and area > 0:
        st.session_state.components.append({"desc": desc, "area": area})
        st.success(f"Added: {desc} → {area:.2f} m²")
    
    # Display component list and total
    if st.session_state.components:
        st.subheader("📋 Component list")
        total_manual = 0.0
        for i, comp in enumerate(st.session_state.components):
            st.write(f"{i+1}. {comp['desc']} – **{comp['area']:.2f} m²**")
            total_manual += comp['area']
        st.subheader(f"🏗️ Total formwork area (manual): {total_manual:.2f} m²")
        
        if st.button("Clear all components"):
            st.session_state.components = []
            st.rerun()
        
        show_quote(total_manual, price_per_sqm)
    else:
        st.info("Add at least one component to see the total area and quote.")

# ============================================
# MODE 2: DXF ASSISTED (transparent + manual override)
# ============================================
else:
    st.subheader("📂 Upload a DXF drawing")
    uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])
    
    if uploaded_file is not None:
        # Store in session state to avoid reprocessing every rerun
        if "dxf_area" not in st.session_state:
            st.session_state.dxf_area = None
            st.session_state.dxf_unit_desc = None
            st.session_state.dxf_entities = None
        
        # Process the file only once
        if st.session_state.dxf_area is None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            try:
                doc = ezdxf.readfile(tmp_path)
                msp = doc.modelspace()
                
                # Entity count
                lines = len(list(msp.query("LINE")))
                polylines = len(list(msp.query("LWPOLYLINE POLYLINE")))
                blocks = len(list(msp.query("INSERT")))
                total_entities = lines + polylines + blocks
                st.session_state.dxf_entities = total_entities
                
                # Unit detection
                doc_units = doc.units
                if doc_units == units.M:
                    sf = 1.0
                    unit_desc = "meters"
                elif doc_units == units.CM:
                    sf = 0.01
                    unit_desc = "centimeters"
                elif doc_units == units.MM:
                    sf = 0.001
                    unit_desc = "millimeters"
                elif doc_units == units.INCH:
                    sf = 0.0254
                    unit_desc = "inches"
                else:
                    sf = 1.0
                    unit_desc = "unknown (assuming meters)"
                
                # Try to compute area from closed polylines
                total_area_units = 0.0
                for poly in msp.query("LWPOLYLINE POLYLINE"):
                    if poly.closed:
                        points = []
                        if poly.dxftype() == "LWPOLYLINE":
                            points = [(x, y) for x, y in poly.vertices()]
                        else:
                            points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        if len(points) >= 3:
                            # Use shapely for area
                            try:
                                from shapely.geometry import Polygon
                                poly_shapely = Polygon(points)
                                total_area_units += poly_shapely.area
                            except:
                                pass
                st.session_state.dxf_area = total_area_units * (sf ** 2)
                st.session_state.dxf_unit_desc = unit_desc
            except Exception as e:
                st.error(f"Error reading DXF: {e}")
                st.session_state.dxf_area = -1
            finally:
                os.unlink(tmp_path)
        
        # Display results
        if st.session_state.dxf_area == -1:
            st.error("Could not parse the DXF file. Please try another file or switch to Manual mode.")
        else:
            st.write(f"**File name:** {uploaded_file.name}")
            st.write(f"**Entities found:** {st.session_state.dxf_entities} (lines, polylines, blocks)")
            st.write(f"**Detected units:** {st.session_state.dxf_unit_desc}")
            st.info("⚠️ Automatic area calculation from DXF is often inaccurate due to scaling and geometry issues. Please verify below.")
            
            auto_area = st.session_state.dxf_area if st.session_state.dxf_area else 0.0
            st.metric("Automatically calculated area (m²)", f"{auto_area:.2f}")
            
            # Manual override
            st.subheader("✏️ Manual override")
            corrected_area = st.number_input("Enter correct area (m²) if auto is wrong", min_value=0.0, value=max(auto_area, 0.0), step=10.0)
            
            if corrected_area > 0:
                show_quote(corrected_area, price_per_sqm, uploaded_file.name)
            else:
                st.warning("Enter a positive area or use Manual mode.")