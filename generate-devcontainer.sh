#!/usr/bin/env bash

usage() {
    cat <<'EOF'
Usage: generate-devcontainer.sh [OPTIONS]

Generate Dockerfile and devcontainer.json in --output (default: .devcontainer).

  --os ubuntu|fedora       Distribution (default: ubuntu)
  --version VERSION       Ubuntu: lts, current, latest, 22.04, 24.04, 26.04
                          Fedora: current, latest, 44
                          Default: Ubuntu lts (26.04), Fedora current (44)
  --java                  Install the distribution's JDK
  --php                   Install the distribution's PHP CLI
  --go                    Install the distribution's Go toolchain
  --docker                Install Docker/Compose and bind the host Docker socket
                          WARNING: socket access grants control of the host daemon
  --build-tools           Install the distribution's compiler/build tools
  --jq --unzip
                          Install each selected utility independently
  --output DIR            Destination directory
  --force                 Replace existing regular output files only
  --help                  Show this help

No packages are installed on the host. Container builds use distribution repos.
Ubuntu 22.04 uses docker-compose if docker-compose-v2 is unavailable.
EOF
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

check_targets() {
    local target
    for target in "$output/Dockerfile" "$output/devcontainer.json"; do
        if [ -L "$target" ]; then
            fail "Refusing symlink: $target"
        elif [ -e "$target" ]; then
            [ -f "$target" ] || fail "Not a regular file: $target"
            [ "$force" = true ] || fail "File already exists (use --force): $target"
        fi
    done
}

# Keep shell settings local, including for bash -s.
main() (
    set -eu
    os=ubuntu
    version=
    output=.devcontainer
    force=false
    java=false
    php=false
    go=false
    docker=false
    build_tools=false
    jq=false

    unzip=false

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --os|--version|--output)
                [ "$#" -ge 2 ] || fail "Missing value for $1"
                case "$2" in
                    ''|--*) fail "Missing value for $1" ;;
                esac
                case "$1" in
                    --os) os=$2 ;;
                    --version) version=$2 ;;
                    --output) output=$2 ;;
                esac
                shift 2
                ;;
            --java) java=true; shift ;;
            --php) php=true; shift ;;
            --go) go=true; shift ;;
            --docker) docker=true; shift ;;
            --build-tools) build_tools=true; shift ;;
            --jq) jq=true; shift ;;

            --unzip) unzip=true; shift ;;
            --force) force=true; shift ;;
            --help) usage; exit 0 ;;
            *) fail "Unknown argument: $1" ;;
        esac
    done

    case "$os" in
        ubuntu)
            [ -n "$version" ] || version=lts
            case "$version" in
                lts|current) tag=26.04 ;;
                latest|22.04|24.04|26.04) tag=$version ;;
                *) fail "Invalid Ubuntu version: $version" ;;
            esac
            image=ubuntu
            packages='bash ca-certificates curl git tar gzip findutils procps'
            [ "$java" = false ] || packages="$packages default-jdk"
            [ "$php" = false ] || packages="$packages php-cli"
            [ "$go" = false ] || packages="$packages golang-go"
            [ "$build_tools" = false ] || packages="$packages build-essential"
            if [ "$docker" = true ]; then
                packages="$packages docker.io"
                # Jammy repositories may not include the newer Compose package.
                [ "$tag" = 22.04 ] || packages="$packages docker-compose-v2"
            fi
            ;;
        fedora)
            [ -n "$version" ] || version=current
            case "$version" in
                current) tag=44 ;;
                latest|44) tag=$version ;;
                *) fail "Invalid Fedora version: $version" ;;
            esac
            image=quay.io/fedora/fedora
            packages='bash ca-certificates curl git tar gzip findutils procps-ng'
            [ "$java" = false ] || packages="$packages java-latest-openjdk-devel"
            [ "$php" = false ] || packages="$packages php-cli"
            [ "$go" = false ] || packages="$packages golang"
            [ "$build_tools" = false ] || packages="$packages gcc gcc-c++ make"
            [ "$docker" = false ] || packages="$packages docker-cli docker-compose"
            ;;
        *) fail "Invalid OS: $os" ;;
    esac
    [ "$jq" = false ] || packages="$packages jq"

    [ "$unzip" = false ] || packages="$packages unzip"

    # Prefix relative paths so a leading dash is never interpreted as an option.
    case "$output" in
        /*) ;;
        *) output=./$output ;;
    esac
    # Strip trailing slashes so a symlink directory cannot bypass the check.
    while [ "$output" != / ] && [ "${output%/}" != "$output" ]; do
        output=${output%/}
    done
    [ ! -L "$output" ] || fail "Refusing symlink output directory: $output"
    if [ -e "$output" ] && [ ! -d "$output" ]; then
        fail "Not a directory: $output"
    fi
    check_targets
    mkdir -p -- "$output"


    {
        printf 'FROM %s:%s\n\n' "$image" "$tag"
        if [ "$os" = ubuntu ]; then
            printf 'RUN apt-get update \\\n'
            if [ "$docker" = true ] && [ "$tag" = 22.04 ]; then
                printf '    && if apt-cache show docker-compose-v2 >/dev/null 2>&1; then \\\n'
                printf '         compose_package=docker-compose-v2; \\\n'
                printf '       else compose_package=docker-compose; fi \\\n'
                printf '    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends %s "$compose_package" \\\n' "$packages"
            else
                printf '    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends %s \\\n' "$packages"
            fi
            printf '    && rm -rf /var/lib/apt/lists/*\n'
        else
            printf 'RUN dnf install -y %s \\\n    && dnf clean all\n' "$packages"
        fi
        printf '\nRUN git config --system --add safe.directory /workspace\n'
        printf '\nWORKDIR /workspace\nCMD ["sleep", "infinity"]\n'
    } > "$output/Dockerfile"

    {
        cat <<'EOF'
{
  "name": "Development container",
  "build": { "dockerfile": "Dockerfile" },
  "workspaceFolder": "/workspace",
  "workspaceMount": "source=${localWorkspaceFolder},target=/workspace,type=bind",
EOF
        if [ "$docker" = true ]; then
            printf '  "mounts": ["source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"],\n'
        fi
        printf '  "shutdownAction": "stopContainer"\n}\n'
    } > "$output/devcontainer.json"


    printf 'Generated %s/Dockerfile and %s/devcontainer.json\n' "$output" "$output"
)

# Keep all side effects after the full script has been received and parsed.
main "$@"
