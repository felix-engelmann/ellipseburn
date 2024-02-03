from flask import Flask, request, render_template

from svgpathtools.parser import parse_path
from svgpathtools import Path, Line, CubicBezier, concatpaths, path_encloses_pt, Arc
from svgpathtools import paths2Drawing
from xml.dom.minidom import parse

import re
import numpy as np

from flask import send_file

from io import StringIO, BytesIO

app = Flask(__name__)



COORD_PAIR_TMPLT = re.compile(
    r'([\+-]?\d*[\.\d]\d*[eE][\+-]?\d+|[\+-]?\d*[\.\d]\d*)' +
    r'(?:\s*,\s*|\s+|(?=-))' +
    r'([\+-]?\d*[\.\d]\d*[eE][\+-]?\d+|[\+-]?\d*[\.\d]\d*)'
)


def path2pathd(path):
    return path.get('d', '')


def ellipse2pathd(ellipse):
    """converts the parameters from an ellipse or a circle to a string for a 
    Path object d-attribute"""

    cx = ellipse.get('cx', 0)
    cy = ellipse.get('cy', 0)
    rx = ellipse.get('rx', None)
    ry = ellipse.get('ry', None)
    r = ellipse.get('r', None)

    if r is not None:
        rx = ry = float(r)
    else:
        rx = float(rx)
        ry = float(ry)

    cx = float(cx)
    cy = float(cy)

    d = ''
    d += 'M' + str(cx - rx) + ',' + str(cy)
    d += 'a' + str(rx) + ',' + str(ry) + ' 0 1,0 ' + str(2 * rx) + ',0'
    d += 'a' + str(rx) + ',' + str(ry) + ' 0 1,0 ' + str(-2 * rx) + ',0'

    return d + 'z'


def polyline2pathd(polyline, is_polygon=False):
    """converts the string from a polyline points-attribute to a string for a
    Path object d-attribute"""
    if isinstance(polyline, str):
        points = polyline
    else:
        points = COORD_PAIR_TMPLT.findall(polyline.get('points', ''))

    closed = (float(points[0][0]) == float(points[-1][0]) and
              float(points[0][1]) == float(points[-1][1]))

    # The `parse_path` call ignores redundant 'z' (closure) commands
    # e.g. `parse_path('M0 0L100 100Z') == parse_path('M0 0L100 100L0 0Z')`
    # This check ensures that an n-point polygon is converted to an n-Line path.
    if is_polygon and closed:
        points.append(points[0])

    d = 'M' + 'L'.join('{0} {1}'.format(x,y) for x,y in points)
    if is_polygon or closed:
        d += 'z'
    return d


def polygon2pathd(polyline):
    """converts the string from a polygon points-attribute to a string 
    for a Path object d-attribute.
    Note:  For a polygon made from n points, the resulting path will be
    composed of n lines (even if some of these lines have length zero).
    """
    return polyline2pathd(polyline, True)


def rect2pathd(rect):
    """Converts an SVG-rect element to a Path d-string.
    
    The rectangle will start at the (x,y) coordinate specified by the 
    rectangle object and proceed counter-clockwise."""
    x, y = float(rect.get('x', 0)), float(rect.get('y', 0))
    w, h = float(rect.get('width', 0)), float(rect.get('height', 0))
    if 'rx' in rect or 'ry' in rect:

        # if only one, rx or ry, is present, use that value for both
        # https://developer.mozilla.org/en-US/docs/Web/SVG/Element/rect
        rx = rect.get('rx', None)
        ry = rect.get('ry', None)
        if rx is None:
            rx = ry or 0.
        if ry is None:
            ry = rx or 0.
        rx, ry = float(rx), float(ry)

        d = "M {} {} ".format(x + rx, y)  # right of p0
        d += "L {} {} ".format(x + w - rx, y)  # go to p1
        d += "A {} {} 0 0 1 {} {} ".format(rx, ry, x+w, y+ry)  # arc for p1
        d += "L {} {} ".format(x+w, y+h-ry)  # above p2
        d += "A {} {} 0 0 1 {} {} ".format(rx, ry, x+w-rx, y+h)  # arc for p2
        d += "L {} {} ".format(x+rx, y+h)  # right of p3
        d += "A {} {} 0 0 1 {} {} ".format(rx, ry, x, y+h-ry)  # arc for p3
        d += "L {} {} ".format(x, y+ry)  # below p0
        d += "A {} {} 0 0 1 {} {} z".format(rx, ry, x+rx, y)  # arc for p0
        return d

    x0, y0 = x, y
    x1, y1 = x + w, y
    x2, y2 = x + w, y + h
    x3, y3 = x, y + h

    d = ("M{} {} L {} {} L {} {} L {} {} z"
         "".format(x0, y0, x1, y1, x2, y2, x3, y3))
        
    return d


