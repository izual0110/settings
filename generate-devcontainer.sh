#!/usr/bin/env bash

usage() {
    cat <<'EOF'
Usage: generate-devcontainer.sh [OPTIONS]

Generate Dockerfile and devcontainer.json in --output (default: .devcontainer).

  --os ubuntu|fedora|alpine
                          Distribution (default: ubuntu)
  --version VERSION       Ubuntu: lts, current, latest, 22.04, 24.04, 26.04
                          Fedora: current, latest, 44
                          Alpine: current, latest, 3.24
                          Default: Ubuntu lts (26.04), Fedora current (44),
                          Alpine current (3.24)
  --java-lts              Install Temurin JDK 25 (LTS; alias: --java)
  --java-latest           Install Temurin JDK 27
  --clojure               Install Clojure CLI
  --maven                 Install Maven 3 (alias: --mvn)
  --gradle                Install Gradle 9
  --php                   Install the distribution's PHP CLI
  --go                    Install the distribution's Go toolchain
  --claude                Install Claude Code CLI
  --codex                 Install OpenAI Codex CLI
  --docker                Install Docker/Compose and bind the host Docker socket
                          WARNING: socket access grants control of the host daemon
  --build-tools           Install the distribution's compiler/build tools
  --jq                    Install jq
  --unzip                 Install unzip
  --mariadb               Install the distribution's MariaDB client (no server)
  --output DIR            Destination directory
  --force                 Replace existing regular output files only
  --help                  Show this help

Clojure, Maven, and Gradle add Java LTS unless a Java version is selected.
Java LTS and latest are mutually exclusive.

No packages are installed on the host. Builds use distribution repos,
Temurin / Maven / Gradle images from Docker Hub, GitHub for Clojure CLI,
and official Claude Code / Codex download services for the selected AI tools.
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
    java=none
    clojure=false
    maven=false
    gradle=false
    php=false
    go=false
    claude=false
    codex=false
    docker=false
    build_tools=false
    jq=false
    unzip=false
    mariadb=false

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
            --java|--java-lts|--java-latest)
                java_version=25
                [ "$1" != --java-latest ] || java_version=27
                if [ "$java" != none ] && [ "$java" != "$java_version" ]; then
                    fail "Choose either Java LTS or latest, not both"
                fi
                java=$java_version
                shift
                ;;
            --clojure) clojure=true; shift ;;
            --maven|--mvn) maven=true; shift ;;
            --gradle) gradle=true; shift ;;
            --php) php=true; shift ;;
            --go) go=true; shift ;;
            --claude) claude=true; shift ;;
            --codex) codex=true; shift ;;
            --docker) docker=true; shift ;;
            --build-tools) build_tools=true; shift ;;
            --jq) jq=true; shift ;;
            --unzip) unzip=true; shift ;;
            --mariadb) mariadb=true; shift ;;
            --force) force=true; shift ;;
            --help) usage; exit 0 ;;
            *) fail "Unknown argument: $1" ;;
        esac
    done

    if { [ "$clojure" = true ] || [ "$maven" = true ] || [ "$gradle" = true ]; } && [ "$java" = none ]; then
        java=25
    fi

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
            [ "$java" = none ] || packages="$packages fontconfig libstdc++6 tzdata zlib1g binutils"
            [ "$php" = false ] || packages="$packages php-cli"
            [ "$go" = false ] || packages="$packages golang-go"
            [ "$mariadb" = false ] || packages="$packages mariadb-client"
            [ "$claude" = false ] || packages="$packages libstdc++6"
            { [ "$codex" = false ] && [ "$gradle" = false ]; } || packages="$packages mawk"
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
            [ "$java" = none ] || packages="$packages fontconfig libstdc++ tzdata zlib binutils"
            [ "$php" = false ] || packages="$packages php-cli"
            [ "$go" = false ] || packages="$packages golang"
            [ "$mariadb" = false ] || packages="$packages mariadb"
            [ "$claude" = false ] || packages="$packages libstdc++"
            { [ "$codex" = false ] && [ "$gradle" = false ]; } || packages="$packages gawk"
            [ "$build_tools" = false ] || packages="$packages gcc gcc-c++ make"
            [ "$docker" = false ] || packages="$packages docker-cli docker-compose"
            ;;
        alpine)
            [ -n "$version" ] || version=current
            case "$version" in
                current) tag=3.24 ;;
                latest|3.24) tag=$version ;;
                *) fail "Invalid Alpine version: $version" ;;
            esac
            image=alpine
            # GNU sleep supports infinity; Codex also needs GNU fold's -b option.
            packages='bash ca-certificates curl git tar gzip findutils procps-ng coreutils'
            [ "$java" = none ] || packages="$packages fontconfig ttf-dejavu libgcc libstdc++ tzdata zlib binutils"
            [ "$php" = false ] || packages="$packages php-cli"
            [ "$go" = false ] || packages="$packages go"
            [ "$mariadb" = false ] || packages="$packages mariadb-client"
            [ "$claude" = false ] || packages="$packages libgcc libstdc++"
            { [ "$codex" = false ] && [ "$gradle" = false ]; } || packages="$packages gawk"
            [ "$build_tools" = false ] || packages="$packages build-base"
            [ "$docker" = false ] || packages="$packages docker-cli docker-cli-compose"
            ;;
        *) fail "Invalid OS: $os" ;;
    esac
    [ "$jq" = false ] || packages="$packages jq"
    [ "$unzip" = false ] || packages="$packages unzip"
    [ "$clojure" = false ] || packages="$packages rlwrap"

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
        elif [ "$os" = fedora ]; then
            printf 'RUN dnf install -y %s \\\n    && dnf clean all\n' "$packages"
        else
            printf 'RUN apk add --no-cache %s\n' "$packages"
        fi
        if [ "$java" != none ]; then
            java_tag=$java-jdk
            [ "$os" != alpine ] || java_tag=$java_tag-alpine
            cat <<EOF

