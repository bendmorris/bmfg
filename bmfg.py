import argparse
import os
import lxml.etree as ET
import pygame
import pygame.freetype
import rectpack

DEFAULT_CHARS = r''' !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~'''
SPECIAL_CHARS = {
    ' ': 'space'
}

def parse_color(c):
    if len(c) == 6:
        c += 'ff'
    elif len(c) != 8:
        raise Exception("Invalid color: {} (use RRGGBB or RRGGBBAA)".format(c))
    val = int(c, 16)
    return pygame.Color((val >> 24) & 0xff,
                        (val >> 16) & 0xff,
                        (val >> 8) & 0xff,
                        val & 0xff)

def set_alpha(surface, alpha):
    if alpha < 0xff:
        surface.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)

def upconvert(src_surface):
    surface = pygame.Surface((src_surface.get_width(), src_surface.get_height()), flags=pygame.SRCALPHA)
    surface.blit(src_surface, (0, 0))
    return surface

def premultiply_alpha(surface):
    #return pygame.image.fromstring(pygame.image.tostring(surface, 'RGBA_PREMULT'), surface.get_size(), 'RGBA')
    import numpy as np
    array = pygame.surfarray.pixels3d(surface)
    alpha = pygame.surfarray.pixels_alpha(surface)
    array[:,:,:] *= np.uint8(alpha[:,:,None] / 255.)

def overflow(n):
    if (n > 0 and n & 0x80000000):
        n -= 0x100000000
    return n

def run(args):
    pygame.display.init()
    pygame.freetype.init()

    output_path = args.output or args.input_file
    output_name = os.path.splitext(os.path.basename(output_path))[0]
    output_dir = os.path.dirname(output_path)

    font_size = args.size
    base_size = args.base_size or font_size
    scale = float(font_size)/base_size
    visible_chars = sorted(set(args.chars))
    antialiasing = hasattr(args, 'antialiasing') and args.antialiasing
    color = parse_color(args.color)
    background_color = parse_color(args.background)
    border_color = parse_color(args.border_color)
    pt = args.padding if args.padding_top is None else args.padding_top
    pb = args.padding if args.padding_bottom is None else args.padding_bottom
    pl = args.padding if args.padding_left is None else args.padding_left
    pr = args.padding if args.padding_right is None else args.padding_right
    border_width = args.border
    max_texture_size = args.max_texture_size
    texture_square = args.square
    pretty_print = args.pretty_print
    premultiply = args.premultiply
    kerning = args.kerning
    char_spacing = args.char_spacing
    line_spacing = args.line_spacing

    border_width = int(border_width * scale + 0.5)
    char_spacing = int(char_spacing * scale + 0.5)
    line_spacing = int(line_spacing * scale + 0.5)

    font = pygame.freetype.Font(args.input_file, font_size)
    font.antialiased = antialiasing
    if kerning:
        font.kerning = True
    surfaces = {}

    removed = set()
    for char in visible_chars:
        if font.get_metrics(char)[0] is None:
            removed.add(char)
    if removed:
        print('Removed the following unsupported chars: ' + ''.join(removed))
        visible_chars = [x for x in visible_chars if x not in removed]

    print('Rendering characters...')
    for char in visible_chars:
        bgcolor = pygame.Color(color.r, color.g, color.b, 0)
        glyph, rect = font.render(char, fgcolor=color, bgcolor=bgcolor)
        surface = upconvert(glyph)
        set_alpha(surface, color.a)
        w = surface.get_width() + pl + pr + border_width * 2
        h = surface.get_height() + pt + pb + border_width * 2
        char_surface = pygame.Surface((w, h), flags=pygame.SRCALPHA)
        if border_width > 0:
            glyph_surface, _ = font.render(char, fgcolor=border_color, bgcolor=bgcolor)
            border_surface = pygame.Surface((w, h), flags=pygame.SRCALPHA)
            for a in range(0, border_width * 2 + 2):
                for b in range(0, border_width * 2 + 2):
                    _a, _b = a - border_width, b - border_width
                    if ((_a * _a + _b * _b) ** 0.5) < border_width:
                        border_surface.blit(glyph_surface, (pl + a, pt + b))

            glyph, _ = font.render(char, fgcolor=pygame.Color(255, 255, 255, 255))
            glyph_mask = pygame.Surface((glyph.get_width(), glyph.get_height()), flags=pygame.SRCALPHA)
            glyph_mask.blit(glyph, (0, 0))
            border_surface.blit(glyph_mask, (pl + border_width, pt + border_width), special_flags=pygame.BLEND_RGBA_SUB)
            set_alpha(border_surface, border_color.a)
            char_surface.blit(border_surface, (0, 0))
        char_surface.blit(surface, (pl + border_width, pt + border_width))
        surfaces[char] = char_surface

    if kerning:
        print('Generating kerning data...')
        kerning_data = {}
        for char1 in visible_chars:
            for char2 in visible_chars:
                w1 = font.get_rect(char1).width
                w2 = font.get_rect(char2).width
                wc = font.get_rect(char1 + char2).width
                if wc != w1 + w2:
                    kerning_data[(char1, char2)] = wc - w1 - w2

    print('Packing...')
    sizes = [128]
    while sizes[-1] * 2 <= max_texture_size:
        sizes.append(sizes[-1] * 2)
    texture_width, texture_height = sizes[0], sizes[0] / 2
    while texture_height < sizes[-1]:
        if texture_height < texture_width:
            texture_height *= 2
        else:
            texture_width *= 2
        packer = rectpack.newPacker(rotation=False)
        packer.add_bin(texture_width, texture_height, count=len(visible_chars))

        for char, surface in surfaces.items():
            packer.add_rect(surface.get_width(), surface.get_height(), char)

        packer.pack()

        if len(packer) == 1:
            break

    if texture_square and texture_height < texture_width:
        texture_height = texture_width
    textures = {}

    print('Generating textures...')
    for b, x, y, w, h, char in packer.rect_list():
        b += 1
        if b not in textures:
            textures[b] = pygame.Surface((texture_width, texture_height), flags=pygame.SRCALPHA)
            textures[b].fill(background_color)
        textures[b].blit(surfaces[char], (x, y))

    texture_pages = []
    for texture_id, texture in textures.items():
        if texture_id > 1:
            filename = os.path.join(output_dir, '{}_{}.png'.format(output_name, texture_id))
        else:
            filename = os.path.join(output_dir, '{}.png'.format(output_name))
        print('Saving {}...'.format(filename))
        texture_pages.append(os.path.basename(filename))
        if premultiply:
            premultiply_alpha(texture)
        pygame.image.save(texture, filename)

    print('Generating font atlas...')
    line_height = font.get_sized_height()
    filename = os.path.join(output_dir, '{}.fnt'.format(output_name))
    root = ET.Element("font")
    info = ET.SubElement(root, "info", {'size': str(font_size), 'face': font.name})
    common = ET.SubElement(root, "common", {'lineHeight': str(line_height + line_spacing + border_width * 2)})
    pages = ET.SubElement(root, "pages")
    for page_id, page in enumerate(texture_pages):
        ET.SubElement(pages, "page", {'id': str(page_id), 'file': page})
    chars = ET.SubElement(root, "chars", {'count': str(len(visible_chars))})
    for b, x, y, w, h, char in packer.rect_list():
        (min_x, max_x, min_y, max_y, x_advance, _) = font.get_metrics(char)[0]
        min_x, max_x, min_y, max_y = map(overflow, (min_x, max_x, min_y, max_y))
        attrib = {}
        attrib['id'] = str(ord(char))
        attrib['width'] = str(w - pl - pr)
        attrib['page'] = str(b)
        attrib['x'] = str(x + pl)
        attrib['y'] = str(y + pt)
        attrib['chnl'] = '0'
        attrib['letter'] = SPECIAL_CHARS.get(char, char)
        attrib['height'] = str(h - pt - pb)
        attrib['xoffset'] = str(min_x)
        attrib['yoffset'] = str(line_height - h + line_spacing - min_y + border_width * 2)
        attrib['xadvance'] = str(int(x_advance + 0.5 + char_spacing + border_width * 2))
        ET.SubElement(chars, "char", attrib)
    if kerning:
        kernings = ET.SubElement(root, "kernings", {'count': str(len(kerning_data))})
        for (c1, c2), amt in kerning_data.items():
            attrib = {
                'first': str(ord(c1)),
                'second': str(ord(c2)),
                'amount': str(amt),
            }
            ET.SubElement(root, "kerning", attrib)
    tree = ET.ElementTree(root)
    with open(filename, 'w') as output_file:
        output_file.write(ET.tostring(tree, pretty_print=pretty_print))

    print('Done')
    pygame.quit()