def line2pathd(l):
    return (
        'M' + l.attrib.get('x1', '0') + ' ' + l.attrib.get('y1', '0')
        + 'L' + l.attrib.get('x2', '0') + ' ' + l.attrib.get('y2', '0')
    )

def unifypoints(paths, mdist):
    points = {}
    for pid,path in enumerate(paths):
        for s in ["start","end"]:
            for point in points.keys():
                if point != getattr(path,s) and abs(point-getattr(path,s)) <  mdist:
                    setattr(paths[pid],s,point)
                    #print("unified")
                    points[getattr(path, s)].append(pid)
                    break
            else:
                points[getattr(path,s)] = [pid]
    return paths

def joinpaths(paths):
    np = []
    consumed = set()
    foundany = False
    for pi, path in enumerate(paths):
        if pi in consumed:
            continue
        foundcon = False
        for ci,conn in enumerate(paths):
            if ci <= pi or ci in consumed:
                continue
            for dp in [path, path.reversed()]:
                for dc in [conn, conn.reversed()]:
                    if dp.end == dc.start:
                        np.append(concatpaths([dp,dc]))
                        consumed.add(ci)
                        foundcon = True
                        break
                if foundcon:
                    break
            if foundcon:
                break
        if foundcon:
            foundany = True
        else:
            np.append(path)
    if foundany:
        return joinpaths(np)
    return np

@app.route("/", methods=['GET', 'POST'])
def hello_world():
    if request.method == 'POST':
        f = request.files['svg']
        print(f)
        doc = parse(f)
        paths, attributes, svg_attributes = dom2paths(doc)

        try:
            laser=np.array([[ float(request.form.get("laserx",0.0)), 0],[ 0, float(request.form.get("lasery",0.0)) ]])
        except:
            laser = np.array([[1, 0], [0, 1]])
        inv = "invert" in request.form

        mdist = float(request.form.get("mdistance", 1e-03))

        arcsegn = int(request.form.get("arcsegments", 50))

        paths = unifypoints(paths, mdist)
        print("unified points")
        paths = joinpaths(paths)
        print("joined paths")


        outlines = []
        if "join" not in request.form:
            for nthp,p in enumerate(paths):
                if p.iscontinuous():
                    if p.isclosed():
                        hole = False
                        if any([p.is_contained_by(a) for a in paths if a != p and a.isclosed()]):
                            hole = True
                        outlines.append(trace(p, laser, hole=hole ^ inv, arcsegn=arcsegn))
                else:
                    subs = p.continuous_subpaths()
                    for sub in subs:
                        if sub.isclosed():
                            hole=False
                            if any([sub.is_contained_by(a) for a in subs if a!=sub]):
                                hole=True
                            outlines.append(trace(sub, laser,hole=hole ^ inv, arcsegn=arcsegn))
                        else:
                            outlines.append(p)
                print("outlined", nthp, "/", len(paths))

        outlines = list(filter(lambda x: len(x) > 0, outlines))
        
        stroke = float(attributes[0].get("stroke-width",0.0899589))
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

def trace(zerop, laser, hole=False, arcsegn=50):
    tp=Path()
    first = zerop[0]
    wrong = path_encloses_pt(first.point(0.5)+(first.normal(0.5)*0.01), -100000+100000j, zerop)
    if wrong:
        hole = not hole
    for li in zerop:
        #print(li)
        if type(li) == Arc:
            parts = arcsegn
            for i in range(parts):
                partli = Line(li.point(i/parts),li.point((i+1)/parts))
                shift = scale_normal(partli.normal(), laser, hole)
                cut = partli.translated(-shift)
                if len(tp) == 0:
                    tp.append(cut)
                else:
                    ps = fix_corner(tp[-1], cut)
                    tp[-1] = ps[0]
                    tp += ps[1:]

        elif type(li)==CubicBezier:
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
        else:
            print("unknown type", type(li))
    if len(tp) > 0:
        ps = fix_corner(tp[-1],tp[0])
        tp[-1] = ps[0]
        tp+=ps[1:-1]
        tp[0] = ps[-1]
    return tp
