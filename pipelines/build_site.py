"""Build the public website folder (_site/) for GitHub Pages: the repo minus what no page reads.
.github/workflows/pages.yml runs this and publishes _site/. Everything stays in the repo; it is only left off the site.

Left off the site:
  - code and working files (*.py, *.sh, *.yml, requirements*.txt, *.md notes, pipelines/, models/, local/ ...)
    so model code is never served on the public page
  - the raw-data paths listed in site_exclude.txt (one per line, relative to the repo root, '#' comments), checked
    against a crawl of every tab: no page requests them.
To put something back on the site, delete its line from site_exclude.txt.

Usage: python pipelines/build_site.py [--check]    (--check: list what would be left off, copy nothing)
"""
import fnmatch, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
ALWAYS_DIRS = {".git", ".github", "_site", "backup", "node_modules", "__pycache__", ".cache", "inbox"}
CODE_GLOBS = ["*.py", "*.pyc", "*.sh", "*.yml", "*.yaml", "requirements*.txt", "*.ipynb", "package-lock.json",
              "HANDOFF.md", "site_exclude.txt", ".gitignore", ".DS_Store"]


def excluded_paths():
    f = ROOT / "site_exclude.txt"
    if not f.exists():
        return []
    return [l.split("#")[0].strip().strip("/") for l in f.read_text().splitlines() if l.split("#")[0].strip()]


def main():
    check = "--check" in sys.argv
    ex = excluded_paths()
    kept = left = 0
    kept_bytes = left_bytes = 0
    if not check:
        shutil.rmtree(OUT, ignore_errors=True)
        OUT.mkdir()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = Path(dirpath).relative_to(ROOT).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep_dirs = []
        for d in dirnames:
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if d == ".git":
                continue
            if d in ALWAYS_DIRS or any(rel == e or rel.startswith(e + "/") for e in ex):
                size = sum(p.stat().st_size for p in Path(dirpath, d).rglob("*") if p.is_file())
                left_bytes += size
                continue
            keep_dirs.append(d)
        dirnames[:] = keep_dirs
        for fn in filenames:
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            src = Path(dirpath, fn)
            size = src.stat().st_size
            if any(fnmatch.fnmatch(fn, g) for g in CODE_GLOBS) or rel in ex:
                left += 1; left_bytes += size
                continue
            kept += 1; kept_bytes += size
            if not check:
                dst = OUT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    if not check:
        (OUT / ".nojekyll").write_text("")
    print(f"site: {kept} files, {kept_bytes / 1e6:.0f} MB kept; {left_bytes / 1e6:.0f} MB left off the site")
    if kept_bytes > 900e6:
        sys.exit("site is over 900 MB: GitHub Pages allows 1 GB")


if __name__ == "__main__":
    main()