def main():
    parser = argparse.ArgumentParser(description='bmfg')
    parser.add_argument('input_file', help='path to font file; output files will be saved in this directory')
    parser.add_argument('--output', '-o', nargs='?', default=None,
                        help='output file path (extension ignored, none for same as input file)')
    parser.add_argument('--size', '-s',
                        type=int, default=64,
                        help='font size')
    parser.add_argument('--base-size',
                        type=int, default=None,
                        help='if provided, scale borders/spacing by size/base-size')
    parser.add_argument('--padding', '-p', type=int, default=2,
                        help='padding (all sides)')
    parser.add_argument('--padding-top',
                        type=int, default=None,
                        help='top padding (overrides --padding)')
    parser.add_argument('--padding-bottom',
                        type=int, default=None,
                        help='bottom padding (overrides --padding)')
    parser.add_argument('--padding-left',
                        type=int, default=None,
                        help='left padding (overrides --padding)')
    parser.add_argument('--padding-right',
                        type=int, default=None,
                        help='right padding (overrides --padding)')
    parser.add_argument('--color', '-c',
                        default='ffffff',
                        help='font color (RRGGBB or RRGGBBAA)')
    parser.add_argument('--border', '-b',
                        type=int, default=0,
                        help='border width (default no border)')
    parser.add_argument('--border-color',
                        default='000000',
                        help='border color (RRGGBB or RRGGBBAA)')
    parser.add_argument('--background',
                        default='00000000',
                        help='background color (RRGGBB or RRGGBBAA)')
    parser.add_argument('--max-texture-size',
                        type=int, default=1024,
                        help='max texture width/height')
    parser.add_argument('--square',
                        action='store_true',
                        help='use the same size for texture width and height')
    parser.add_argument('--chars',
                        default=DEFAULT_CHARS,
                        help='character set to render')
    parser.add_argument('--antialiasing',
                        action='store_true',
                        help='use antialiasing when rendering glyphs')
    parser.add_argument('--premultiply',
                        action='store_true',
                        help='save textures with premultiplied alpha')
    parser.add_argument('--kerning',
                        action='store_true',
                        help='include kerning for character pairs')
    parser.add_argument('--char-spacing',
                        type=int, default=0,
                        help='extra space between characters')
    parser.add_argument('--line-spacing',
                        type=int, default=0,
                        help='extra space between lines')
    parser.add_argument('--pretty-print',
                        action='store_true',
                        help='use multiple lines and indentation for atlas')

    args = parser.parse_args()

    run(args)

if __name__ == '__main__':
    main()
