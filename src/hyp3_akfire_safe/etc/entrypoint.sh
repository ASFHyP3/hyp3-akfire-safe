#!/bin/bash --login
set -e
conda activate hyp3-akfire-safe
exec python -um hyp3_akfire_safe "$@"
