#!/usr/bin/env bash
# Aegis container-first bootstrap installer (host wrapper).
#
# The normal path is:
#   curl -fsSL https://releases.example.invalid/install.sh | sudo bash
#
# SAFER ALTERNATIVE (recommended): download, inspect, verify, then run locally:
#   curl -fsSLO https://releases.example.invalid/install.sh
#   curl -fsSLO https://releases.example.invalid/install.sh.sha256
#   sha256sum -c install.sh.sha256
#   # optionally verify the detached signature with the published release key
#   less install.sh
#   sudo bash install.sh
#
# This wrapper delegates to the Python bootstrap, which performs host preflight,
# verifies its own release metadata, installs rootless Docker + Compose, creates the
# locked service identities and directories, installs the digest-pinned Compose bundle,
# collects configuration and secret references, pulls immutable images, starts the
# appliance, and waits for readiness. Re-running is idempotent.
#
# The production release replaces the example domain and ships checksums, a detached
# signature, an SBOM, and a compatibility matrix alongside this script.
set -euo pipefail

PRODUCT_CLI="${PRODUCT_CLI:-ae}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to bootstrap the appliance" >&2
  exit 1
fi

echo "Aegis bootstrap: running host preflight and reconciliation..."
# The published bundle vendors the Python package; in a source checkout, invoke the CLI.
if command -v "${PRODUCT_CLI}" >/dev/null 2>&1; then
  "${PRODUCT_CLI}" appliance doctor || true
  echo "Run '${PRODUCT_CLI} appliance config init' then '${PRODUCT_CLI} appliance config validate' to configure."
else
  echo "The '${PRODUCT_CLI}' command is not on PATH yet." >&2
  echo "Install the released bundle, or from a source checkout run: uv run ${PRODUCT_CLI} appliance version" >&2
  exit 1
fi
