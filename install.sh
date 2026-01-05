#!/bin/bash
set -e

# Voice Claude Installer
# Supports: macOS, Linux, WSL

REPO_URL="https://github.com/iwebercodes/voice-claude"
INSTALL_DIR="$HOME/.voice-claude"
MIN_PYTHON_VERSION="3.10"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ -f /etc/debian_version ]]; then
        OS="debian"
    elif [[ -f /etc/redhat-release ]]; then
        OS="redhat"
    elif [[ -f /etc/arch-release ]]; then
        OS="arch"
    elif grep -qi microsoft /proc/version 2>/dev/null; then
        OS="wsl"
    else
        OS="linux"
    fi
    info "Detected OS: $OS"
}

# Check Python version
check_python() {
    info "Checking Python installation..."

    # Try python3 first, then python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        error "Python not found. Please install Python $MIN_PYTHON_VERSION or later."
    fi

    # Check version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [[ $MAJOR -lt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -lt 10 ]]; then
        error "Python $PYTHON_VERSION found, but $MIN_PYTHON_VERSION or later is required."
    fi

    info "Found Python $PYTHON_VERSION"
}

# Install system dependencies
install_dependencies() {
    info "Installing system dependencies..."

    case $OS in
        macos)
            if ! command -v brew &> /dev/null; then
                warn "Homebrew not found. Installing portaudio requires Homebrew."
                warn "Install Homebrew from https://brew.sh or install portaudio manually."
            else
                brew install portaudio 2>/dev/null || info "portaudio already installed"
            fi
            ;;
        debian|wsl)
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y libportaudio2 portaudio19-dev python3-venv
            fi
            ;;
        redhat)
            if command -v dnf &> /dev/null; then
                sudo dnf install -y portaudio portaudio-devel python3-virtualenv
            elif command -v yum &> /dev/null; then
                sudo yum install -y portaudio portaudio-devel python3-virtualenv
            fi
            ;;
        arch)
            sudo pacman -S --noconfirm portaudio python-virtualenv
            ;;
        *)
            warn "Unknown Linux distribution. Please install portaudio manually."
            ;;
    esac
}

# Check for Claude Code
check_claude_code() {
    info "Checking for Claude Code..."

    if ! command -v claude &> /dev/null; then
        warn "Claude Code not found."
        echo ""
        echo "Voice Claude requires Claude Code to be installed."
        echo "Install it with:"
        echo ""
        echo "  curl -fsSL https://claude.ai/install.sh | bash"
        echo ""
        read -p "Would you like to install Claude Code now? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            curl -fsSL https://claude.ai/install.sh | bash
            # Reload PATH
            export PATH="$HOME/.claude/local/bin:$PATH"
        else
            warn "Continuing without Claude Code. You'll need to install it before using Voice Claude."
        fi
    else
        info "Claude Code found"
    fi
}

# Clone or update repository
install_voice_claude() {
    info "Installing Voice Claude..."

    if [[ -d "$INSTALL_DIR" ]]; then
        info "Updating existing installation..."
        cd "$INSTALL_DIR"
        git fetch origin
        git reset --hard origin/master
    else
        info "Cloning repository..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
}

# Set up Python virtual environment
setup_venv() {
    info "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    if [[ ! -d "venv" ]]; then
        $PYTHON_CMD -m venv venv
    fi

    source venv/bin/activate

    info "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

    deactivate
}

# Create launcher script
create_launcher() {
    info "Creating launcher script..."

    LAUNCHER="$INSTALL_DIR/voice-claude"
    cat > "$LAUNCHER" << 'EOF'
#!/bin/bash
# Resolve symlinks to get the actual script location
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"

cd "$SCRIPT_DIR"
source venv/bin/activate
python3 -u src/main.py "$@"
EOF
    chmod +x "$LAUNCHER"

    # Add to PATH via symlink
    mkdir -p "$HOME/.local/bin"
    ln -sf "$LAUNCHER" "$HOME/.local/bin/voice-claude"

    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "~/.local/bin is not in your PATH"
        echo ""
        echo "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
        echo ""
        echo '  export PATH="$HOME/.local/bin:$PATH"'
        echo ""
    fi
}

# Main installation flow
main() {
    echo ""
    echo "================================"
    echo "  Voice Claude Installer"
    echo "================================"
    echo ""

    detect_os
    check_python
    install_dependencies
    check_claude_code
    install_voice_claude
    setup_venv
    create_launcher

    echo ""
    echo "================================"
    echo -e "${GREEN}  Installation complete!${NC}"
    echo "================================"
    echo ""
    echo "Run Voice Claude with:"
    echo ""
    echo "  voice-claude"
    echo ""
    echo "Or directly:"
    echo ""
    echo "  $INSTALL_DIR/voice-claude"
    echo ""
    echo "Note: The first run will download the Whisper speech model (~500MB)."
    echo ""
}

main
