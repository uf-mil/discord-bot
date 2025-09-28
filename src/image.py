from cairosvg import svg2png


def convert_svg_to_png(svg_filename) -> bytes | None:
    with open(svg_filename, "rb") as svg_file:
        svg_data = svg_file.read()
    png_data = svg2png(bytestring=svg_data, dpi=300, scale=10)
    return bytes(png_data) if png_data else None
