from flask import Flask, request, render_template

from svgpathtools.parser import parse_path
from svgpathtools import Path, Line, CubicBezier
from svgpathtools import paths2Drawing
from xml.dom.minidom import parse

import numpy as np

from flask import send_file

from io import StringIO, BytesIO

app = Flask(__name__)

@app.route("/", methods=['GET', 'POST'])
def hello_world():
    if request.method == 'POST':
        f = request.files['svg']
        print(f)
        doc = parse(f)
        paths, attributes, svg_attributes = dom2paths(doc)
        
        laser=np.array([[ float(request.form["laserx"]), 0],[ 0, float(request.form["lasery"]) ]])
        
        outlines = []
        for p in paths:
            if p.iscontinuous():
                if p.isclosed():
                    outlines.append(trace(p, laser))
            else:
                subs = p.continuous_subpaths()
                for sub in subs:
                    if sub.isclosed():
                        hole=False
                        if any([sub.is_contained_by(a) for a in subs if a!=sub]):
                            hole=True
                        outlines.append(trace(sub, laser,hole=hole))
                    else:
                        outlines.append(p)
        
        stroke = float(attributes[0]["stroke-width"])
        if "original" in request.form:
            svg = paths2Drawing(paths+outlines, "k"*len(paths)+"g"*len(outlines), svg_attributes = svg_attributes, stroke_widths=[stroke]*(len(paths)+len(outlines)))
        else:
            svg = paths2Drawing(outlines, "g"*len(outlines), svg_attributes = svg_attributes, stroke_widths=[stroke]*(len(outlines)))
        svg_io = StringIO()
        svg.write(svg_io)
        svg_io.seek(0)
        
        mem = BytesIO()
        mem.write(svg_io.getvalue().encode())
        # seeking was necessary. Python 3.5.2, Flask 0.12.2
        mem.seek(0)
        svg_io.close()
    
        return send_file(mem, mimetype='image/svg+xml')
    else:
        return render_template("main.html")
    
    
    
def dom2paths(doc,
              return_svg_attributes=True,
              convert_circles_to_paths=True,
              convert_ellipses_to_paths=True,
              convert_lines_to_paths=True,
              convert_polylines_to_paths=True,
              convert_polygons_to_paths=True,
              convert_rectangles_to_paths=True):
    """Converts an SVG into a list of Path objects and attribute dictionaries. 
    Converts an SVG file into a list of Path objects and a list of
    dictionaries containing their attributes.  This currently supports
    SVG Path, Line, Polyline, Polygon, Circle, and Ellipse elements.
    Args:
        svg_file_location (string): the location of the svg file
        return_svg_attributes (bool): Set to True and a dictionary of
            svg-attributes will be extracted and returned.  See also the 
            `svg2paths2()` function.
        convert_circles_to_paths: Set to False to exclude SVG-Circle
            elements (converted to Paths).  By default circles are included as 
            paths of two `Arc` objects.
        convert_ellipses_to_paths (bool): Set to False to exclude SVG-Ellipse
            elements (converted to Paths).  By default ellipses are included as 
            paths of two `Arc` objects.
        convert_lines_to_paths (bool): Set to False to exclude SVG-Line elements
            (converted to Paths)
        convert_polylines_to_paths (bool): Set to False to exclude SVG-Polyline
            elements (converted to Paths)
        convert_polygons_to_paths (bool): Set to False to exclude SVG-Polygon
            elements (converted to Paths)
        convert_rectangles_to_paths (bool): Set to False to exclude SVG-Rect
            elements (converted to Paths).
    Returns: 
        list: The list of Path objects.
        list: The list of corresponding path attribute dictionaries.
        dict (optional): A dictionary of svg-attributes (see `svg2paths2()`).
    """
    #doc = parse(svg_file_location)

    def dom2dict(element):
        """Converts DOM elements to dictionaries of attributes."""
        keys = list(element.attributes.keys())
        values = [val.value for val in list(element.attributes.values())]
        return dict(list(zip(keys, values)))

    # Use minidom to extract path strings from input SVG
    paths = [dom2dict(el) for el in doc.getElementsByTagName('path')]
    d_strings = [el['d'] for el in paths]
    attribute_dictionary_list = paths

    # Use minidom to extract polyline strings from input SVG, convert to
    # path strings, add to list
    if convert_polylines_to_paths:
        plins = [dom2dict(el) for el in doc.getElementsByTagName('polyline')]
        d_strings += [polyline2pathd(pl) for pl in plins]
        attribute_dictionary_list += plins

    # Use minidom to extract polygon strings from input SVG, convert to
    # path strings, add to list
    if convert_polygons_to_paths:
        pgons = [dom2dict(el) for el in doc.getElementsByTagName('polygon')]
        d_strings += [polygon2pathd(pg) for pg in pgons]
        attribute_dictionary_list += pgons

    if convert_lines_to_paths:
        lines = [dom2dict(el) for el in doc.getElementsByTagName('line')]
        d_strings += [('M' + l['x1'] + ' ' + l['y1'] +
                       'L' + l['x2'] + ' ' + l['y2']) for l in lines]
        attribute_dictionary_list += lines

    if convert_ellipses_to_paths:
        ellipses = [dom2dict(el) for el in doc.getElementsByTagName('ellipse')]
        d_strings += [ellipse2pathd(e) for e in ellipses]
        attribute_dictionary_list += ellipses

    if convert_circles_to_paths:
        circles = [dom2dict(el) for el in doc.getElementsByTagName('circle')]
        d_strings += [ellipse2pathd(c) for c in circles]
        attribute_dictionary_list += circles

    if convert_rectangles_to_paths:
        rectangles = [dom2dict(el) for el in doc.getElementsByTagName('rect')]
        d_strings += [rect2pathd(r) for r in rectangles]
        attribute_dictionary_list += rectangles

    if return_svg_attributes:
        svg_attributes = dom2dict(doc.getElementsByTagName('svg')[0])
        doc.unlink()
        path_list = [parse_path(d) for d in d_strings]
        return path_list, attribute_dictionary_list, svg_attributes
    else:
        doc.unlink()
        path_list = [parse_path(d) for d in d_strings]
        return path_list, attribute_dictionary_list


