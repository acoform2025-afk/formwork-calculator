# app.py - Aluminum Formwork Calculator (Hybrid Mode)
# Improved DXF processing with polygonization and manual scale override.

import streamlit as st
import ezdxf
from ezdxf import units
import tempfile
import os
import math
from shapely.geometry import LineString, Polygon, MultiLineString
from shapely.ops import polygonize, linemerge
import numpy as np

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
# MODE 1: MANUAL ENTRY (unchanged, works well)
# ============================================
if mode == "Manual entry":
    st.subheader("➕ Add structural elements")
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
# MODE 2: DXF ASSISTED (improved polygonization)
# ============================================
else:
    st.subheader("📂 Upload a DXF drawing")
    uploaded_file = st.file_uploader("Choose a DXF file", type=["dxf"])
    
    if uploaded_file is not None:
        # Session state for caching
        if "dxf_area" not in st.session_state:
            st.session_state.dxf_area = None
            st.session_state.dxf_unit_desc = None
            st.session_state.dxf_entity_count = None
            st.session_state.dxf_polygon_count = None
        
        # Manual scale override input (shown before processing)
        scale_override = st.number_input(
            "Manual scale factor (leave 0 to auto-detect):\n1 unit = ? meters (e.g., 0.001 for mm, 0.0254 for inches)",
            min_value=0.0, value=0.0, step=0.0001, format="%f"
        )
        
        # Process only once
        if st.session_state.dxf_area is None and uploaded_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            
            try:
                doc = ezdxf.readfile(tmp_path)
                msp = doc.modelspace()
                
                # --- 1. Collect all line segments from relevant entities ---
                segments = []
                
                # Helper to add a segment between two points
                def add_seg(p1, p2):
                    segments.append(LineString([(p1.x, p1.y), (p2.x, p2.y)]))
                
                # LINEs
                for line in msp.query("LINE"):
                    add_seg(line.dxf.start, line.dxf.end)
                
                # LWPOLYLINE and POLYLINE (explode into segments)
                for poly in msp.query("LWPOLYLINE POLYLINE"):
                    points = []
                    if poly.dxftype() == "LWPOLYLINE":
                        points = [(x, y) for x, y in poly.vertices()]
                    else:
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                    if len(points) >= 2:
                        for i in range(len(points)-1):
                            segments.append(LineString([points[i], points[i+1]]))
                        if poly.closed and len(points) >= 3:
                            segments.append(LineString([points[-1], points[0]]))
                
                # ARCs (approximate by chord or small segments)
                for arc in msp.query("ARC"):
                    # Convert arc to a set of line segments (simplify)
                    center = arc.dxf.center
                    radius = arc.dxf.radius
                    start_angle = arc.dxf.start_angle
                    end_angle = arc.dxf.end_angle
                    # Use 20 segments for smoothness
                    num_seg = max(4, int(abs(end_angle - start_angle) / 10))
                    angles = np.linspace(start_angle, end_angle, num_seg+1)
                    pts = [(center.x + radius*math.cos(np.radians(a)), center.y + radius*math.sin(np.radians(a))) for a in angles]
                    for i in range(len(pts)-1):
                        segments.append(LineString([pts[i], pts[i+1]]))
                
                # CIRCLEs (approximate by polygon)
                for circle in msp.query("CIRCLE"):
                    center = circle.dxf.center
                    radius = circle.dxf.radius
                    num_seg = 36
                    angles = np.linspace(0, 360, num_seg+1)
                    pts = [(center.x + radius*math.cos(np.radians(a)), center.y + radius*math.sin(np.radians(a))) for a in angles]
                    for i in range(len(pts)-1):
                        segments.append(LineString([pts[i], pts[i+1]]))
                
                # --- 2. Merge collinear segments and polygonize ---
                if len(segments) == 0:
                    st.warning("No geometry found in the DXF file.")
                    st.session_state.dxf_area = 0.0
                else:
                    # Merge overlapping/collinear lines
                    merged = linemerge(MultiLineString(segments))
                    # Polygonize the merged linework
                    polygons = list(polygonize(merged))
                    st.session_state.dxf_polygon_count = len(polygons)
                    
                    # --- 3. Determine scale factor ---
                    if scale_override > 0:
                        sf = scale_override
                        unit_desc = f"manual override (1 unit = {scale_override} m)"
                    else:
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
                            # Default: assume meters, but warn
                            sf = 1.0
                            unit_desc = "unknown (assuming meters). Use manual scale if wrong."
                            st.warning("No unit information in DXF. Assuming 1 drawing unit = 1 meter. You can override below.")
                    
                    # --- 4. Calculate total area in square meters ---
                    total_area = 0.0
                    for poly in polygons:
                        if poly.is_valid and not poly.is_empty:
                            total_area += poly.area * (sf ** 2)
                    
                    st.session_state.dxf_area = total_area
                    st.session_state.dxf_unit_desc = unit_desc
                    st.session_state.dxf_entity_count = len(segments)
            
            except Exception as e:
                st.error(f"Error processing DXF: {e}")
                st.session_state.dxf_area = -1
            finally:
                os.unlink(tmp_path)
        
        # Display results
        if st.session_state.dxf_area == -1:
            st.error("Failed to process DXF. Please try another file or switch to Manual mode.")
        else:
            st.write(f"**File name:** {uploaded_file.name}")
            if st.session_state.dxf_entity_count is not None:
                st.write(f"**Line segments extracted:** {st.session_state.dxf_entity_count}")
            if st.session_state.dxf_polygon_count is not None:
                st.write(f"**Closed polygons formed:** {st.session_state.dxf_polygon_count}")
            st.write(f"**Unit scale:** {st.session_state.dxf_unit_desc}")
            
            auto_area = st.session_state.dxf_area if st.session_state.dxf_area else 0.0
            st.metric("Automatically calculated area (m²)", f"{auto_area:.2f}")
            
            # Manual override input for area (final adjustment)
            st.subheader("✏️ Manual override (final area)")
            corrected_area = st.number_input("Enter correct area (m²) if auto is wrong", min_value=0.0, value=float(auto_area), step=10.0)
            
            if corrected_area > 0:
                show_quote(corrected_area, price_per_sqm, uploaded_file.name)
            else:
                st.warning("Enter a positive area to generate a quote.")