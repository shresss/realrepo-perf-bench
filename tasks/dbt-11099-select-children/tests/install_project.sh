#!/bin/sh
# Docker-build helper only: install metadata, then restore archive-clean source.
# Pure-Python projects only: compiled extensions built in-tree are discarded by the
# restore below (NOTE: if the project has C/Cython extensions, this task needs a
# different install and is out of template scope).
set -eu
archive=$1
source_root=$2
case "$source_root" in /app|/tests/pristine) ;; *) exit 2 ;; esac
test -f "$archive"
test ! -e "$source_root/core"
mkdir -p "$source_root"
tar -xzf "$archive" --strip-components=1 -C "$source_root"
/usr/local/bin/python -m pip install --no-cache-dir --use-pep517 --no-deps --no-build-isolation -e "$source_root/core"
# Keep generated metadata out of the baseline/submission tree. The installed
# editable finder still points to source_root, restored below from exact Git bytes.
staging=$(mktemp -d /tmp/project-metadata.XXXXXX)
chmod 0700 "$staging"
mv "$source_root" "$staging/source"
mkdir -p "$source_root"
tar -xzf "$archive" --strip-components=1 -C "$source_root"
