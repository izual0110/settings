# Settings

Personal configuration files for [Zed](zed/), [VS Code](vs%20code/), and [tmux](tmux/).

## Devcontainer builder

Open [index.html](index.html) in a browser to configure an Ubuntu or Fedora development container. No build step required.

Run the generator from your project's root directory:

```sh
bash /path/to/settings/generate-devcontainer.sh --os ubuntu --java-lts --clojure
```

Creates `.devcontainer/Dockerfile` and `.devcontainer/devcontainer.json`. Then reopen the project in a Dev Containers-compatible editor.

Use `--help` for all options or `--force` to replace existing generated files.

## CI

GitHub Actions builds Docker images for Ubuntu `latest` and Fedora `latest` on pushes, pull requests, and manual runs. Both builds enable all optional packages, using Java LTS because the LTS and latest Java options are mutually exclusive. Images are built for validation only and are not published. Docker BuildKit layers are cached in GitHub Actions separately for each distribution; builds still check for updated base images.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