def scale_normal(c, laser, hole=False):
    if hole:
        c=-c
    normal_vec = [c.real,c.imag]
    corr_vec = laser.dot(normal_vec)
    shift = corr_vec[0]+corr_vec[1]*1j
    return shift

def fix_corner(old, new):
    ps = [old]
    try:
        intersect = old.intersect(new)
    except AssertionError:
        intersect=[]
    if len(intersect) == 0:
        olds = Line(old.point(1) - 100*old.unit_tangent(1), old.point(1) + 100*old.unit_tangent(1))
        cuts = Line(new.point(0) - 100*new.unit_tangent(0), new.point(0) + 100*new.unit_tangent(0))
        try:
            inter = olds.intersect(cuts)
        except AssertionError:
            inter = []
        if len(inter) == 0:
            ps.append(new)
        else:
            interp = olds.point(inter[0][0])
            ps+=[Line(old.end,interp), Line(interp,new.start), new]
    else:
        stay, drop = old.split(intersect[0][0])
        ps[-1]=stay
        drop, stay = new.split(intersect[0][1])
        ps.append(stay)
    return ps

def trace(zerop, laser, hole=False):
    tp=Path()
    for li in zerop:
        #print(li)
        if type(li)==CubicBezier:
            shift = scale_normal(li.normal(1), laser, hole)
            ends = li.translated(-shift)
            shift = scale_normal(li.normal(0), laser, hole)
            starts = li.translated(-shift)
            
            fix = ends.end - starts.end
            
            box = starts.bbox()
            rx = fix.real/(box[1]-box[0])
            ry = fix.imag/(box[3]-box[2])
            direct = starts.end - starts.start
            if direct.real > 0:
                if direct.imag > 0:
                    sx=1+rx
                    sy=1+ry
                else:
                    sx=1+rx
                    sy=1-ry
            else:
                if direct.imag > 0:
                    sx=1-rx
                    sy=1+ry
                else:
                    sx=1-rx
                    sy=1-ry
            interp = starts.scaled(sx,sy, origin=starts.start)
            tp.append(interp)
        elif type(li) == Line:
            shift=scale_normal(li.normal(), laser, hole)
            cut = li.translated(-shift)
            if len(tp)==0:
                tp.append(cut)
            else:
                ps = fix_corner(tp[-1],cut)
                tp[-1] = ps[0]
                tp+=ps[1:]
    ps = fix_corner(tp[-1],tp[0])
    tp[-1] = ps[0]
    tp+=ps[1:-1]
    tp[0] = ps[-1]
    return tp
