# Six-volume print edition (Royal 156 x 234 mm)

A personal, non-commercial print edition in six volumes (the six books of
the 2015 edition), laid out for printing at Printenbind.nl.  The original
`.tex` sources are not modified; `tools/prepare.py` derives the volumes from
them.

    make all              # everything from scratch -> dist/
    make all PAPER=a5     # the same set as A5
    make check            # verification (logs, fonts, QR codes, links)
    make links            # re-extract EPUB links and re-check all URLs
                          # (network; needs links/rationality.epub)

Output in `dist/`:

* `volN/interior.pdf` - interior, single pages of the trim size, fonts
  embedded, mirrored margins (inner 25 mm, outer 34 mm on Royal)
* `volN/cover.pdf` - back + spine + front, 3 mm bleed;
  `volN/cover-front.pdf`, `volN/cover-back.pdf` - the same with 3 mm bleed
* `volumes.csv` - page counts and spine widths
  (spine = sheets x `SHEET_MM`, default 0.1 mm for 80 g/m2:
  `make covers SHEET_MM=0.11`)
* `_redirects` - Cloudflare Pages redirects for the short links
  `sharov.me/r/<volume>-<n>` (external links) and
  `sharov.me/r/<volume>-c<n>` (discussion of each essay on LessWrong)
* `links.csv` - code, volume, page, link text, original URL, final URL,
  status (ok / redirected / archived / unchecked), kind

## Paper size

The paper is a single parameter, `PAPER` (Makefile), resolved in
`print/paper.tex`, which holds the trim size, margins and type size of each
supported paper (`royal`, `a5`).  Covers read the same file.

## Build order and cross references

Links between essays are printed as "(p. 123)" within a volume and as
"(vol. II, p. 123)" across volumes, using zref-xr: every volume imports the
`.aux` files of the other five.  Because the references go in both
directions, `tools/build_interiors.sh` compiles vol1..vol6 in passes until
no `.aux` file changes (usually three passes) and fails if any reference
remains undefined.  Covers are built afterwards from the final page counts,
and `_redirects` / `links.csv` last, from the page numbers in the final
`.aux` files.

## Links

1. `tools/epub_links.py` extracts every hyperlink of the 2015 EPUB.
2. `tools/place_links.py` finds each link in the `.tex` text by its link
   text and the text before it, and writes `links/placements.json`.
3. `tools/check_links.py` checks every URL (redirects followed; dead links
   replaced by the Wayback Machine snapshot closest to 2015) into
   `links/url_status.json`.
4. `tools/prepare.py` inserts page references and QR footnotes.

`links/lw_posts.json` maps every essay to its LessWrong page (for the
discussion QR code at the end of every essay); `tools/lw_posts.py`
refreshes it.

Ebook links that are not placed in the text are listed, with the reason, in
`links/placements_report.json`.  Phrases in which every word links to a
different essay get one footnote listing the words and their pages.

The Part divider illustrations are the sequence images of
lesswrong.com/rationality; they are downloaded at build time
(`tools/illustrations.py`) and are not part of this repository.

---

# rationality-ai-zombies

A tex version of the ebook by Eliezer Yudkowsky: Rationality from AI to Zombies

The original book is available at
https://intelligence.org/rationality-ai-zombies/

Released under the Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported license.
CC BY-NC-SA 3.0

This is based on the 2015 edition of the book.  This does not yet
incorporate the the changes in the multivolume 2018+ versions.

## Creating PDFs

The release files are created by running the script dist_build

There is also a makefile that can be used. Make needs to be run twice
if the page numbering has changed (the dist_build script does this
automatically).

lualatex can be used directly to create the PDFs:
touch version.tex; lualatex rationality_from_ai_to_zombies.tex

## Creating Printed Versions

The first step is to create a PDF. This can be done with the dist_build or
by getting a prebuilt version from:
https://github.com/jrincayc/rationality-ai-zombies/releases

The two column version is recommended: rationality_from_ai_to_zombies_2c.pdf
This has fewer pages than the one column version, and has the same font size.

The file images/cover_image.png can be used for the cover.

The file images/back_cover.png can be used for a back cover.

This is for 8 1/2 inch by 11 inch pages.

## Creating a Printed Version with Lulu

First, download the newest version of: rationality_from_ai_to_zombies_2c.pdf
from:
https://github.com/jrincayc/rationality-ai-zombies/releases
and the cover files:
https://github.com/jrincayc/rationality-ai-zombies/raw/master_lite/images/cover_image.png
and
https://github.com/jrincayc/rationality-ai-zombies/raw/master_lite/images/back_cover.png

Go to http://www.lulu.com and select Create -> Print Book

Create an account if you need to.

Choose either paperback 8.5x11in (~ $12) or Hardcover 8.25x10.75in (~ $31)
(If you put in 656 pages, it will tell you the exact price,
black and white is generally fine, there are only a few color images
inside, and they work fine in black and white.)

Go to "make this book."

Put in the Title:
Rationality: From AI to Zombies

And the Author:
Eliezer Yudkowsky

And choose "Make available only to me" (note that the book is available under a
Noncommercial license, you cannot sell it for profit.)

Then upload `rationality_from_ai_to_zombies_2c.pdf` and make print-ready file.

Then ignore the warnings about low resolution images and small fonts and
save and continue.

Use the old cover designer.

On Backgrounds & Pictures, upload cover_image.png as the front cover
and back_cover.png as the back cover.

For Text, for the Front Cover, unclick show title and show author.
For the Spine, switch text size to 24, and add the author: Eliezer Yudkowsky
Then make print-ready cover.

Alternatively there are some one piece covers on the wiki that can be used:
https://github.com/jrincayc/rationality-ai-zombies/wiki

Save and Finish, and you can order it.

## History and Purpose of Project

This project started with the 2015 epub version of Rationality: from
AI to Zombies, and then used Calibre and Open Office to create a LaTeX
document.  Then, the resulting document was edited to recreate TeX
elements like footnotes and chapters and small caps and equations.

While the entire document has been proofread multiple times, there may still
be mistakes, if you find them, please either create an issue or a pull
request.

If you need a editable version, this version works great.  If you want
a single volume printable version, the two column version is much more
practical than the original single column PDF.

## About Eliezer Yudkowsky:

Eliezer Yudkowsky is a decision theorist and mathematician who works
on foundational issues in Artificial General Intelligence (AGI), the
theoretical study of domain-general problem-solving
systems. Yudkowsky's work in AI has been a major driving force behind
his exploration of the psychology of human rationality.

Eliezer Yudkowsky is the author of many works including *Harry Potter
and the Methods of Rationality* and the chapter “Cognitive Biases
Potentially Affecting Judgement of Global Risks” in *Global
Catastrophic Risks*. He is a research fellow and a co-founder of the
Machine Intelligence Research Institute.

## About the Book:

Rationality from AI to Zombies is a book about getting our
understanding of the world right, even when it might not be easy, or
there is uncertainty, or we have bias. Containing a collection of two
years of blog posts edited into a cohesive whole the book covers
topics ranging from changing your mind and Bayesian reasoning, to
philosophical zombies and implications of Artificial
Intelligence. Included are practical methods of improving your
rationality, inspirational essays and illustrative stories.
