# BillFlow icon assets

`icon.svg` is the source of truth. The mark is the existing BillFlow "B"
monogram on a rounded square; it is recolored to the BillFlow palette from
`CONTRACT.md`:

| Colour | Hex | Use |
| --- | --- | --- |
| Black | `#0A0A0A` | square background |
| White | `#FFFFFF` | the "B" monogram |
| Orange | `#FF6A00` | accent dot only |

No other colours, gradients or shadows are used.

Generated binaries checked into this folder:

- `icon.png` — 256 x 256 RGBA, used by the Linux `.desktop` launcher and AppImage.
- `icon.ico` — multi-size Windows icon (16/32/48/64/128/256), used by the
  portable bundle and the Inno Setup installer.

These files are build-time artefacts only. The native app has **no runtime
dependency** on any image tool, Python or Node.

## Regenerating the raster files

Any of the following works from the repository root (pick what is installed):

```bash
# librsvg
rsvg-convert -w 256 -h 256 assets/icon.svg -o assets/icon.png

# Inkscape
inkscape assets/icon.svg --export-type=png --export-width=256 --export-height=256 -o assets/icon.png

# ImageMagick
convert -background none -density 1152 assets/icon.svg -resize 256x256 assets/icon.png

# Python + cairosvg (build-time only)
python3 -c "import cairosvg; cairosvg.svg2png(url='assets/icon.svg', output_width=256, output_height=256, write_to='assets/icon.png')"
```

Then build the Windows ICO from the PNG:

```bash
# ImageMagick
convert assets/icon.png -define icon:auto-resize=256,128,64,48,32,16 assets/icon.ico

# Python + Pillow (build-time only)
python3 -c "from PIL import Image; im=Image.open('assets/icon.png'); im.save('assets/icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
```
