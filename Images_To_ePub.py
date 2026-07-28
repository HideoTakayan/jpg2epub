""" Convert a folder with images to an ePub file. Great for comics and manga!
    Copyright (C) 2021  Antoine Veenstra

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see [http://www.gnu.org/licenses/]
"""
import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from core.ePubMaker import EPubMaker, CmdProgress
from core.PdfMaker import PdfMaker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert a folder with images to an ePub or PDF file.",
        usage='%(prog)s [--progress] --dir DIRECTORY --file FILE --name NAME\n'
        '   or: %(prog)s [--progress] DIRECTORY [DIRECTORY ...]')
    parser.add_argument(
        '-p', '--progress', action='store_true', default=False,
        help='Show a nice progressbar'
    )
    parser.add_argument(
        '-d',
        '--dir',
        dest='input_dir',
        metavar='DIRECTORY',
        type=Path,
        help='DIRECTORY with the images')
    parser.add_argument(
        '-f',
        '--file',
        dest='file',
        metavar='FILE',
        type=Path,
        help='FILE where the ePub/PDF is stored')
    parser.add_argument(
        '-n',
        '--name',
        dest='name',
        default='',
        metavar='NAME',
        help='NAME of the book')
    parser.add_argument(
        '-a',
        '--author',
        dest='author',
        default='',
        metavar='AUTHOR',
        help='AUTHOR of the book')
    parser.add_argument(
        '-F',
        '--format',
        dest='format',
        choices=[
            'epub',
            'pdf'],
        default='epub',
        help='Output format: epub or pdf (default: epub)')
    parser.add_argument(
        '-g',
        '--grayscale',
        dest='grayscale',
        default=False,
        action='store_true',
        help="Convert all images to black and white before adding them to the file.",
    )
    parser.add_argument(
        '-W', '--max-width', dest='max_width', default=None, type=int,
        help="Resize all images to have the given maximum width in pixels."
    )
    parser.add_argument(
        '-H', '--max-height', dest='max_height', default=None, type=int,
        help="Resize all images to have the given maximum height in pixels."
    )
    parser.add_argument(
        '-q', '--quality', dest='quality', default=100, type=int,
        help="Image quality for JPEG compression (1-100), default: 100 (lossless)."
    )
    parser.add_argument(
        '--rtl',
        dest='rtl',
        action='store_true',
        default=False,
        help="Manga mode: Right-to-left page progression (ePub only).")
    parser.add_argument(
        '--crop',
        dest='crop',
        action='store_true',
        default=False,
        help='Auto crop white borders from images'
    )
    parser.add_argument(
        '--split',
        dest='split',
        action='store_true',
        default=False,
        help='Split double-page spreads into two pages'
    )

    # Mutually exclusive group for wrap_pages
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--wrap-pages',
        dest='wrap_pages',
        action='store_true',
        default=True,
        help="Wrap the pages in a separate file (ePub only). Results will vary for each reader. (Default)")
    group.add_argument(
        '--no-wrap-pages',
        dest='wrap_pages',
        action='store_false',
        help="Do not wrap the pages in a separate file (ePub only). Results will vary for each reader.")

    # Catch-all for batch mode directories
    parser.add_argument(
        'args',
        nargs='*',
        type=Path,
        help="Directories for batch mode")

    args = parser.parse_args()

    def run_maker(
            master,
            input_dir,
            output_file,
            name,
            author,
            grayscale,
            max_width,
            max_height,
            quality,
            rtl,
            auto_crop,
            split_spreads,
            progress,
            wrap_pages,
            out_format):

        cleanup_dir = None
        input_path = Path(input_dir)
        if input_path.is_file() and input_path.suffix.lower() in ('.zip', '.cbz'):
            cleanup_dir = tempfile.mkdtemp(prefix="img2epub_")
            try:
                with zipfile.ZipFile(input_path, 'r') as zip_ref:
                    zip_ref.extractall(cleanup_dir)
                input_dir = cleanup_dir
            except Exception as e:
                import os
                import shutil
                if os.path.exists(cleanup_dir):
                    shutil.rmtree(cleanup_dir, ignore_errors=True)
                if master:
                    master.showerror("Extraction Error",
                                     f"Could not extract archive:\n{e}")
                    master.stop(0)
                else:
                    print(f"Extraction Error: {e}", file=sys.stderr)
                return

        if out_format == 'pdf':
            PdfMaker(
                master=master,
                input_dir=input_dir,
                file=output_file,
                name=name,
                grayscale=grayscale,
                max_width=max_width,
                max_height=max_height,
                quality=quality,
                rtl=rtl,
                auto_crop=auto_crop,
                split_spreads=split_spreads,
                cleanup_dir=cleanup_dir,
                progress=progress).run()
        else:
            EPubMaker(
                master=master,
                input_dir=input_dir,
                file=output_file,
                name=name,
                author=author,
                grayscale=grayscale,
                max_width=max_width,
                max_height=max_height,
                quality=quality,
                rtl=rtl,
                auto_crop=auto_crop,
                split_spreads=split_spreads,
                cleanup_dir=cleanup_dir,
                progress=progress,
                wrap_pages=wrap_pages).run()

    # Determine mode
    if not args.input_dir and not args.file and not args.name:
        if not args.args:
            if sys.stdout is not None:
                parser.print_help()
            sys.exit(0)

        if not all(elem.is_dir() or (elem.is_file() and elem.suffix.lower() in ('.zip', '.cbz')) for elem in args.args):
            parser.error(
                "All batch arguments must be directories or .zip/.cbz files!")

        directories: list[Path] = []
        for path in args.args:
            if not path.is_dir() and not (path.is_file() and path.suffix.lower() in ('.zip', '.cbz')):
                parser.error(
                    f"The following path is not a valid directory or archive: {path}")
            if not path.name:
                parser.error(
                    f"Could not get the name of the directory/file: {path}")
            directories.append(path)

        for path in directories:
            # Remove extension for output file name if it's an archive
            base_name = path.stem if path.is_file() else path.name
            out_file = str(path.parent / f"{base_name}.{args.format}")
            run_maker(
                master=None,
                input_dir=str(path),
                output_file=out_file,
                name=base_name or "Output",
                author=args.author,
                grayscale=args.grayscale,
                max_width=args.max_width,
                max_height=args.max_height,
                quality=args.quality,
                rtl=args.rtl,
                auto_crop=args.crop,
                split_spreads=args.split,
                progress=CmdProgress(args.progress),
                wrap_pages=args.wrap_pages,
                out_format=args.format
            )
    elif args.input_dir and args.file and args.name:
        run_maker(
            master=None,
            input_dir=str(args.input_dir),
            output_file=str(args.file),
            name=args.name,
            author=args.author,
            grayscale=args.grayscale,
            max_width=args.max_width,
            max_height=args.max_height,
            quality=args.quality,
            rtl=args.rtl,
            auto_crop=args.crop,
            split_spreads=args.split,
            progress=CmdProgress(args.progress),
            wrap_pages=args.wrap_pages,
            out_format=args.format
        )
    else:
        parser.print_help()
