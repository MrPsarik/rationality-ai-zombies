# Six-volume print edition of "Rationality: From AI to Zombies".
#
#   make all              build everything from scratch into dist/
#   make all PAPER=a5     the same set as A5 (the only paper parameter)
#   make check            verify logs, QR codes and link placement
#   make links            re-extract links from the EPUB and re-check URLs
#                         (needs network and links/rationality.epub)
#   make clean
#
# Build order (see tools/build_interiors.sh): the volumes reference each
# other's page numbers, so all six interiors are compiled in passes until
# no .aux file changes; covers are built afterwards from the final page
# counts; the redirect file and links.csv last, from the final .aux files.

PAPER    ?= royal
SHEET_MM ?= 0.1
PYTHON   ?= python3
export PAPER SHEET_MM

VOLS := 1 2 3 4 5 6

.PHONY: all prepare interiors covers redirects check links clean distclean

all: prepare interiors covers redirects
	@echo "done: dist/vol1..vol6, dist/_redirects, dist/links.csv"

prepare:
	$(PYTHON) tools/prepare.py
	$(PYTHON) tools/bibliography.py
	-$(PYTHON) tools/illustrations.py

interiors: prepare
	tools/build_interiors.sh
	@for v in $(VOLS); do mkdir -p dist/vol$$v; \
	  cp build/tex/vol$$v.pdf dist/vol$$v/interior.pdf; done

covers:
	$(PYTHON) tools/covers.py

redirects:
	$(PYTHON) tools/redirects.py

check:
	$(PYTHON) tools/check.py

links:
	$(PYTHON) tools/epub_links.py links/rationality.epub
	$(PYTHON) tools/place_links.py
	$(PYTHON) tools/prepare.py
	$(PYTHON) tools/bibliography.py
	$(PYTHON) tools/check_links.py

clean:
	rm -rf build

distclean: clean
	rm -rf dist

# ---------------------------------------------------------------------------
# Original single-file letter-size builds (used by ./dist_build)
.PHONY: legacy
legacy: rationality_from_ai_to_zombies.pdf rationality_from_ai_to_zombies_2c.pdf


rationality_from_ai_to_zombies.pdf : rationality_from_ai_to_zombies.tex map_and_territory.tex change_mind.tex machine_in_ghost.tex mere_reality.tex mere_goodness.tex becoming_stronger.tex front.tex macros.tex bibliography.tex version.tex
	lualatex rationality_from_ai_to_zombies.tex


rationality_from_ai_to_zombies_2c.pdf : rationality_from_ai_to_zombies_2c.tex map_and_territory.tex change_mind.tex machine_in_ghost.tex mere_reality.tex mere_goodness.tex becoming_stronger.tex front.tex macros.tex bibliography.tex version.tex
	lualatex rationality_from_ai_to_zombies_2c.tex

version.tex:
	git describe > version.tex
	echo >> version.tex
	git log -1 --format='format:%H \\%aD' >> version.tex