COPY --from=eclipse-temurin:$java_tag /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="\${JAVA_HOME}/bin:\${PATH}"
RUN java --version && javac --version
EOF
        fi
        # Copy only the build tools, never the donor images' JDKs or entrypoints.
        if [ "$maven" = true ]; then
            cat <<'EOF'

COPY --from=maven:3-eclipse-temurin-25 /usr/share/maven /usr/share/maven
ENV MAVEN_HOME=/usr/share/maven
ENV PATH="${MAVEN_HOME}/bin:${PATH}"
RUN mvn --version
EOF
        fi
        if [ "$gradle" = true ]; then
            cat <<'EOF'

COPY --from=gradle:9-jdk25 /opt/gradle /opt/gradle
ENV GRADLE_HOME=/opt/gradle
ENV PATH="${GRADLE_HOME}/bin:${PATH}"
RUN gradle --version
EOF
        fi
        if [ "$clojure" = true ]; then
            cat <<'EOF'

ARG CLOJURE_VERSION=1.12.6.1673
RUN curl -fsSL -o /tmp/linux-install.sh \
      "https://github.com/clojure/brew-install/releases/download/${CLOJURE_VERSION}/linux-install.sh" \
    && cd /tmp \
    && bash linux-install.sh \
    && rm -f linux-install.sh \
    && clojure -Sdescribe
EOF
        fi
        if [ "$claude" = true ] || [ "$codex" = true ]; then
            cat <<'EOF'

ENV PATH="/root/.local/bin:${PATH}"
EOF
        fi
        if [ "$claude" = true ]; then
            cat <<'EOF'

RUN curl -fsSL -o /tmp/claude-install.sh https://claude.ai/install.sh \
    && bash /tmp/claude-install.sh latest \
    && rm -f /tmp/claude-install.sh \
    && claude --version
EOF
        fi
        if [ "$codex" = true ]; then
            cat <<'EOF'

RUN curl -fsSL -o /tmp/codex-install.sh https://chatgpt.com/codex/install.sh \
    && CODEX_NON_INTERACTIVE=true sh /tmp/codex-install.sh \
    && rm -f /tmp/codex-install.sh \
    && codex --version
EOF
        fi
        printf "\nRUN git config --system --add safe.directory '/workspaces/*'\n"
        printf '\nWORKDIR /workspaces\nCMD ["sleep", "infinity"]\n'
    } > "$output/Dockerfile"

    {
        cat <<'EOF'
{
  "name": "Development container for ${localWorkspaceFolderBasename}",
  "build": { "dockerfile": "Dockerfile" },
  "workspaceFolder": "/workspaces/${localWorkspaceFolderBasename}",
  "workspaceMount": "source=${localWorkspaceFolder},target=/workspaces/${localWorkspaceFolderBasename},type=bind",
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
