# Settings

Personal configuration files for [Zed](zed/), [VS Code](vs%20code/), and [tmux](tmux/).

## Devcontainer builder

Open [index.html](index.html) in a browser to configure an Ubuntu, Fedora, or Alpine development container. No build step required.

Run the generator from your project's root directory:

```sh
bash /path/to/settings/generate-devcontainer.sh --os ubuntu --java-lts --clojure
```

Creates `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json`. Then reopen the project in a Dev Containers-compatible editor.

Use `--help` for all options or `--force` to replace existing generated files.

Alpine defaults to `3.24` (`--version current`); `--version latest` follows the publisher's floating tag. Java uses musl-compatible Temurin images on Alpine.

Selecting Java (or Clojure, which includes Java) reveals optional Maven (`mvn`) and Gradle checkboxes. From the CLI, use `--maven` (alias `--mvn`) and/or `--gradle`; either adds Java LTS if no Java version was selected. Both tools use the selected JDK and are copied from official Docker images, without installing another JDK.

```sh
bash /path/to/settings/generate-devcontainer.sh --os alpine --java-lts --maven --gradle
```

Use `--mariadb` (or the **MariaDB client** checkbox under Tools) to install the distribution's SQL client without a database server: `mariadb-client` on Ubuntu/Alpine, `mariadb` on Fedora.

## CI

GitHub Actions builds Docker images for Ubuntu, Fedora, and Alpine `latest` on pushes, pull requests, and manual runs. All builds enable all optional packages, including Maven and Gradle, using Java LTS because the LTS and latest Java options are mutually exclusive. Images are built for validation only and are not published. Docker BuildKit layers are cached in GitHub Actions separately for each distribution; builds still check for updated base images.

## Tests

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_devcontainer.js
```

Frontend tests use Node.js built-in modules; no npm install is required.
