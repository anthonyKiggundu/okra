#!/usr/bin/env bash
set -e
echo "[+] Starting multi-vm 5G environment setup..."

# 1. Install lightweight Kubernetes (k3s) if not installed
if ! command -v kubectl &> /dev/null; then
  echo "[+] Installing k3s..."
  curl -sfL https://get.k3s.io | sh -
fi

K3S_KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Ensure current user can use kubectl (copy kubeconfig from k3s)
if [ -f "$K3S_KUBECONFIG" ]; then
  echo "[+] Making k3s kubeconfig available to the current user..."
  mkdir -p "$HOME/.kube"
  sudo cp "$K3S_KUBECONFIG" "$HOME/.kube/config"
  sudo chown $(id -u):$(id -g) "$HOME/.kube/config"
  export KUBECONFIG="$HOME/.kube/config"
else
  echo "[!] k3s kubeconfig not found at $K3S_KUBECONFIG (k3s might still be starting)."
fi

# Wait for API server to become available
echo "[+] Waiting for Kubernetes API to be ready..."
until kubectl --kubeconfig "${KUBECONFIG:-$HOME/.kube/config}" get nodes >/dev/null 2>&1; do
  sleep 2
done

echo "[+] K3s installed. Cluster status:"
kubectl get nodes

# Ensure helm is installed (helm is required by helmfile)
if ! command -v helm &> /dev/null; then
  echo "[!] helm not found. Installing Helm v3 (recommended for helm-diff + helmfile)..."
  HELM_V3_VERSION="v3.12.3" # pick a stable v3 release
  OS="$(uname | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64|amd64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
  esac
  TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR"' EXIT
  curl -fsSL "https://get.helm.sh/helm-${HELM_V3_VERSION}-${OS}-${ARCH}.tar.gz" -o "$TMPDIR/helm.tgz"
  tar -xzf "$TMPDIR/helm.tgz" -C "$TMPDIR"
  # tar structure: linux-amd64/helm
  sudo mv "${TMPDIR}/${OS}-${ARCH}/helm" /usr/local/bin/helm
  sudo chmod +x /usr/local/bin/helm
fi

# Ensure helmfile is installed (try brew, then release binary)
if ! command -v helmfile &> /dev/null; then
  echo "[+] helmfile not found — attempting to install..."
  if command -v brew &> /dev/null; then
    echo "[+] Installing helmfile via Homebrew..."
    brew install helmfile
  else
    echo "[+] Downloading helmfile binary (adjust VERSION if needed)..."
    VERSION="v0.144.0" # change to desired version
    OS="$(uname | tr '[:upper:]' '[:lower:]')"
    ARCH="$(uname -m)"
    case "$ARCH" in
      x86_64|amd64) ARCH=amd64 ;;
      aarch64|arm64) ARCH=arm64 ;;
    esac
    BIN_URL="https://github.com/roboll/helmfile/releases/download/${VERSION}/helmfile_${OS}_${ARCH}"
    sudo curl -Lo /usr/local/bin/helmfile "${BIN_URL}"
    sudo chmod +x /usr/local/bin/helmfile
  fi
fi

# Check helm version and plugin compat
HELM_BIN="$(command -v helm || true)"
if [ -z "$HELM_BIN" ]; then
  echo "[!] helm was not found after install; aborting."
  exit 1
fi

echo "[+] Using helm at: $HELM_BIN"
HELM_VER="$(helm version --short 2>/dev/null || true)"
echo "[+] helm version: $HELM_VER"

# If helm appears to be v4, warn the user and offer to install v3
if echo "$HELM_VER" | grep -q '^v4'; then
  echo "[!] Detected Helm v4. Many helmfile workflows and helm-diff expect Helm v3."
  echo "[!] Either install a helm-diff compatible with Helm v4, or install Helm v3 and try again."
  # Optionally: automatically install Helm v3 to /usr/local/bin/helm.v3 and use that with HELM_BIN override
  # (left out automatic downgrade to avoid unexpected system changes)
fi

# Robust helm-diff install helper
if ! helm plugin list 2>/dev/null | grep -q '^diff'; then
  echo "[+] helm-diff plugin not found — installing..."
  # Determine who should own the plugin: the user that will run helmfile.
  # If this script is run with sudo, $SUDO_USER is the original user; helmfile may run as root though.
  # We'll attempt installing for both SUDO_USER (if present) and root to be safe.
  INSTALL_URL="https://github.com/databus23/helm-diff"
  if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    echo "[+] Attempting to install helm-diff for user $SUDO_USER"
    sudo -u "$SUDO_USER" helm plugin install "$INSTALL_URL" 2>&1 || true
    # If still not visible, also try installing as root (so root-run helmfile will see it)
    if ! sudo -u "$SUDO_USER" helm plugin list 2>/dev/null | grep -q '^diff'; then
      echo "[+] Installing helm-diff for root (in case helmfile is executed under sudo/root)"
      sudo helm plugin install "$INSTALL_URL" 2>&1 || true
    fi
  else
    # no sudo user; install for current user and for root as a fallback
    helm plugin install "$INSTALL_URL" 2>&1 || true
    if ! helm plugin list 2>/dev/null | grep -q '^diff'; then
      echo "[+] Trying to install helm-diff as root (sudo)"
      sudo helm plugin install "$INSTALL_URL" 2>&1 || true
    fi
  fi

  # Final check
  if helm plugin list 2>/dev/null | grep -q '^diff'; then
    echo "[+] helm-diff installed and visible to the current helm."
  else
    echo "[!] Failed to install helm-diff (or it is not visible to this helm binary)."
    echo "Please run 'helm plugin install https://github.com/databus23/helm-diff' as the same user who will run helmfile,"
    echo "or make sure you are using Helm v3 compatible with the plugin."
    exit 1
  fi
else
  echo "[+] helm-diff already installed — nothing to do"
fi

# 2. Add Helm repositories
echo "[+] Adding Helm repos..."
bash k8s/helm-add-repos.sh

# 3. Apply base manifests
echo "[+] Applying network and storage configs..."
kubectl apply -f k8s/manifests/

# 4. Deploy all charts via Helmfile
echo "[+] Deploying 5G components..."
helmfile -f k8s/helmfile.yaml apply

echo "[✓] Deployment completed!"
kubectl get pods -A
