from cairosvg import svg2png


def convert_svg_to_png(svg_filename) -> bytes | None:
    with open(svg_filename, "rb") as svg_file:
        svg_data = svg_file.read()
    try:
        png_data = svg2png(bytestring=svg_data, dpi=300, scale=10)
    # This catches all Exceptions due to svg2png's reliance on several underlying libraries,
    # which could emit various exceptions when trying to parse the SVG, or generate the PNG.
    except Exception:
        png_data = None
    return bytes(png_data) if png_data else None
