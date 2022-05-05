# Ellipse Burn

This tool is useful if you use a laser cutter with an elliptical focus point.
Many CAM tools support a burn/kerf value for a circular correction of cutting width.
However this is not precise if the correction needs to be direction dependent.
Therefore I created this small tool to cut the amazing boxes from https://www.festi.info/boxes.py/
with tight tolerances on all finger joints.

## Usage

The easiest way is to use the online service at
https://ellipseburn.nlogn.org/

Provide the radius in x and y direction of the focus. Please check first with the output of the original path.
To use for cutting, uncheck the `output original` to only get the cutting path.

### Local

If you are uncomfortable uploading your SVGs, you can run the service locally with python

    FLASK_APP=burn flask run

and then access it locally at http://localhost:5000/

## Example

The green line shows the toolpath for a focus which is stretched in the y direction.

![example.svg](example.svg)
